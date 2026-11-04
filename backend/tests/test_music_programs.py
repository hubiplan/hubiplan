"""Einzelprogramme erben Vorlagen, bleiben verschiebbar und geben nur passende Noten frei."""
# ruff: noqa: F811

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.tenancy import tenant_context
from datatransfer.tables import IdMap, dump_rows, load_tables
from documents.models import Document, DocumentVersion, Folder
from events.models import Event, EventException
from music.models import (
    Arrangement,
    Piece,
    Rehearsal,
    RehearsalProgram,
    RehearsalProgramItem,
    ScoreDocument,
)

from .factories import give_role, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_practice import practice  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


def url(club, practice):
    return f"/api/orgs/{club.pk}/music/rehearsals/{practice[4].rehearsal_id}/program/"


def change(
    c, club, practice, *, scope="occurrence", original=None, focus="Einzelprobe", items=None
):
    return c.post(
        url(club, practice),
        {
            "scope": scope,
            "original_start": (original or practice[3].starts_at).isoformat(),
            "focus": focus,
            "items": items if items is not None else [],
        },
        content_type=JSON,
    )


def rows(c, club):
    return c.get(f"/api/orgs/{club.pk}/music/practice/").json()


def test_inherit_override_series_edit_and_reset(c, club, practice):
    original = practice[3].starts_at
    first, second = rows(c, club)[:2]
    assert first["focus"] == second["focus"] == "Rhythmus"
    assert not first["overridden"]
    items = [{"arrangement": practice[5].arrangement_id, "focus": "Takte 9 bis 16"}]
    assert change(c, club, practice, items=items).status_code == 200
    first, second = rows(c, club)[:2]
    assert first["focus"] == "Einzelprobe" and first["items"][0]["focus"] == "Takte 9 bis 16"
    assert first["overridden"] and second["focus"] == "Rhythmus"
    # Dieselbe fachliche Anfrage ist auch bei Wiederholung kein zweites Programm.
    assert change(c, club, practice, items=items).status_code == 200
    with tenant_context(club.pk):
        assert RehearsalProgram.objects.count() == 1
        assert RehearsalProgramItem.objects.count() == 1
    assert change(c, club, practice, scope="series", focus="Neue Vorlage").status_code == 200
    first, second = rows(c, club)[:2]
    assert first["focus"] == "Einzelprobe" and first["items"]
    assert second["focus"] == "Neue Vorlage" and second["items"] == []
    response = c.get(url(club, practice), {"original_start": original.isoformat()}).json()
    assert response["template"] == {"focus": "Neue Vorlage", "items": []}
    assert change(c, club, practice, scope="inherit").json()["overridden"] is False
    assert rows(c, club)[0]["focus"] == "Neue Vorlage"


def test_empty_override_and_member_response_survive_series_edit(api, c, club, practice):
    user, access, _, event, invite, part = practice
    portal = f"/api/portal/{access.pk}/music/practice/"
    client = api(user)
    assert (
        client.post(
            portal,
            {
                "id": invite.pk,
                "original_start": event.starts_at.isoformat(),
                "status": "accepted",
            },
            content_type=JSON,
        ).status_code
        == 200
    )
    assert change(c, club, practice, focus="", items=[]).status_code == 200
    items = [{"arrangement": part.arrangement_id, "focus": "Neue Takte"}]
    assert (
        change(c, club, practice, scope="series", focus="Vorlage", items=items).status_code == 200
    )
    first, second = client.get(portal).json()["rehearsals"][:2]
    assert first["items"] == [] and first["focus"] == "" and first["overridden"]
    assert first["status"] == "accepted" and second["status"] == "pending"
    assert second["items"][0]["focus"] == "Neue Takte"


def test_moved_occurrence_keeps_program_by_original_start(c, club, practice):
    event = practice[3]
    assert change(c, club, practice).status_code == 200
    with tenant_context(club.pk):
        EventException.objects.create(
            organization=club,
            event=event,
            original_start=event.starts_at,
            starts_at=event.starts_at + datetime.timedelta(hours=2),
            ends_at=event.ends_at + datetime.timedelta(hours=2),
        )
    first = rows(c, club)[0]
    assert first["focus"] == "Einzelprobe" and first["overridden"]
    assert first["starts_at"] != first["original_start"]
    # Derselbe Zeitpunkt mit anderem Offset überschreibt dieselbe Abweichung.
    local = event.starts_at.astimezone(datetime.timezone(datetime.timedelta(hours=1)))
    assert change(c, club, practice, original=local, focus="Verschoben").status_code == 200
    with tenant_context(club.pk):
        assert RehearsalProgram.objects.count() == 1
        event.starts_at += datetime.timedelta(hours=1)
        event.ends_at += datetime.timedelta(hours=1)
        event.save()
    # Nach einer neuen Serienregel wird das alte Programm keinem anderen Termin angeheftet.
    assert all(not r["overridden"] for r in rows(c, club))
    assert c.get(url(club, practice), {"original_start": local.isoformat()}).status_code == 400


