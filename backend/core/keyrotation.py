"""Wiederaufnehmbare Umstellung gespeicherter Daten auf eine neue Schlüsselgeneration.

Die Daten selbst sind der Fortschrittsnachweis: Jede Wiederaufnahme liest erneut
und überspringt nur authentifiziert lesbare Zielchiffrate. Phasen sind ausschließlich
Betriebsmetadaten. Schreibdienste müssen während des gesamten Laufs angehalten sein.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from django.apps import apps
from django.core.exceptions import SuspiciousFileOperation
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone

from core import crypto
from core.encfields import (
    EncryptedJSONField,
    EncryptedMixin,
    decrypt_text,
    encrypt_text_with_key,
    owner_org_id,
)
from core.management.commands.daten_verschluesseln import Command as FieldCommand
from core.management.commands.daten_verschluesseln import _stored, encrypted_fields
from core.models import DataKey, DataKeyRotation
from core.privatefiles import PrivateFileField, org_id_of
from organizations.models import Organization

BATCH = 200
LOCK_ID = 0x48554249524F5441


@contextmanager
def rotation_lock():
    # Eine Sitzung hält die Sperre auch über die kurzen Zeilentransaktionen hinweg.
    # Global statt je Verein: Dateiverweise können über Organisationsgrenzen gehen.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
        acquired = cursor.fetchone()[0]
    if not acquired:
        raise CommandError("Ein anderer Datenschlüsselwechsel läuft bereits.")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])


def rows(model):
    """Rohwerte ohne die toleranten ORM-Entschlüsselungs-Fallbacks lesen."""
    fields = list(model._meta.concrete_fields)
    quote = connection.ops.quote_name
    table, pk = quote(model._meta.db_table), quote(model._meta.pk.column)
    columns = ", ".join(quote(field.column) for field in fields)
    last = None
    while True:
        where, params = (f"WHERE {pk} > %s", [last]) if last is not None else ("", [])
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {columns} FROM {table} {where} ORDER BY {pk} LIMIT %s",  # noqa: S608
                [*params, BATCH],
            )
            batch = cursor.fetchall()
        if not batch:
            return
        for row in batch:
            data = dict(zip((f.attname for f in fields), row, strict=True))
            last = data[model._meta.pk.attname]
            yield data


def instance(model, data):
    # Eigentümerauflösung benötigt keine entschlüsselten Felder. Alle übrigen
    # Spalten sind gesetzt, damit auch relationale Dateieigentümer auflösbar sind.
    return model(
        **{
            field.attname: data[field.attname]
            for field in model._meta.concrete_fields
            if not isinstance(field, EncryptedMixin)
        }
    )


def cipher_key_id(value):
    if not isinstance(value, str) or not value.startswith("enc1:"):
        return None
    try:
        raw = base64.b64decode(value[5:], validate=True)
        if len(raw) < 36:
            raise ValueError
        return int.from_bytes(raw[:8], "big")
    except ValueError:
        raise CommandError("Beschädigtes Feldchiffrat; keine sichere Umstellung möglich.") from None


def file_key_id(path):
    with path.open("rb") as source:
        header = source.read(crypto.HEADER)
    if not crypto.is_encrypted_header(header):
        return None
    if len(header) != crypto.HEADER:
        raise CommandError("Abgeschnittener Dateikopf; keine sichere Umstellung möglich.")
    return int.from_bytes(header[8:16], "big")


def digest(source):
    result, size = hashlib.sha256(), 0
    while chunk := source.read(crypto.CHUNK):
        result.update(chunk)
        size += len(chunk)
    return result.digest(), size


class HashingReader:
    def __init__(self, source):
        self.source = source
        self.hash = hashlib.sha256()
        self.size = 0

    def read(self, size):
        value = self.source.read(size)
        self.hash.update(value)
        self.size += len(value)
        return value


def fingerprint(path):
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise CommandError("Private Datei ist keine reguläre Datei.")
    return info, (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Rotation:
    def __init__(self, owner_id, output):
        self.owner_id, self.output = owner_id, output
        self.org = Organization.objects.filter(pk=owner_id).first()
        if self.org is None or self.org.type == Organization.Type.UNIT:
            raise CommandError(
                "Eine vorhandene Plattform, einen Dachverband oder Verein "
                "als Schlüsselinhaber angeben."
            )
        from exchange.models import private_storage

        self.storage = private_storage()
        self.root = Path(self.storage.location).resolve()
        self.rotation = None
        self.target = None
        self.allowed_keys = set()
        self.stats = Counter()

    def key_state(self):
        self.key_owners = dict(DataKey.objects.values_list("pk", "organization_id"))
        state = list(
            DataKey.objects.filter(organization_id=self.owner_id)
            .order_by("pk")
            .values("pk", "wrapped", "is_active")
        )
        if sum(row["is_active"] for row in state) != 1:
            raise CommandError("Genau ein aktiver Datenschlüssel muss bereits vorhanden sein.")
        for row in state:
            try:
                raw = crypto.unwrap_key(row["wrapped"], crypto._context(self.owner_id))
                if len(raw) != 32:
                    raise ValueError
            except (crypto.DecryptionError, crypto.KeyUnavailable, ValueError):
                raise CommandError(
                    "Ein benötigter Datenschlüssel lässt sich nicht entpacken."
                ) from None
        crypto.reset()
        self.allowed_keys = {row["pk"] for row in state}
        return state

    def preflight(self):
        self.key_state()
        self.scan_database("preflight")
        self.scan_files("preflight")
        self.report("Vorprüfung erfolgreich")

    def latest(self):
        rotation = (
            DataKeyRotation.objects.filter(organization_id=self.owner_id).order_by("-pk").first()
        )
        if rotation is None:
            raise CommandError("Kein Wechsel vorhanden; nach Vorprüfung mit --starten beginnen.")
        return rotation

    def load(self, rotation):
        state = self.key_state()
        sources = rotation.source_key_ids
        if (
            not isinstance(sources, list)
            or not sources
            or any(type(pk) is not int or pk <= 0 for pk in sources)
        ):
            raise CommandError("Ungültiger Schlüsselwechsel-Auftrag.")
        if (
            self.allowed_keys != set(sources) | {rotation.target_key_id}
            or len(set(sources)) != len(sources)
            or rotation.target_key_id in sources
        ):
            raise CommandError("Schlüsselbestand hat sich seit Beginn des Wechsels verändert.")
        active = next(row["pk"] for row in state if row["is_active"])
        if active != rotation.target_key_id:
            raise CommandError("Die Zielgeneration des Wechsels ist nicht aktiv.")
        self.rotation = rotation
        self.target = (active, crypto.key_by_id(active))

    def start(self):
        if DataKeyRotation.objects.filter(
            organization_id=self.owner_id, completed_at__isnull=True
        ).exists():
            raise CommandError("Ein Wechsel ist offen; denselben Befehl ohne --starten fortsetzen.")
        state = self.key_state()
        self.scan_database("preflight")
        self.scan_files("preflight")
        key = crypto.AESGCM.generate_key(bit_length=256)
        wrapped = crypto.wrap_key(key, crypto._context(self.owner_id))
        if crypto.unwrap_key(wrapped, crypto._context(self.owner_id)) != key:
            raise CommandError("Die neue Schlüsselverpackung ist nicht lesbar.")
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=self.owner_id)
            current = list(
                DataKey.objects.select_for_update()
                .filter(organization_id=self.owner_id)
                .order_by("pk")
                .values("pk", "wrapped", "is_active")
            )
            if current != state:
                raise CommandError("Schlüsselbestand wurde während der Vorprüfung verändert.")
            DataKey.objects.filter(organization_id=self.owner_id, is_active=True).update(
                is_active=False
            )
            target = DataKey.objects.create(organization_id=self.owner_id, wrapped=wrapped)
            rotation = DataKeyRotation.objects.create(
                organization_id=self.owner_id,
                target_key=target,
                source_key_ids=[row["pk"] for row in state],
            )
        self.output.write(f"Schlüsselwechsel {rotation.pk}: Zielgeneration {target.pk} aktiviert.")
        self.load(rotation)

    def run(self, *, start=False):
        if start:
            self.start()
        else:
            self.load(self.latest())
            if self.rotation.completed_at is not None:
                self.verify()
                self.report("Bereits abgeschlossen; erneut geprüft")
                return
            # Wiederaufnahme prüft den tatsächlichen Mischbestand statt einer
            # gespeicherten letzten Zeilennummer oder einer übersprungenen Phase.
            self.scan_database("preflight")
            self.scan_files("preflight")
        self.cleanup_temporary()
        for phase, action in (
            ("database", self.scan_database),
            ("files", self.scan_files),
            ("marks", self.scan_marks),
        ):
            DataKeyRotation.objects.filter(pk=self.rotation.pk).update(phase=phase)
            action("rewrite")
        self.cleanup_temporary()
        DataKeyRotation.objects.filter(pk=self.rotation.pk).update(phase="verification")
        self.verify()
        DataKeyRotation.objects.filter(pk=self.rotation.pk).update(
            phase="completed", completed_at=timezone.now()
        )
        self.report("Schlüsselwechsel vollständig abgeschlossen")

    def verify_latest(self):
        self.load(self.latest())
        self.verify()
        self.report("Abschlussprüfung erfolgreich")

    def verify(self):
        self.scan_database("verify")
        self.scan_files("verify")
        self.scan_marks("verify")
        # Nach dem Lesen noch einmal gegen nicht kooperierende Verwaltungsänderungen
        # prüfen; die Schreibpause bleibt eine betriebliche Voraussetzung.
        self.load(self.rotation)

    def scan_database(self, mode):
        for model, fields in encrypted_fields():
            for data in rows(model):
                owner = owner_org_id(instance(model, data))
                selected = owner is not None and crypto.key_owner_id(owner) == self.owner_id
                updates = {}
                for field in fields:
                    try:
                        encrypted, value = _stored(field, data[field.attname])
                        if not encrypted:
                            if selected and not field._stays_plain(value):
                                raise CommandError(
                                    "Unverschlüsselter Feldbestand: zuerst "
                                    "daten_verschluesseln ausführen und prüfen."
                                )
                            continue
                        try:
                            key_id = cipher_key_id(value)
                        except CommandError:
                            if selected:
                                raise
                            continue
                        if not selected:
                            if key_id in self.allowed_keys:
                                raise CommandError(
                                    "Schlüsselverweis in einem fremden Datenbereich gefunden."
                                )
                            continue
                        if key_id not in self.allowed_keys:
                            raise CommandError(
                                "Feld verweist auf einen fehlenden oder fremden Datenschlüssel."
                            )
                        text = decrypt_text(value, field)
                        # Auch Datum und JSON validieren, nicht nur das GCM-Tag.
                        field._text_to_plain(text)
                        self.stats[f"{mode}_fields"] += 1
                        if mode == "verify" and key_id != self.target[0]:
                            raise CommandError(
                                "Aktuelle Daten benötigen noch eine alte Schlüsselgeneration."
                            )
                        if mode == "rewrite" and key_id != self.target[0]:
                            cipher = encrypt_text_with_key(text, field, *self.target)
                            updates[field] = (
                                {field.KEY: cipher}
                                if isinstance(field, EncryptedJSONField)
                                else cipher
                            )
                    except (crypto.DecryptionError, ValueError, TypeError, UnicodeError):
                        raise CommandError(
                            f"Feldbestand in {model._meta.label}.{field.name} ist nicht lesbar."
                        ) from None
                if updates:
                    quote = connection.ops.quote_name
                    expected = {f.column: data[f.attname] for f in model._meta.concrete_fields}
                    if not FieldCommand._write(
                        quote(model._meta.db_table),
                        quote(model._meta.pk.column),
                        data[model._meta.pk.attname],
                        updates,
                        expected=expected,
                    ):
                        raise CommandError(
                            "Datensatz während der Umstellung verändert; "
                            "Schreibpause prüfen und fortsetzen."
                        )
                    self.stats["changed_fields"] += len(updates)

    def platform_id(self):
        pk = (
            Organization.objects.filter(type=Organization.Type.PLATFORM)
            .values_list("pk", flat=True)
            .first()
        )
        if pk is None:
            raise CommandError("Plattform als Schlüsselinhaber fehlt.")
        return pk

    def safe_path(self, storage, name):
        try:
            path = Path(storage.path(name))
            relative = path.relative_to(self.root)
            if ".." in relative.parts or any(
                parent.is_symlink()
                for parent in (path, *path.parents)
                if parent != self.root and self.root in parent.parents
            ):
                raise ValueError
            path.resolve().relative_to(self.root)
            return path
        except (ValueError, OSError, SuspiciousFileOperation):
            raise CommandError("Unsicherer oder nicht lokaler privater Dateipfad.") from None

    def file_references(self):
        references = {}

        def add(storage, name, owner, *, authoritative=True):
            if not name:
                return
            path = self.safe_path(storage, name)
            owners, required = references.setdefault(path, (set(), set()))
            owner_id = crypto.key_owner_id(owner if owner is not None else self.platform_id())
            required.add(owner_id)
            if authoritative:
                owners.add(owner_id)

        for model in apps.get_models():
            if model._meta.proxy:
                continue
            fields = [
                field
                for field in model._meta.concrete_fields
                if isinstance(field, PrivateFileField)
            ]
            if not fields:
                continue
            for data in rows(model):
                obj = instance(model, data)
                for field in fields:
                    if data[field.attname]:
                        add(field.storage, data[field.attname], org_id_of(obj))
        from outbox.models import OutgoingMail

        for data in rows(OutgoingMail):
            items = data["attachments"]
            items = json.loads(items) if isinstance(items, str) else items
            if not isinstance(items, list):
                raise CommandError("Ungültige Dateiverweise im Postausgang.")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("path", ""), str):
                    raise CommandError("Ungültiger Dateiverweis im Postausgang.")
                name = item.get("path", "")
                add(
                    self.storage,
                    name,
                    owner_org_id(instance(OutgoingMail, data)),
                    authoritative=name.startswith("outbox/"),
                )
        return references

    def staging_path(self, rotation):
        return self.root / f".datenschluesselwechsel-{rotation.token.hex}"

    def inventory(self):
        references = self.file_references()
        if not self.root.exists():
            if any(self.owner_id in required for _, required in references.values()):
                raise CommandError("Mindestens eine benötigte private Datei fehlt.")
            return
        staging = {self.staging_path(r): r for r in DataKeyRotation.objects.all()}
        for path in references:
            if any(stage == path or stage in path.parents for stage in staging):
                raise CommandError(
                    "Nutzdatei verweist auf den temporären Schlüsselwechsel-Bereich."
                )

        def unreadable(_error):
            raise CommandError("Privater Dateiordner ist nicht vollständig lesbar.")

        for directory, dirs, files in os.walk(self.root, followlinks=False, onerror=unreadable):
            parent = Path(directory)
            for name in list(dirs):
                path = parent / name
                if path.is_symlink():
                    raise CommandError(
                        "Symbolischer Link im privaten Dateibestand; Prüfung nicht eindeutig."
                    )
                if path in staging:
                    rotation = staging[path]
                    if (
                        rotation.organization_id == self.owner_id
                        and rotation.completed_at
                        and any(path.iterdir())
                    ):
                        raise CommandError(
                            "Temporäre Dateien eines abgeschlossenen Wechsels sind noch vorhanden."
                        )
                    dirs.remove(name)
            for name in sorted(files):
                path = parent / name
                if path.is_symlink():
                    raise CommandError(
                        "Symbolischer Link im privaten Dateibestand; Prüfung nicht eindeutig."
                    )
                owners, required = references.pop(path, (set(), set()))
                yield path, owners, required
        if any(self.owner_id in required for _, required in references.values()):
            raise CommandError("Mindestens eine benötigte private Datei fehlt.")

    def scan_files(self, mode):
        try:
            for path, owners, required in self.inventory():
                info, _ = fingerprint(path)
                key_id = file_key_id(path)
                key_owner = self.key_owners.get(key_id)
                selected = self.owner_id in owners or key_owner == self.owner_id
                needed = selected or self.owner_id in required
                if not needed:
                    continue
                if key_id is None:
                    raise CommandError(
                        "Unverschlüsselte private Datei: zuerst "
                        "dateien_verschluesseln ausführen und prüfen."
                    )
                if owners and owners != {key_owner}:
                    raise CommandError(
                        "Private Datei und Dateiverweise gehören zu "
                        "unterschiedlichen Schlüsselinhabern."
                    )
                if selected and key_id not in self.allowed_keys:
                    raise CommandError(
                        "Private Datei verweist auf einen fehlenden oder fremden Datenschlüssel."
                    )
                if self.root.stat().st_dev != info.st_dev:
                    raise CommandError(
                        "Private Dateien müssen für atomaren Austausch "
                        "im selben Dateisystem liegen."
                    )
                if selected and mode == "verify" and key_id != self.target[0]:
                    raise CommandError(
                        "Eine private Datei benötigt noch eine alte Schlüsselgeneration."
                    )
                if selected and mode == "rewrite" and key_id != self.target[0]:
                    self.rewrite_file(path)
                    self.stats["changed_files"] += 1
                else:
                    with path.open("rb") as raw, crypto.open_plain(raw) as source:
                        digest(source)
                self.stats[f"{mode}_files"] += 1
        except (crypto.DecryptionError, OSError, ValueError):
            raise CommandError("Privater Dateibestand ist nicht vollständig lesbar.") from None

    def temporary_directory(self):
        path = self.staging_path(self.rotation)
        if path.is_symlink():
            raise CommandError("Unsicherer temporärer Schlüsselwechsel-Bereich.")
        path.mkdir(mode=0o700, exist_ok=True)
        return path

    def cleanup_temporary(self):
        path = self.staging_path(self.rotation)
        if not path.exists() and not path.is_symlink():
            return
        if path.is_symlink() or not path.is_dir():
            raise CommandError("Unsicherer temporärer Schlüsselwechsel-Bereich.")
        for entry in path.iterdir():
            if (
                not re.fullmatch(r"[0-9a-f]{32}\.part", entry.name)
                or entry.is_symlink()
                or not entry.is_file()
            ):
                raise CommandError("Unbekannter Inhalt im temporären Schlüsselwechsel-Bereich.")
            entry.unlink()
        path.rmdir()
        sync_directory(self.root)

    def rewrite_file(self, path):
        info, before = fingerprint(path)
        directory = self.temporary_directory()
        temporary = directory / f"{uuid.uuid4().hex}.part"
        try:
            with (
                path.open("rb") as raw,
                crypto.open_plain(raw) as source,
                temporary.open("xb") as target,
            ):
                reader = HashingReader(source)
                for chunk in crypto.encrypt_chunks(reader, *self.target):
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            with temporary.open("rb") as raw, crypto.open_plain(raw) as source:
                if digest(source) != (reader.hash.digest(), reader.size):
                    raise CommandError(
                        "Neu verschlüsselte Datei stimmt nicht mit dem "
                        "ursprünglichen Inhalt überein."
                    )
            if fingerprint(path)[1] != before:
                raise CommandError(
                    "Private Datei während der Umstellung verändert; Schreibpause prüfen."
                )
            os.chmod(temporary, stat.S_IMODE(info.st_mode))
            os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns))
            os.replace(temporary, path)
            sync_directory(path.parent)
            sync_directory(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def scan_marks(self, mode):
        from members.models import Person
        from members.personmarks import DERIVED_FIELDS, values

        scopes = [
            pk
            for pk in Organization.objects.values_list("pk", flat=True)
            if crypto.key_owner_id(pk) == self.owner_id
        ]
        qs = Person.objects.filter(scope_id__in=scopes).order_by("pk")
        last = 0
        while ids := list(qs.filter(pk__gt=last).values_list("pk", flat=True)[:BATCH]):
            last = ids[-1]
            for pk in ids:
                with transaction.atomic():
                    try:
                        person = qs.select_for_update().filter(pk=pk).first()
                    except crypto.DecryptionError:
                        raise CommandError(
                            "Personenbestand ist nicht vollständig lesbar."
                        ) from None
                    if person is None:
                        raise CommandError(
                            "Person während der Umstellung entfernt; Schreibpause prüfen."
                        )
                    try:
                        expected = values(person, create_key=False)
                    except (crypto.DecryptionError, ValueError):
                        raise CommandError(
                            "Personensuchmarken können nicht vollständig geprüft werden."
                        ) from None
                    if expected["marks_key_id"] != self.target[0]:
                        raise CommandError(
                            "Aktiver Datenschlüssel während der Markenberechnung verändert."
                        )
                    if any(getattr(person, field) != expected[field] for field in DERIVED_FIELDS):
                        if mode == "verify":
                            raise CommandError(
                                "Personensuchmarken sind noch nicht vollständig umgestellt."
                            )
                        columns = ", ".join(f'"{field}" = %s' for field in expected)
                        with connection.cursor() as cursor:
                            cursor.execute(
                                f"UPDATE members_person SET {columns} WHERE id = %s",  # noqa: S608
                                [*expected.values(), pk],
                            )
                        self.stats["changed_marks"] += 1
                    self.stats[f"{mode}_marks"] += 1

    def report(self, title):
        self.output.write(
            f"{title}. Geprüfte Felder: "
            f"{self.stats['verify_fields'] or self.stats['preflight_fields']}; "
            f"Dateien: {self.stats['verify_files'] or self.stats['preflight_files']}; "
            f"umgestellt: {self.stats['changed_fields']} Felder, "
            f"{self.stats['changed_files']} Dateien, "
            f"{self.stats['changed_marks']} Personenmarken. Alte Schlüssel bleiben erhalten."
        )
