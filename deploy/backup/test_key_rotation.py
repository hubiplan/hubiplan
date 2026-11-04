"""Lokale synthetische Rotations-/Wiederherstellungsprobe, nicht im Betriebsimage."""
# ruff: noqa: S101

import datetime
import hashlib
import io
import json
import os
import resource
import sys
import time
from pathlib import Path
from unittest.mock import patch


def main():
    sys.path.insert(0, os.getcwd())
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django

    django.setup()
    from django.core.files.base import ContentFile
    from django.core.management import call_command

    from core import crypto
    from core.keyrotation import Rotation, file_key_id
    from core.models import DataKey, DataKeyRotation
    from core.tenancy import rls_bypass
    from exchange.models import ImportJob
    from members.models import Person
    from members.personmarks import values
    from organizations.models import Organization
    from todos.models import Todo

    mode = sys.argv[1]
    with rls_bypass():
        if mode == "seed":
            org = Organization.objects.create(
                name="Rotations-Testverein", type="club", parent=Organization.platform()
            )
            other = Organization.objects.create(
                name="Fremder Testverein", type="club", parent=Organization.platform()
            )
            Person.objects.bulk_create(
                [
                    Person(
                        scope=scope,
                        first_name=f"Testvorname {i}",
                        last_name=f"Testname {i}",
                        birth_date=datetime.date(1980, 5, 17),
                    )
                    for scope, count in ((org, 2000), (other, 200))
                    for i in range(count)
                ]
            )
            Todo.objects.bulk_create(
                [
                    Todo(
                        organization=org,
                        title=f"Testaufgabe {i}",
                        description="Synthetischer Inhalt",
                    )
                    for i in range(1000)
                ]
            )
            # Ein 72-MiB-Nutzinhalt ohne entsprechend große Klartextdatei im Dateisystem.
            job = ImportJob(organization=org, file_name="gross.bin")
            job.file.save("gross.bin", ContentFile(b"Testdatei" * (8 * 1024 * 1024)), save=False)
            job.save()
            for i in range(20):
                item = ImportJob(
                    organization=org, file_name=f"klein-{i}.bin", preview=[{"test": "x" * 100000}]
                )
                item.file.save(
                    item.file_name, ContentFile(f"Synthetische Datei {i}".encode()), save=False
                )
                item.save()
            print(
                "Rotationsbestand: 2000 eigene und 200 fremde Personen, "
                "1000 Aufgaben, 21 Dateien, 72 MiB Großdatei"
            )
            return
        org = Organization.objects.get(name="Rotations-Testverein")
        if mode in {"interrupt", "finish", "benchmark"}:
            started = time.perf_counter()
            if mode == "interrupt":
                original = Rotation.rewrite_file

                def stop(self, path):
                    original(self, path)
                    raise RuntimeError("Geplanter lokaler Testabbruch nach erster Datei")

                with patch.object(Rotation, "rewrite_file", stop):
                    try:
                        call_command(
                            "datenschluessel_wechseln",
                            organisation=org.pk,
                            starten=True,
                            schreiber_angehalten=True,
                            stdout=io.StringIO(),
                        )
                    except RuntimeError:
                        pass
                rotation = DataKeyRotation.objects.get(organization=org)
                assert rotation.completed_at is None
                p = Person.objects.filter(scope=org).first()
                assert p.marks_version == 0
                keys = {
                    file_key_id(Path(job.file.path))
                    for job in ImportJob.objects.filter(organization=org)
                }
                assert rotation.target_key_id in keys and keys & set(rotation.source_key_ids)
            else:
                call_command(
                    "datenschluessel_wechseln",
                    organisation=org.pk,
                    starten=mode == "benchmark",
                    schreiber_angehalten=True,
                    stdout=io.StringIO(),
                )
            print(
                "Schlüsselwechsel-Messung "
                + json.dumps(
                    {
                        "phase": mode,
                        "seconds": round(time.perf_counter() - started, 3),
                        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    }
                )
            )
            return
        people = list(
            Person.objects.order_by("pk").values_list(
                "scope_id", "first_name", "last_name", "birth_date"
            )
        )
        tasks = list(Todo.objects.order_by("pk").values_list("title", "description"))
        files = []
        for job in ImportJob.objects.order_by("pk"):
            result = hashlib.sha256()
            with job.file.open("rb") as handle:
                while chunk := handle.read(crypto.CHUNK):
                    result.update(chunk)
            files.append(result.hexdigest())
        fingerprint = hashlib.sha256(
            json.dumps([people, tasks, files], default=str).encode()
        ).hexdigest()
        if mode.startswith("restore-"):
            stage = mode.removeprefix("restore-")
            if stage == "before":
                assert not DataKeyRotation.objects.exists()
                call_command(
                    "datenschluessel_wechseln",
                    organisation=org.pk,
                    starten=True,
                    schreiber_angehalten=True,
                    stdout=io.StringIO(),
                )
            elif stage == "during":
                rotation = DataKeyRotation.objects.get(organization=org)
                assert rotation.completed_at is None
                target = rotation.target_key_id
                count = DataKey.objects.filter(organization=org).count()
                call_command(
                    "datenschluessel_wechseln",
                    organisation=org.pk,
                    schreiber_angehalten=True,
                    stdout=io.StringIO(),
                )
                rotation.refresh_from_db()
                assert rotation.target_key_id == target and rotation.completed_at
                assert DataKey.objects.filter(organization=org).count() == count
            else:
                assert DataKeyRotation.objects.get(organization=org).completed_at
            call_command(
                "datenschluessel_wechseln", organisation=org.pk, pruefen=True, stdout=io.StringIO()
            )
            for p in Person.objects.filter(scope=org):
                assert values(p, create_key=False)["marks_key_id"] == p.marks_key_id
            # Nach Wiederaufnahme müssen auch Inhalte unverändert lesbar sein.
            assert (
                list(
                    Person.objects.order_by("pk").values_list(
                        "scope_id", "first_name", "last_name", "birth_date"
                    )
                )
                == people
            )
            assert list(Todo.objects.order_by("pk").values_list("title", "description")) == tasks
            for job, expected in zip(ImportJob.objects.order_by("pk"), files, strict=True):
                result = hashlib.sha256()
                with job.file.open("rb") as handle:
                    while chunk := handle.read(crypto.CHUNK):
                        result.update(chunk)
                assert result.hexdigest() == expected
        print(fingerprint)


if __name__ == "__main__":
    main()