def test_scope_validation_permissions_and_foreign_arrangement(api, c, club, orgs, practice):
    user = make_user("probenlesen@example.org")
    role = give_role(user, club, permissions=["music.view", "events.view"], name="Proben lesen")
    client = api(user)
    assert (
        client.get(
            url(club, practice), {"original_start": practice[3].starts_at.isoformat()}
        ).status_code
        == 200
    )
    assert change(client, club, practice).status_code == 403
    with tenant_context(orgs["b"].pk):
        piece = Piece.objects.create(organization=orgs["b"], title="Fremd")
        arrangement = Arrangement.objects.create(organization=orgs["b"], piece=piece, name="Fremd")
    assert (
        change(
            c, club, practice, scope="series", items=[{"arrangement": arrangement.pk, "focus": ""}]
        ).status_code
        == 404
    )
    assert rows(c, club)[0]["focus"] == "Rhythmus"  # Auch die Vorlage bleibt unverändert.
    assert change(c, club, practice, scope="unknown").status_code == 400
    assert (
        change(
            c, club, practice, original=practice[3].starts_at + datetime.timedelta(minutes=1)
        ).status_code
        == 400
    )
    assert (
        change(c, club, practice, items=[{"arrangement": 1, "focus": "x" * 501}]).status_code == 400
    )
    with tenant_context(club.pk):
        event = practice[3]
        event.visibility = "board"
        event.save()
    role.role.is_board = False
    role.role.save()
    assert (
        client.get(url(club, practice), {"original_start": event.starts_at.isoformat()}).status_code
        == 404
    )
    club.enabled_modules.remove("music")
    club.save()
    assert change(c, club, practice).status_code == 404


def test_personal_notes_follow_effective_program_and_live_permissions(
    api, c, club, practice, settings, tmp_path
):
    settings.PRIVATE_ROOT = tmp_path
    user, access, _, event, _, part = practice
    with tenant_context(club.pk):
        piece = Piece.objects.create(organization=club, title="Anderes Musterlied")
        arrangement = Arrangement.objects.create(
            organization=club, piece=piece, name="Andere Fassung"
        )
        folder = Folder.objects.create(
            organization=club, name="Noten", visibility="members", public_key=Folder.new_key()
        )
        links = []
        for arr in (part.arrangement, arrangement):
            document = Document.objects.create(organization=club, folder=folder, title=arr.name)
            DocumentVersion.objects.create(
                organization=club,
                document=document,
                name="noten.txt",
                content_type="text/plain",
                file=SimpleUploadedFile("noten.txt", b"Nur synthetische Noten"),
            )
            links.append(
                ScoreDocument.objects.create(organization=club, arrangement=arr, document=document)
            )
    assert (
        change(
            c, club, practice, items=[{"arrangement": arrangement.pk, "focus": "Solo"}]
        ).status_code
        == 200
    )
    client = api(user)
    portal = f"/api/portal/{access.pk}/music/practice/"
    result = client.get(portal).json()
    first, second = result["rehearsals"][:2]
    assert first["items"][0]["title"] == "Anderes Musterlied"
    assert [s["id"] for s in first["scores"]] == [links[1].pk]
    assert [s["id"] for s in second["scores"]] == [links[0].pk]
    download = f"/api/portal/{access.pk}/music/files/{links[1].pk}/"
    response = client.get(download)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"Nur synthetische Noten"
    # Entfernen des einzigen relevanten Einzelprogramms widerruft auch den Direktlink.
    assert change(c, club, practice, focus="Nur Rhythmus").status_code == 200
    assert client.get(download).status_code == 404
    assert (
        change(
            c, club, practice, items=[{"arrangement": arrangement.pk, "focus": "Solo"}]
        ).status_code
        == 200
    )
    with tenant_context(club.pk):
        folder.visibility = "board"
        folder.save()
    assert client.get(download).status_code == 404
    assert all(r["scores"] == [] for r in client.get(portal).json()["rehearsals"])
    with tenant_context(club.pk):
        folder.visibility = "members"
        folder.save()
        EventException.objects.create(
            organization=club, event=event, original_start=event.starts_at, is_cancelled=True
        )
    assert client.get(portal).json()["rehearsals"][0]["scores"] == []
    assert client.get(download).status_code == 404


def test_program_data_roundtrip_and_rls(c, club, orgs, practice):
    items = [
        {"arrangement": practice[5].arrangement_id, "focus": "Teil A"},
        {"arrangement": practice[5].arrangement_id, "focus": "Teil B"},
    ]
    assert change(c, club, practice, items=items).status_code == 200
    with tenant_context(club.pk):
        tables = {
            model._meta.label_lower: dump_rows(model, club, None)
            for model in (RehearsalProgram, RehearsalProgramItem)
        }
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not RehearsalProgram.objects.exists()
        assert not RehearsalProgramItem.objects.exists()
    with tenant_context(orgs["b"].pk):
        event = Event.objects.create(
            organization=orgs["b"],
            title="Importprobe",
            starts_at=practice[3].starts_at,
            ends_at=practice[3].ends_at,
        )
        rehearsal = Rehearsal.objects.create(organization=orgs["b"], event=event)
        piece = Piece.objects.create(organization=orgs["b"], title="Importlied")
        arrangement = Arrangement.objects.create(
            organization=orgs["b"], piece=piece, name="Importfassung"
        )
        ids = IdMap()
        ids.set("music.rehearsal", practice[4].rehearsal_id, rehearsal.pk)
        ids.set("music.arrangement", practice[5].arrangement_id, arrangement.pk)
        assert load_tables(tables, orgs["b"], ids, None) == 3
        program = RehearsalProgram.objects.get(organization=orgs["b"])
        assert program.rehearsal_id == rehearsal.pk and program.focus == "Einzelprobe"
        assert list(program.items.values_list("focus", flat=True)) == ["Teil A", "Teil B"]
        assert set(program.items.values_list("arrangement_id", flat=True)) == {arrangement.pk}
