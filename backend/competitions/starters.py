"""Starter eines Wettbewerbs: anlegen, ändern, löschen, Ergebnisse setzen (ohne HTTP-Views)."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from audit.log import diff, record, snapshot
from members.models import Membership
from members.personsearch import ordered
from organizations.models import Department

from . import bird, services
from .models import (
    Competition,
    Hit,
    Presence,
    Prize,
    Score,
    Starter,
)


def _units(org) -> list[Department]:
    return list(Department.objects.filter(organization=org).order_by("sort_order", "name"))


# --- Starter ---


def _starter_data(s: Starter, value_by_scoring: dict | None = None) -> dict:
    return {
        "id": s.pk,
        "name": s.name,
        "club": s.club,
        "guest": s.is_guest,
        "adult": s.guest_adult,
        "membership": s.membership_id,
        "unit": s.unit_id,
        "unit_name": s.unit.name if s.unit_id else "",
        "number": s.number,
        "out_of_competition": s.out_of_competition,
        "presence": s.presence,
        "drawn_how": s.drawn_how,
        "key": str(s.client_key) if s.client_key else None,
        "values": value_by_scoring or {},
    }


def _open_for_entries(comp: Competition) -> None:
    if comp.status == Competition.Status.FINAL:
        raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))


@transaction.atomic
def create_starter(org, user, comp: Competition, data, merged: list | None = None) -> Starter:
    """Mitglied (``membership``) oder Gast (``name``, ``club``) als Starter anlegen.
    ``client_key``: Kennung vom Gerät (Offline-Betrieb); ein zweites Senden liefert
    denselben Starter zurück. Mit ``merged`` (Abgleich mehrerer Tablets): hat ein anderes
    Gerät das Mitglied schon angelegt, gilt die Kennung als zweiter Name dieses Starters,
    und die folgenden Eingaben des Geräts landen dort (Ralf 2026-11-01)."""
    _open_for_entries(comp)
    key = _uuid(data.get("client_key"))
    if key:
        same = Starter.objects.filter(competition=comp, client_key=key).select_related("unit")
        if same.exists():
            return same.get()
        alias = comp.starters.filter(aliases__contains=[str(key)]).first()
        if alias:
            return alias
    unit = _unit_or_none(org, data.get("unit"))
    if data.get("membership"):
        m = (
            Membership.objects.filter(
                organization=org, pk=data["membership"], purged_at__isnull=True
            )
            .select_related("person")
            .first()
        )
        if m is None:
            raise ValidationError({"membership": gettext("Unbekanntes Mitglied.")})
        existing = comp.starters.filter(membership=m).first()
        if existing and key and merged is not None:
            existing.aliases = [*existing.aliases, str(key)]
            existing.save(update_fields=["aliases", "updated_at"])
            merged.append(existing)
            return existing
        if existing:
            raise ValidationError(
                {"membership": gettext("{x} ist schon eingetragen.").format(x=_person_name(m))}
            )
        s = Starter(
            organization=org,
            competition=comp,
            membership=m,
            name=_person_name(m),
            unit_id=unit.pk if unit else services.default_unit(org, m, comp.date),
        )
    else:
        name = str(data.get("name", "")).strip()[:200]
        if not name:
            raise ValidationError({"name": gettext("Bitte einen Namen angeben.")})
        s = Starter(
            organization=org,
            competition=comp,
            name=name,
            club=str(data.get("club", "")).strip()[:200],
            guest_adult=bool(data.get("adult", False)),
            unit_id=unit.pk if unit else None,
        )
    s.number = str(data.get("number", "") or "").strip()[:20]
    s.client_key = key
    try:
        with transaction.atomic():
            s.save()
            record(org, user, "create", s, diff({}, snapshot(s)))
    except IntegrityError as exc:
        raise ValidationError({"membership": gettext("Schon eingetragen.")}) from exc
    return Starter.objects.select_related("unit").get(pk=s.pk)


def _uuid(raw):
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError as exc:
        raise ValidationError({"client_key": gettext("Ungültige Kennung.")}) from exc


def _person_name(m: Membership) -> str:
    return f"{m.person.first_name} {m.person.last_name}".strip()


def _unit_or_none(org, raw):
    if raw in (None, "", 0, "0"):
        return None
    unit = Department.objects.filter(organization=org, pk=raw).first()
    if unit is None:
        raise ValidationError({"unit": gettext("Unbekannte Untereinheit.")})
    return unit


@transaction.atomic
def delete_starter(org, user, s: Starter) -> None:
    """Starter mit seinen Werten entfernen. Schüsse und Pfänder beim Vogelschießen behalten
    den Namen."""
    _open_for_entries(s.competition)
    record(org, user, "delete", s, diff(snapshot(s), {}))
    # Pfänder behalten den Namen als freien Gewinner; die Angabe „volljährig“ des Gastes geht
    # mit (Mitglieder: nicht angegeben, der Verein trägt es bei Bedarf nach)
    if s.is_guest and s.guest_adult:
        Prize.objects.filter(winner=s).update(winner_adult=True)
    s.delete()


@transaction.atomic
def update_starter(org, user, s: Starter, data) -> None:
    _open_for_entries(s.competition)
    before = snapshot(s)
    if "unit" in data:
        unit = _unit_or_none(org, data["unit"])
        s.unit_id = unit.pk if unit else None
    if "number" in data:
        s.number = str(data["number"] or "").strip()[:20]
        if s.competition.form == Competition.Form.BIRD and s.number:
            n = bird.lot(s.number)
            if n is None:
                raise ValidationError({"number": gettext("Losnummer: bitte eine ganze Zahl ab 1.")})
            other = s.competition.starters.exclude(pk=s.pk).filter(number=str(n)).first()
            if other:
                raise ValidationError(
                    {"number": gettext("Nummer {n} hat schon {name}.").format(n=n, name=other.name)}
                )
            s.number = str(n)
            s.drawn_how = s.drawn_how or "hut"
    if "presence" in data:
        if data["presence"] not in Presence.values:
            raise ValidationError({"presence": gettext("Unbekannte Angabe.")})
        s.presence = data["presence"]
    if "out_of_competition" in data:
        s.out_of_competition = bool(data["out_of_competition"])
    if s.is_guest:
        if "name" in data:
            name = str(data["name"] or "").strip()[:200]
            if not name:
                raise ValidationError({"name": gettext("Bitte einen Namen angeben.")})
            s.name = name
        if "club" in data:
            s.club = str(data["club"] or "").strip()[:200]
        if "adult" in data:
            s.guest_adult = bool(data["adult"])
    s.save()
    changes = diff(before, snapshot(s))
    if changes:
        record(org, user, "update", s, changes)


def _decimal(raw, field: str) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw).replace(",", ".").strip())
    except InvalidOperation as exc:
        raise ValidationError({field: gettext("Bitte eine Zahl eingeben.")}) from exc
    if not value.is_finite() or value < 0 or value >= Decimal("10000000"):
        raise ValidationError({field: gettext("Bitte eine gültige Zahl eingeben.")})
    return value


def _check_decimals(value: Decimal, decimals: int, field: str):
    if value != value.quantize(Decimal(1).scaleb(-decimals)):
        raise ValidationError(
            {field: gettext("Höchstens {decimals} Nachkommastellen.").format(decimals=decimals)}
            if decimals
            else {field: gettext("Bitte eine ganze Zahl eingeben.")}
        )


@transaction.atomic
def set_score(org, user, comp, scoring, starter, raw, at=None, *, from_hits=False):
    """Wert setzen (leer: löschen). ``at``: Zeitpunkt der Eingabe auf dem Gerät. Wurde der
    Wert auf dem Server danach geändert, gilt die spätere Eingabe; zurück kommt dann der
    gültige Wert und ``True`` (Konflikt)."""
    comp = Competition.objects.select_for_update().get(pk=comp.pk)
    scoring.refresh_from_db()
    _open_for_entries(comp)
    value = _decimal(raw, "value")
    existing = Score.objects.select_for_update().filter(scoring=scoring, starter=starter).first()
    if at is not None and existing and existing.updated_at > at and existing.value != value:
        return existing.value, True
    if value is None:
        if existing:
            record(org, user, "delete", existing, diff(snapshot(existing), {}))
            existing.delete()
        return None, False
    _check_decimals(value, scoring.decimals, "value")
    if scoring.max_value is not None and value > scoring.max_value:
        raise ValidationError(
            {"value": gettext("Höchstens {x}.").format(x=services.fmt(scoring.max_value, 0))}
        )
    if existing:
        before = snapshot(existing)
        existing.value = value
        existing.from_hits = from_hits
        existing.save()
        changes = diff(before, snapshot(existing))
        if changes:
            record(org, user, "update", existing, changes)
    else:
        existing = Score.objects.create(
            organization=org, scoring=scoring, starter=starter, value=value, from_hits=from_hits
        )
        record(org, user, "create", existing, diff({}, snapshot(existing)))
    if comp.status == Competition.Status.PREPARATION:
        comp.status = Competition.Status.RUNNING
        comp.save(update_fields=["status", "updated_at"])
    return value, False


def _starters_with_values(comp) -> list[dict]:
    values: dict[int, dict] = {}
    latest: dict[int, datetime.datetime] = {}
    for sc in Score.objects.filter(scoring__competition=comp):
        values.setdefault(sc.starter_id, {})[str(sc.scoring_id)] = str(sc.value)
        if sc.starter_id not in latest or sc.updated_at > latest[sc.starter_id]:
            latest[sc.starter_id] = sc.updated_at
    hits: dict[int, dict] = {}
    program_scorings = {}
    for scoring_id, program_id in comp.scorings.values_list("pk", "program_id"):
        if program_id:
            program_scorings.setdefault(program_id, []).append(scoring_id)
    for h in Hit.objects.filter(
        Q(program__competition=comp) | Q(scoring__competition=comp)
    ).order_by("number"):
        ids = program_scorings.get(h.program_id, [h.scoring_id])
        for scoring_id in ids:
            hits.setdefault(h.starter_id, {}).setdefault(str(scoring_id), []).append(
                {"x": str(h.x), "y": str(h.y), "spot": h.spot}
            )
    out = []
    for s in ordered(comp.starters.select_related("unit"), "name", "pk"):
        data = _starter_data(s, values.get(s.pk))
        # Trefferpunkte je Wertung (Antippen am Stand: vorhandene Treffer weiter bearbeiten)
        data["hits"] = hits.get(s.pk, {})
        # Zuletzt erfasst über alle Geräte (Standmodus, Standzugang, Verwaltung)
        data["scored_at"] = latest[s.pk].isoformat() if s.pk in latest else None
        out.append(data)
    return out


def _umlaut_variants(word: str) -> set[str]:
    """„muel“ findet „Müller“, „Müller“ auch „Mueller“."""
    w = word.lower()
    pairs = (("ae", "ä"), ("oe", "ö"), ("ue", "ü"), ("ss", "ß"))
    out = {w}
    for a, b in pairs:
        out |= {v.replace(a, b) for v in list(out)} | {v.replace(b, a) for v in list(out)}
    return out


def unit_members(org, comp: Competition, raw_unit) -> list:
    """Mitglieder einer Untereinheit am Wettbewerbstag (Schütze im Stechen)."""
    from members.models import DepartmentMembership

    unit = _unit_or_none(org, raw_unit)
    if unit is None:
        return []
    on = comp.date
    ids = (
        DepartmentMembership.objects.filter(organization=org, department=unit, valid_from__lte=on)
        .exclude(valid_until__lt=on)
        .values_list("membership_id", flat=True)
    )
    rows = Membership.objects.filter(pk__in=ids, purged_at__isnull=True).select_related("person")
    return sorted(
        ({"membership": m.pk, "name": _person_name(m)} for m in rows),
        key=lambda r: r["name"],
    )
