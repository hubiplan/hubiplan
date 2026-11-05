"""Lesender Schlüsselbestand und ausdrücklich freigegebene Materialentfernung."""

import hashlib
import io
import json
import re
from collections import Counter

from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from core import crypto
from core.keyrotation import Rotation
from core.models import DataKey, DataKeyRotation
from organizations.models import Organization


class KeyInventory(Rotation):
    def __init__(self, owner_id):
        super().__init__(owner_id, io.StringIO())
        self.counts = {name: Counter() for name in ("fields", "files", "marks")}
        self.collect = True

    def record_reference(self, kind, key_id):
        if self.collect and key_id in self.key_ids:
            self.counts[kind][key_id] += 1

    def state(self, *, lock=False):
        keys = DataKey.objects.filter(organization_id=self.owner_id).order_by("pk")
        if lock:
            keys = keys.select_for_update()
        return {
            "keys": list(keys.values()),
            # Auch ein fremder offener Auftrag sperrt die Ausmusterung: sein
            # ausgeblendeter Arbeitsbereich darf keine ungeprüften Verweise bergen.
            "rotations": list(DataKeyRotation.objects.order_by("pk").values()),
        }

    def read(self):
        self.snapshot = self.state()
        self.key_ids = {key["id"] for key in self.snapshot["keys"]}
        rotations = [r for r in self.snapshot["rotations"] if r["organization_id"] == self.owner_id]
        latest = rotations[-1] if rotations else None
        blockers = []
        if any(r["completed_at"] is None for r in self.snapshot["rotations"]):
            blockers.append("Mindestens ein Schlüsselwechsel ist noch offen.")
        if latest is None or latest["completed_at"] is None:
            blockers.append("Ein abgeschlossener Schlüsselwechsel fehlt.")
        complete = True
        try:
            self.preflight()
            from members.models import Person

            for scope_id, key_id in (
                Person.objects.order_by("pk").values_list("scope_id", "marks_key_id").iterator()
            ):
                self.record_reference("marks", key_id)
                if key_id in self.key_ids and crypto.key_owner_id(scope_id) != self.owner_id:
                    raise CommandError(
                        "Suchmarken mit Schlüsselverweis in einem fremden Datenbereich."
                    )
            self.collect = False
            if not blockers:
                self.verify_latest()
        except (CommandError, crypto.KeyUnavailable, crypto.DecryptionError, OSError, ValueError):
            complete = False
            blockers.append(
                "Bestandsprüfung nicht vollständig erfolgreich; Vor-/Abschlussprüfung ausführen."
            )
        if self.state() != self.snapshot:
            complete = False
            blockers.append("Schlüsselbestand oder Wechselaufträge während der Prüfung verändert.")
        keys = []
        for key in self.snapshot["keys"]:
            refs = {kind: counts[key["id"]] for kind, counts in self.counts.items()}
            keys.append(
                {
                    "id": key["id"],
                    "active": key["is_active"],
                    "created_at": key["created_at"],
                    "rewrapped_at": key["rewrapped_at"],
                    "retired_at": key["retired_at"],
                    "retirement_reference": key["retirement_reference"],
                    "references": refs,
                    "eligible": complete
                    and not blockers
                    and not key["is_active"]
                    and key["retired_at"] is None
                    and not any(refs.values()),
                }
            )
        report = {
            "format": 1,
            "organization_id": self.owner_id,
            "complete": complete,
            "blockers": blockers,
            "latest_rotation": latest,
            "keys": keys,
            "backup_check": "external_confirmation_required",
        }
        # Einschließlich Verpackungszustand, aber ohne Schlüsselmaterial auszugeben.
        checksum = hashlib.sha256(
            json.dumps(
                {"report": report, "state": self.snapshot}, sort_keys=True, default=str
            ).encode()
        ).hexdigest()
        report["checksum"] = checksum
        return report


def retire(owner_id, key_id, checksum, reference, *, probe=False):
    if not re.fullmatch(r"[0-9a-f]{64}", checksum or ""):
        raise CommandError("Gültige Prüfkennung des Schlüsselbestandsberichts angeben.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}", reference or ""):
        raise CommandError("Freigabereferenz mit höchstens 100 einfachen Zeichen angeben.")
    inventory = KeyInventory(owner_id)
    report = inventory.read()
    key = next((k for k in inventory.snapshot["keys"] if k["id"] == key_id), None)
    if key is None:
        raise CommandError("Schlüssel gehört nicht zum angegebenen Inhaber.")
    if not report["complete"] or report["blockers"]:
        raise CommandError(
            "Ausmusterung gesperrt: Bestands-/Abschlussprüfung oder offene Wechsel prüfen."
        )
    if key["retired_at"] is not None:
        if probe:
            raise CommandError("Schlüssel bereits ausgemustert; kein neuer Vorher-Satz zulässig.")
        if key["retirement_checksum"] == checksum and key["retirement_reference"] == reference:
            return False
        raise CommandError("Schlüssel bereits mit einer anderen Freigabe ausgemustert.")
    if checksum != report["checksum"]:
        raise CommandError("Prüfkennung veraltet; Bestand erneut lesen und Freigabe prüfen.")
    if not next(k for k in report["keys"] if k["id"] == key_id)["eligible"]:
        raise CommandError(
            "Aktiver oder noch verwendeter Schlüssel darf nicht ausgemustert werden."
        )
    if probe:
        return False
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=owner_id)
        if inventory.state(lock=True) != inventory.snapshot:
            raise CommandError("Schlüsselbestand seit der Prüfung verändert; nichts entfernt.")
        DataKey.objects.filter(pk=key_id).update(
            wrapped="",
            retired_at=timezone.now(),
            retirement_reference=reference,
            retirement_checksum=checksum,
        )
        transaction.on_commit(crypto.reset)
    return True
