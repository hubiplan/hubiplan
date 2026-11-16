"""Löschliste (Gesamtaudit 31.10.b, Frage 7): erledigte Löschungen überleben ein Backup.

Wird ein älteres Backup eingespielt, sind gelöschte Daten wieder da. Deshalb steht jede
Löschung zusätzlich in einer Datei außerhalb der Datenbank (eigenes Volume, nur Kennungen
und Zeitpunkte, keine Namen). Beim Start des Backends und täglich wird die Liste erneut
angewendet: Was dort steht und in der Datenbank wieder ungelöscht ist, wird nochmals
gelöscht. Die Kennung allein reicht nicht (nach dem Einspielen vergibt die Datenbank
Nummern neu), deshalb muss auch der Anlagezeitpunkt der Mitgliedschaft passen.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


def path() -> Path | None:
    value = getattr(settings, "LOESCHLISTE_PATH", "")
    return Path(value) if value else None


def note(membership, *, after_deadline: bool) -> None:
    """Löschung nach dem Speichern in die Liste schreiben (eine Zeile je Löschung)."""
    _append(membership, {"d": after_deadline})


def note_history(membership) -> None:
    """Namen auch aus Chronik und Ehrungen entfernt (Fachfrage FQ12)."""
    _append(membership, {"d": True, "h": True})


def note_readmitted(membership) -> None:
    """Wiederaufnahme: eine frühere Löschung dieser Mitgliedschaft gilt nicht mehr."""
    _append(membership, {"r": True})


def note_unit(org_id: int, created_at) -> None:
    """Einheit endgültig gelöscht (Gesamtaudit 10.11., F02): ``e`` statt ``m``."""
    _write(
        {"e": org_id, "c": created_at.isoformat(), "at": timezone.now().isoformat()},
        f"Einheit {org_id}",
    )


def _append(membership, extra: dict) -> None:
    entry = {
        "m": membership.pk,
        "o": membership.organization_id,
        "p": membership.person_id,
        "c": membership.created_at.isoformat(),
        **extra,
        "at": timezone.now().isoformat(),
    }
    _write(entry, f"Mitgliedschaft {membership.pk}")


def _write(entry: dict, what: str) -> None:
    target = path()
    if target is None:
        return

    def write():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            # Die Löschung selbst ist geschehen; fehlt nur der Eintrag, meldet das der Alarm
            logger.exception("Löschliste nicht beschreibbar: %s", target)
            from core.alarm import send_alert

            send_alert(
                "Löschliste nicht beschreibbar",
                [f"Der Eintrag zu {what} fehlt in {target}."],
            )

    transaction.on_commit(write)


def _lines() -> list[dict]:
    target = path()
    if target is None or not target.exists():
        return []
    result = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            result.append(item)
    return result


def entries() -> list[dict]:
    return [item for item in _lines() if isinstance(item.get("m"), int)]


def unit_entries() -> list[dict]:
    """Gelöschte Einheiten in der Reihenfolge der Löschung (Untereinheiten zuerst)."""
    return [item for item in _lines() if isinstance(item.get("e"), int)]


def apply() -> int:
    """Liste erneut anwenden; Rückgabe: Anzahl erneut gelöschter Mitgliedschaften."""
    from core.tenancy import rls_bypass
    from organizations.deletion import reapply

    # Zuerst ganze Einheiten (Gesamtaudit 10.11., F02); ihre Mitgliedschaften gehen mit
    units = reapply(unit_entries())
    if units:
        logger.warning("Löschliste: %s Einheiten erneut gelöscht", units)
        from core.alarm import send_alert

        send_alert(
            "Löschliste nach dem Einspielen angewendet",
            [
                f"{units} gelöschte Einheiten waren in der Datenbank wieder vorhanden und "
                "wurden erneut gelöscht (vermutlich wurde ein älteres Backup eingespielt)."
            ],
        )

    from .models import Membership
    from .workflows import erase_history, purge_membership, report_failures

    # Je Mitgliedschaft zählt der letzte Eintrag (Löschung oder Wiederaufnahme)
    last: dict[tuple, dict] = {}
    for item in entries():
        last[(item["m"], item.get("c"))] = item
    items = [item for item in last.values() if not item.get("r")]
    count = 0
    failed: list[int] = []
    with rls_bypass():
        # Die Liste wächst mit jeder Löschung und wird täglich angewendet: Stand der
        # Mitgliedschaften gesammelt lesen statt einer Abfrage je Eintrag (Gesamtaudit 15.11.,
        # PF-10). Angefasst wird nur, was wieder ungelöscht ist.
        found = _memberships([item["m"] for item in items])
        todo = []
        for item in items:
            row = found.get(item["m"])
            created = parse_datetime(item.get("c") or "")
            if row is None or created is None or row["created_at"] != created:
                continue
            if row["organization_id"] != item.get("o"):
                continue
            if row["purged_at"] is not None and not item.get("h"):
                continue
            todo.append((item, row))
        history = _history_left([row for item, row in todo if item.get("h")])
        for item, row in todo:
            restored = row["purged_at"] is None
            if not restored and row["pk"] not in history:
                continue
            try:
                membership = Membership.objects.select_related("person", "organization").get(
                    pk=row["pk"]
                )
                with transaction.atomic():
                    again = restored
                    if restored:
                        purge_membership(
                            membership, after_deadline=bool(item.get("d")), listed=True
                        )
                    if item.get("h"):
                        # Auch die Namen in Chronik und Ehrungen (FQ12); ändert nichts, wenn
                        # sie schon entfernt sind
                        changed = erase_history(membership, listed=True)
                        again = again or any(changed.values())
            except Exception:  # noqa: BLE001 – ein Eintrag darf die übrigen nicht aufhalten
                logger.exception("Löschliste: Mitgliedschaft %s nicht erneut gelöscht", row["pk"])
                failed.append(row["pk"])
                continue
            if again:
                count += 1
    if failed:
        report_failures("Löschliste", failed)
    if count:
        logger.warning("Löschliste: %s Mitgliedschaften erneut gelöscht", count)
        from core.alarm import send_alert

        send_alert(
            "Löschliste nach dem Einspielen angewendet",
            [
                f"{count} Mitgliedschaften waren in der Datenbank wieder ungelöscht und wurden "
                "erneut gelöscht (vermutlich wurde ein älteres Backup eingespielt)."
            ],
        )
    return count


def _memberships(pks: list[int]) -> dict[int, dict]:
    """Stand der Mitgliedschaften auf der Liste, in Blöcken gelesen (ohne RLS-Kontext)."""
    from .models import Membership

    result = {}
    unique = sorted(set(pks))
    for start in range(0, len(unique), 1000):
        for row in Membership.objects.filter(pk__in=unique[start : start + 1000]).values(
            "pk", "organization_id", "person_id", "created_at", "purged_at"
        ):
            result[row["pk"]] = row
    return result


def _history_left(rows: list[dict]) -> set[int]:
    """Mitgliedschaften, bei denen Chronik, Würden oder Ehrungen den Namen wieder tragen.

    Gesammelt über alle Einträge mit ``h``, je Tabelle eine Abfrage. Großzügig: Ein Treffer
    in einem anderen Verein der Person oder ein Name, der wegen einer Mitgliedschaft
    anderswo bleibt, führt nur zu einem wirkungslosen Aufruf von ``erase_history``."""
    if not rows:
        return set()
    from competitions.models import AwardGrant
    from honors.models import Companion, Reign
    from qualifications.models import Qualification

    from .models import HonoraryTitleAward, Person
    from .workflows import NAME_REMOVED

    persons = {row["person_id"] for row in rows}
    memberships = {row["pk"] for row in rows}
    hit_persons: set[int] = set()
    for model in (Reign, Companion, HonoraryTitleAward, Qualification):
        hit_persons.update(
            model.objects.filter(person_id__in=persons).values_list("person_id", flat=True)
        )
    # Name der Person wieder da: großzügig für jede Person der Liste; ob der Name wirklich
    # entfernt wird (keine Mitgliedschaft außerhalb des Vereinsbaums), entscheidet
    # erase_history, sonst ist der Aufruf wirkungslos. Namen sind verschlüsselt, der
    # Vergleich geht nur hier.
    hit_persons.update(
        person.pk
        for person in Person.objects.filter(pk__in=persons)
        if person.last_name != NAME_REMOVED
    )
    hit = set(
        AwardGrant.objects.filter(membership_id__in=memberships).values_list(
            "membership_id", flat=True
        )
    )
    hit.update(row["pk"] for row in rows if row["person_id"] in hit_persons)
    return hit
