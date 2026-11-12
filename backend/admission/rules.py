"""Zustimmungen nach Satzung: Wer muss der Aufnahme zustimmen?

Regel (``ApplicationForm.rule``)::

    {"mode": "single" | "rule" | "assembly",
     "roles": [Rollen-IDs, jede muss zustimmen],
     "min_count": Mindestzahl verschiedener Personen (0 = keine),
     "pool": [Rollen-IDs, aus denen die Mindestzahl kommt; leer = alle, die zustimmen dürfen],
     "unit": Zustimmung der gewünschten Untereinheit nötig,
     "auto_admit": nach der letzten Zustimmung automatisch aufnehmen,
     "multi_role": eine Person darf mehrere geforderte Rollen abdecken}

- ``single``: Eine Person mit Recht „Mitglieder bearbeiten“ nimmt auf (Vorgabe).
- ``rule``: Zustimmungen sammeln, bis die Regel erfüllt ist.
- ``assembly``: Die Versammlung beschließt; der Vorstand trägt das Ergebnis mit Datum ein.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext

from access.catalog import MEMBERS_EDIT
from access.models import Role, RoleAssignment

MODES = ("single", "rule", "assembly")


def clean_rule(raw, org) -> dict:
    from rest_framework.exceptions import ValidationError

    from .models import default_rule

    rule = default_rule()
    if not isinstance(raw, dict):
        return rule
    mode = raw.get("mode", "single")
    if mode not in MODES:
        raise ValidationError({"rule": gettext("Unbekannte Regel.")})
    rule["mode"] = mode
    known = set(Role.objects.filter(organization=org).values_list("pk", flat=True))
    for key in ("roles", "pool"):
        ids = raw.get(key) or []
        if not isinstance(ids, list) or any(not isinstance(i, int) for i in ids):
            raise ValidationError({"rule": gettext("Ungültige Rollen.")})
        if set(ids) - known:
            raise ValidationError({"rule": gettext("Diese Rolle gibt es hier nicht.")})
        rule[key] = list(dict.fromkeys(ids))
    count = raw.get("min_count") or 0
    if not isinstance(count, int) or not 0 <= count <= 20:
        raise ValidationError({"rule": gettext("Die Mindestzahl muss zwischen 0 und 20 liegen.")})
    rule["min_count"] = count
    for key in ("unit", "auto_admit", "multi_role"):
        rule[key] = bool(raw.get(key))
    if mode == "rule" and not (rule["roles"] or rule["min_count"] or rule["unit"]):
        raise ValidationError(
            {"rule": gettext("Bitte Rollen, eine Mindestzahl oder die Untereinheit angeben.")}
        )
    return rule


def user_roles(user, org) -> dict[int, str]:
    """Aktive Rollen eines Kontos in der Einheit: ID → Name."""
    if user is None or not user.is_authenticated:
        return {}
    rows = (
        RoleAssignment.objects.active()
        .filter(user=user, organization=org, membership__isnull=True)
        .select_related("role")
    )
    return {a.role_id: a.role.name for a in rows}


def may_approve(rule: dict, roles: dict[int, str], perms: set[str]) -> bool:
    """Darf diese Person eine Zustimmung abgeben, die nach der Regel zählt?"""
    if rule.get("mode") != "rule":
        return False
    wanted = set(rule.get("roles") or []) | set(rule.get("pool") or [])
    if set(roles) & wanted:
        return True
    # Mindestzahl ohne Kreis: alle, die Mitglieder bearbeiten dürfen
    return bool(rule.get("min_count")) and not rule.get("pool") and MEMBERS_EDIT in perms


def _cover(required: list[int], approvers: list[set[int]], used: set[int]) -> bool:
    """Jede geforderte Rolle von einer anderen Person (kleine Suche, Vereinsgröße)."""
    if not required:
        return True
    first, rest = required[0], required[1:]
    for i, roles in enumerate(approvers):
        if i in used or first not in roles:
            continue
        if _cover(rest, approvers, used | {i}):
            return True
    return False


@dataclass
class State:
    met: bool
    disputed: bool
    missing: list[str] = field(default_factory=list)


def evaluate(rule: dict, approvals, role_names: dict[int, str] | None = None) -> State:
    """Ist die Regel mit diesen Zustimmungen erfüllt? ``approvals``: gültige Einträge."""
    approvals = list(approvals)
    disputed = any(a.decision == "reject" for a in approvals)
    mode = rule.get("mode", "single")
    if mode != "rule":
        return State(met=True, disputed=disputed)
    yes = [a for a in approvals if a.decision == "approve"]
    persons: dict[object, set[int]] = {}
    unit_ok = False
    for a in yes:
        if a.for_unit:
            unit_ok = True
            continue
        key = a.user_id or f"name:{a.user_name}"
        persons.setdefault(key, set()).update(a.role_ids or [])
    approvers = list(persons.values())
    names = role_names or {}
    missing: list[str] = []
    required = list(rule.get("roles") or [])
    if rule.get("multi_role"):
        for rid in required:
            if not any(rid in roles for roles in approvers):
                missing.append(names.get(rid, gettext("Rolle")))
    elif not _cover(required, approvers, set()):
        for rid in required:
            if not any(rid in roles for roles in approvers):
                missing.append(names.get(rid, gettext("Rolle")))
        if not missing:
            missing.append(gettext("verschiedene Personen für die geforderten Rollen"))
    count = rule.get("min_count") or 0
    pool = set(rule.get("pool") or [])
    counted = [r for r in approvers if not pool or r & pool]
    if len(counted) < count:
        missing.append(gettext("noch {n} Zustimmung(en)").format(n=count - len(counted)))
    if rule.get("unit") and not unit_ok:
        missing.append(gettext("Zustimmung der Untereinheit"))
    return State(met=not missing, disputed=disputed, missing=missing)


def role_names(org) -> dict[int, str]:
    return dict(Role.objects.filter(organization=org).values_list("pk", "name"))


def describe(rule: dict, org) -> str:
    """Regel in einem Satz, z. B. für die Hilfe der Prüfseite."""
    mode = rule.get("mode", "single")
    if mode == "single":
        return gettext("Eine Person mit Recht „Mitglieder bearbeiten“ entscheidet.")
    if mode == "assembly":
        return gettext("Die Versammlung beschließt; der Vorstand trägt das Ergebnis ein.")
    names = role_names(org)
    parts = []
    roles = [names.get(r, "?") for r in rule.get("roles") or []]
    if roles:
        parts.append(gettext("Zustimmung von: {roles}").format(roles=", ".join(roles)))
    if rule.get("min_count"):
        pool = [names.get(r, "?") for r in rule.get("pool") or []]
        text = gettext("mindestens {n} Personen").format(n=rule["min_count"])
        if pool:
            text += " " + gettext("aus {roles}").format(roles=", ".join(pool))
        parts.append(text)
    if rule.get("unit"):
        parts.append(gettext("Zustimmung der gewünschten Untereinheit"))
    return "; ".join(parts) + "."
