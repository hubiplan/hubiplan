"""Stechen: anlegen, ändern, löschen, Ergebnisse (ohne HTTP-Views)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from audit.log import diff, record, snapshot
from members.models import Membership

from . import bird, services
from .models import (
    Competition,
    Scoring,
    ShootOff,
    ShootOffEntry,
    Starter,
)
from .starters import _check_decimals, _decimal, _person_name

# --- Stechen ---


def _shootoff_data(so: ShootOff) -> dict:
    return {
        "id": so.pk,
        "scoring": so.scoring_id,
        "number": so.number,
        "shots": so.shots,
        "counted_shots": so.counted_shots,
        "entries": [
            {
                "id": e.pk,
                "key": e.key,
                "starter": e.starter_id,
                "unit": e.unit_id,
                "membership": e.membership_id,
                "name": e.name,
                "value": None if e.value is None else str(e.value),
            }
            for e in so.entries.all()
        ],
    }


def _shootoff_rules(data, defaults: tuple) -> tuple:
    """Schüsse und davon gewertet fürs Stechen; vor Ort festgelegt (Ralf 2026-11-01), sonst
    wie im vorigen Stechen oder wie unter „Einrichten“ vorgeschlagen."""
    shots = bird._positive(data["shots"], "shots") if "shots" in data else defaults[0]  # noqa: SLF001
    counted = (
        bird._positive(data["counted_shots"], "counted_shots")  # noqa: SLF001
        if "counted_shots" in data
        else defaults[1]
    )
    if shots and counted and counted > shots:
        raise ValidationError({"counted_shots": gettext("Höchstens so viele wie Schüsse.")})
    return shots, counted


def _not_final(comp: Competition) -> None:
    if comp.status == Competition.Status.FINAL:
        raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))


# Stechen: angemeldet (Org-API) und über den Standzugang (stand_views) gleich


def list_shootoffs(comp: Competition) -> list:
    qs = ShootOff.objects.filter(scoring__competition=comp).prefetch_related("entries")
    return [_shootoff_data(so) for so in qs.order_by("scoring_id", "number")]


@transaction.atomic
def create_shootoff(org, user, comp: Competition, data) -> dict:
    if comp.status == Competition.Status.FINAL:
        raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))
    scoring = get_object_or_404(Scoring, pk=data.get("scoring"), competition=comp)
    keys = data.get("keys") or []
    standings = services.standings(comp)
    block = next(s for s in standings["scorings"] if s["scoring"] == scoring.pk)
    group = next(
        (t for t in block["open"] if sorted(t["keys"]) == sorted(keys) and t["shootoff"] is None),
        None,
    )
    if group is None:
        raise ValidationError(gettext("Für diese Gruppe ist kein Stechen nötig."))
    number = (scoring.shootoffs.aggregate(m=Max("number"))["m"] or 0) + 1
    previous = scoring.shootoffs.order_by("-number").first()
    defaults = (
        (previous.shots, previous.counted_shots)
        if previous
        else (scoring.shootoff_shots, scoring.shootoff_counted)
    )
    shots, counted = _shootoff_rules(data, defaults)
    so = ShootOff.objects.create(
        organization=org,
        scoring=scoring,
        number=number,
        shots=shots,
        counted_shots=counted,
    )
    rows = {r["key"]: r for r in block["rows"]}
    for key in group["keys"]:
        if key.startswith("u"):
            row = rows[key]
            best = Starter.objects.filter(pk=row.get("best_starter")).first()
            ShootOffEntry.objects.create(
                organization=org,
                shootoff=so,
                unit_id=int(key[1:]),
                membership=best.membership if best else None,
                name=best.name if best else "",
            )
        else:
            starter = Starter.objects.get(pk=int(key[1:]), competition=comp)
            ShootOffEntry.objects.create(
                organization=org, shootoff=so, starter=starter, name=starter.name
            )
    record(org, user, "create", so, diff({}, snapshot(so)))
    so = ShootOff.objects.prefetch_related("entries").get(pk=so.pk)
    return _shootoff_data(so)


@transaction.atomic
def update_shootoff(org, user, comp: Competition, pk: int, data) -> dict:
    if comp.status == Competition.Status.FINAL:
        raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))
    so = get_object_or_404(ShootOff, pk=pk, scoring__competition=comp)
    if so.entries.filter(value__isnull=False).exists():
        raise ValidationError(gettext("Es sind schon Werte eingetragen; erst die Werte löschen."))
    before = snapshot(so)
    so.shots, so.counted_shots = _shootoff_rules(data, (so.shots, so.counted_shots))
    so.save(update_fields=["shots", "counted_shots"])
    record(org, user, "update", so, diff(before, snapshot(so)))
    so = ShootOff.objects.prefetch_related("entries").get(pk=so.pk)
    return _shootoff_data(so)


@transaction.atomic
def delete_shootoff(org, user, comp: Competition, pk: int) -> None:
    if comp.status == Competition.Status.FINAL:
        raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))
    so = get_object_or_404(ShootOff, pk=pk, scoring__competition=comp)
    if so.scoring.shootoffs.filter(number__gt=so.number).exists():
        raise ValidationError(gettext("Erst das spätere Stechen entfernen."))
    record(org, user, "delete", so, diff(snapshot(so), {}))
    so.delete()


@transaction.atomic
def update_shootoff_entry(org, user, comp: Competition, pk: int, data) -> dict:
    _not_final(comp)
    entry = get_object_or_404(
        ShootOffEntry.objects.select_related("shootoff__scoring__source"),
        pk=pk,
        shootoff__scoring__competition=comp,
    )
    before = snapshot(entry)
    scoring = entry.shootoff.scoring
    if "value" in data:
        value = _decimal(data["value"], "value")
        if value is not None:
            metric = scoring.source if scoring.kind == Scoring.Kind.UNIT else scoring
            _check_decimals(value, metric.decimals, "value")
            per_shot = scoring.max_per_shot or metric.max_per_shot
            count = entry.shootoff.counted_shots or entry.shootoff.shots
            if per_shot is not None and count and value > per_shot * count:
                raise ValidationError(
                    {"value": gettext("Höchstens {x}.").format(x=services.fmt(per_shot * count, 0))}
                )
        entry.value = value
    if entry.unit_id and "membership" in data:
        if data["membership"]:
            m = (
                Membership.objects.filter(
                    organization=org, pk=data["membership"], purged_at__isnull=True
                )
                .select_related("person")
                .first()
            )
            if m is None:
                raise ValidationError({"membership": gettext("Unbekanntes Mitglied.")})
            entry.membership = m
            entry.name = _person_name(m)
        else:
            entry.membership = None
            entry.name = str(data.get("name") or "").strip()[:200]
    entry.save()
    changes = diff(before, snapshot(entry))
    if changes:
        record(org, user, "update", entry, changes)
    return _shootoff_data(ShootOff.objects.prefetch_related("entries").get(pk=entry.shootoff_id))
