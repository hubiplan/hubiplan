"""Abgleich der Erfassung ohne Netz: gesammelte Schritte der App nacheinander anwenden."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, ValidationError

from . import bird
from .models import (
    Competition,
    Prize,
    Scoring,
    ShootOff,
    Starter,
)
from .shootoffs import create_shootoff, list_shootoffs, update_shootoff, update_shootoff_entry
from .starters import (
    _decimal,
    _starters_with_values,
    _uuid,
    create_starter,
    delete_starter,
    set_score,
    update_starter,
)

RESET_NOTE = "Der Wettbewerb wurde zurückgesetzt, die Eingabe ist verworfen."


@transaction.atomic
def sync(org, user, comp: Competition, ops, generation=None) -> dict:
    """Eingaben aus dem Standmodus nachreichen (auch für den Standzugang). ``generation``:
    der Stand des Zurücksetzens, den das Gerät kennt; passt er nicht, stammen die Eingaben
    von vor dem Zurücksetzen und werden verworfen."""
    comp = Competition.objects.select_for_update().get(pk=comp.pk)
    ops = ops or []
    if not isinstance(ops, list) or len(ops) > 2000:
        raise ValidationError(gettext("Höchstens 2000 Eingaben auf einmal."))
    results, conflicts = [], []
    stale = generation is not None and str(generation) != str(comp.generation)
    for op in ops:
        if stale:
            results.append({"ok": False, "error": RESET_NOTE})
            continue
        try:
            if not isinstance(op, dict):
                raise TypeError
            with transaction.atomic():
                results.append(_apply_op(org, user, comp, op, conflicts))
        except (ValidationError, NotFound) as exc:
            results.append({"ok": False, "error": _message(exc)})
        except (
            Starter.DoesNotExist,
            Scoring.DoesNotExist,
            Prize.DoesNotExist,
            ShootOff.DoesNotExist,
            ValueError,
            TypeError,
        ):
            results.append({"ok": False, "error": "Ungültige Eingabe."})
    comp.refresh_from_db()
    keys = {
        str(k): pk
        for pk, k in comp.starters.filter(client_key__isnull=False).values_list("pk", "client_key")
    }
    for pk, aliases in comp.starters.exclude(aliases=[]).values_list("pk", "aliases"):
        keys.update({str(a): pk for a in aliases})
    out = {
        "results": results,
        "conflicts": conflicts,
        "keys": keys,
        "starters": _starters_with_values(comp),
        "status": comp.status,
        "generation": comp.generation,
    }
    if comp.form == Competition.Form.BIRD:
        out["bird"] = _jsonable(bird.state(comp))
    else:
        out["shootoffs"] = list_shootoffs(comp)
        shootoff_keys = {}
        for pk, key, aliases in ShootOff.objects.filter(scoring__competition=comp).values_list(
            "pk", "client_key", "aliases"
        ):
            if key:
                shootoff_keys[str(key)] = pk
            shootoff_keys.update({str(a): pk for a in aliases or []})
        out["shootoff_keys"] = shootoff_keys
    return out


def _starter_ref(comp, ref) -> Starter:
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        return Starter.objects.get(pk=int(ref), competition=comp)
    key = _uuid(ref)
    if key is None:  # sonst träfe client_key=None jeden Starter ohne Gerätekennung
        raise Starter.DoesNotExist
    found = Starter.objects.filter(client_key=key, competition=comp).first()
    return found or Starter.objects.get(competition=comp, aliases__contains=[str(key)])


def _apply_op(org, user, comp, op, conflicts) -> dict:
    kind = op.get("op")
    if kind == "starter":
        merged: list = []
        s = create_starter(org, user, comp, op, merged)
        if merged:
            conflicts.append(
                {
                    "starter": s.pk,
                    "name": s.name,
                    "note": "war schon von einem anderen Gerät eingetragen, zusammengeführt",
                }
            )
        return {"ok": True, "starter": s.pk}
    if kind == "starter_update":
        s = _starter_ref(comp, op.get("starter"))
        update_starter(org, user, s, op)
        return {"ok": True}
    if kind == "starter_delete":
        try:
            s = _starter_ref(comp, op.get("starter"))
        except Starter.DoesNotExist:
            return {"ok": True}  # schon entfernt (zweites Senden vom Gerät)
        delete_starter(org, user, s)
        return {"ok": True}
    if kind == "score":
        s = _starter_ref(comp, op.get("starter"))
        scoring = Scoring.objects.get(
            pk=op.get("scoring"), competition=comp, kind=Scoring.Kind.INDIVIDUAL
        )
        at = parse_datetime(str(op.get("at") or "")) if op.get("at") else None
        value, conflict = set_score(org, user, comp, scoring, s, op.get("value"), at)
        if conflict:
            conflicts.append(
                {"starter": s.pk, "name": s.name, "scoring": scoring.pk, "value": str(value)}
            )
        return {"ok": True}
    if kind == "hits":
        from . import target_views

        s = _starter_ref(comp, op.get("starter"))
        scoring = Scoring.objects.get(
            pk=op.get("scoring"), competition=comp, kind=Scoring.Kind.INDIVIDUAL
        )
        at = parse_datetime(str(op.get("at") or "")) if op.get("at") else None
        data = target_views.set_hits(
            org,
            user,
            comp,
            scoring,
            s,
            op.get("hits"),
            op.get("source"),
            at=at,
            sample_keys=op.get("samples"),
        )
        if data.get("conflict"):
            conflicts.append(
                {
                    "starter": s.pk,
                    "name": s.name,
                    "note": "Treffer wurden auf einem anderen Gerät später geändert, diese gelten",
                }
            )
        return {"ok": True}
    if kind == "shot":
        s = _starter_ref(comp, op.get("starter"))
        hits = op.get("hits") or []
        if not isinstance(hits, list):
            raise TypeError
        shot = bird.fire(
            org,
            user,
            comp,
            s,
            hits,
            at=bird.parse_at(op.get("at")),
            client_key=bird.parse_key(op.get("client_key")),
        )
        return {"ok": True, "shot": shot.number}
    if kind == "undo":
        bird.undo(org, user, comp, client_key=bird.parse_key(op.get("client_key")))
        return {"ok": True}
    if kind in ("shootoff", "shootoff_rules", "shootoff_value", "shootoff_member"):
        return _shootoff_op(org, user, comp, kind, op, conflicts)
    if kind == "draw":
        s = _starter_ref(comp, op.get("starter"))
        how = op.get("how") if op.get("how") in ("hut", "digital") else "hut"
        number, note = bird.draw(org, user, comp, s, op.get("number"), how)
        if note:
            conflicts.append({"starter": s.pk, "name": s.name, "number": number, "note": note})
        return {"ok": True, "number": number}
    raise ValidationError(gettext("Unbekannte Eingabe."))


def _shootoff_ref(comp, ref) -> ShootOff:
    qs = ShootOff.objects.filter(scoring__competition=comp)
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        return qs.get(pk=int(ref))
    key = _uuid(ref)
    if key is None:
        raise ShootOff.DoesNotExist
    return qs.filter(client_key=key).first() or qs.get(aliases__contains=[str(key)])


def _shootoff_op(org, user, comp, kind, op, conflicts) -> dict:
    """Stechen aus der Warteschlange eines Geräts (auch ohne Empfang erfasst)."""
    if kind == "shootoff":
        key = _uuid(op.get("client_key"))
        if key is None:
            raise ValidationError(gettext("Gerätekennung fehlt."))
        try:
            return {"ok": True, "shootoff": _shootoff_ref(comp, str(key)).pk}
        except ShootOff.DoesNotExist:
            pass  # noch nicht angekommen
        keys = sorted(op.get("keys") or [])
        rules = {k: op[k] for k in ("shots", "counted_shots") if k in op}
        try:
            data = create_shootoff(
                org, user, comp, {"scoring": op.get("scoring"), "keys": keys, **rules}
            )
            ShootOff.objects.filter(pk=data["id"]).update(client_key=key)
            return {"ok": True, "shootoff": data["id"]}
        except ValidationError:
            # Ein anderes Gerät hat dieses Stechen schon angelegt: zusammenführen
            so = (
                ShootOff.objects.filter(scoring_id=op.get("scoring"), scoring__competition=comp)
                .order_by("-number")
                .prefetch_related("entries")
                .first()
            )
            if so is None or sorted(e.key for e in so.entries.all()) != keys:
                raise
            so.aliases = [*so.aliases, str(key)]
            so.save(update_fields=["aliases"])
            wanted = (
                rules.get("shots", so.shots),
                rules.get("counted_shots", so.counted_shots),
            )
            note = "war schon von einem anderen Gerät angelegt, zusammengeführt"
            if wanted != (so.shots, so.counted_shots):
                note += "; dort gelten andere Regeln, bitte prüfen"
            conflicts.append({"name": f"{so.number}. Stechen", "note": note})
            return {"ok": True, "shootoff": so.pk}
    so = _shootoff_ref(comp, op.get("shootoff"))
    if kind == "shootoff_rules":
        rules = {k: op[k] for k in ("shots", "counted_shots") if k in op}
        update_shootoff(org, user, comp, so.pk, rules)
        return {"ok": True}
    entry = so.entries.all()
    entry = next((e for e in entry if e.key == op.get("key")), None)
    if entry is None:
        raise ValidationError(gettext("Unbekannter Teilnehmer im Stechen."))
    if kind == "shootoff_member":
        update_shootoff_entry(org, user, comp, entry.pk, {"membership": op.get("membership")})
        return {"ok": True}
    # Wert: die spätere Eingabe gilt, wie bei den Ergebnissen
    at = parse_datetime(str(op.get("at") or "")) if op.get("at") else None
    new = _decimal(op.get("value"), "value")
    if at is not None and entry.value is not None and at < entry.updated_at and entry.value != new:
        conflicts.append(
            {
                "name": f"{entry.name} ({so.number}. Stechen)",
                "value": str(entry.value),
                "note": "ein anderes Gerät hat später einen Wert eingetragen, der gilt",
            }
        )
        return {"ok": True}
    update_shootoff_entry(org, user, comp, entry.pk, {"value": op.get("value")})
    return {"ok": True}


def _message(exc) -> str:
    detail = getattr(exc, "detail", str(exc))
    if isinstance(detail, dict):
        detail = next(iter(detail.values()), "")
    if isinstance(detail, list):
        detail = detail[0] if detail else ""
    return str(detail)


def _jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj
