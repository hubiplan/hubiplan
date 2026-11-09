"""Notenmappen: Marschbuch/Repertoire, Mappen je Termin und Fassungskennung für die App."""
# ruff: noqa: F811

import datetime

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from core.tenancy import tenant_context
from documents.models import Document, DocumentVersion, Folder
from music.models import (
    Arrangement,
    Assignment,
    Musician,
    Performance,
    Piece,
    Position,
    ProgramEntry,
    ScoreDocument,
    ScoreFolder,
    ScoreFolderItem,
    ScorePart,
    Skill,
)
from organizations.models import Department
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n%Musterseite\n"


def _arrangement(club, title, composer=""):
    piece = Piece.objects.create(organization=club, title=title, composer=composer)
    return Arrangement.objects.create(
        organization=club, piece=piece, name=f"{title} (Blasorchester)"
    )


def _score(club, folder, arrangement, instrument, title):
    part = ScorePart.objects.create(
        organization=club, arrangement=arrangement, instrument=instrument, paper_format="march"
    )
    document = Document.objects.create(organization=club, folder=folder, title=title)
    version = DocumentVersion.objects.create(
        organization=club,
        document=document,
        name=f"{title}.pdf",
        size=len(PDF),
        content_type="application/pdf",
        file=ContentFile(PDF, name=f"{title}.pdf"),
    )
    link = ScoreDocument.objects.create(
        organization=club, arrangement=arrangement, part=part, document=document
    )
    return link, version


@pytest.fixture
def setup(club, music):
    user = make_user("tenorhorn@example.org")
    member = make_member(club, "Toni", "Beispiel")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
        musician = Musician.objects.create(organization=club, membership=member)
        Skill.objects.create(organization=club, musician=musician, instrument="Tenorhorn")
        docs = Folder.objects.create(
            organization=club, name="Noten", visibility="members", public_key=Folder.new_key()
        )
        alte = _arrangement(club, "Alte Kameraden", "Carl Teike")
        florentiner = _arrangement(club, "Florentiner Marsch", "Julius Fučík")
        own, version = _score(club, docs, alte, "Tenorhorn", "Alte Kameraden Tenorhorn")
        _score(club, docs, alte, "Flöte", "Alte Kameraden Flöte")
        own2, _ = _score(club, docs, florentiner, "Tenorhorn", "Florentiner Tenorhorn")
        book = ScoreFolder.objects.create(organization=club, name="Marschbuch", kind="marchbook")
        ScoreFolderItem.objects.create(
            organization=club, folder=book, arrangement=florentiner, position=1, number="12"
        )
        ScoreFolderItem.objects.create(
            organization=club, folder=book, arrangement=alte, position=2, number="27"
        )
    return {
        "user": user,
        "access": access,
        "musician": musician,
        "book": book,
        "own": own,
        "own2": own2,
        "version": version,
        "alte": alte,
        "member": member,
    }


def test_marchbook_lists_own_voice_in_order(api, setup):
    client = api(setup["user"])
    data = client.get(f"/api/portal/{setup['access'].pk}/music/folders/").json()
    [book] = data["folders"]
    assert book["kind"] == "marchbook"
    assert [(i["number"], i["title"]) for i in book["items"]] == [
        ("12", "Florentiner Marsch"),
        ("27", "Alte Kameraden"),
    ]
    scores = book["items"][1]["scores"]
    assert [s["id"] for s in scores] == [setup["own"].pk]
    assert scores[0]["version"] == setup["version"].pk
    assert scores[0]["paper_format"] == "march"
    assert book["items"][1]["composer"] == "Carl Teike"
    # Dateien aus Mappen sind auch über den bestehenden Notenabruf erreichbar
    url = scores[0]["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert response["ETag"] == f'"v{setup["version"].pk}"'
    assert client.get(url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code == 304
    practice = client.get(f"/api/portal/{setup['access'].pk}/music/practice/").json()
    assert {s["id"] for s in practice["scores"]} == {setup["own"].pk, setup["own2"].pk}


def test_folder_limited_to_units(api, club, setup):
    client = api(setup["user"])
    url = f"/api/portal/{setup['access'].pk}/music/folders/"
    with tenant_context(club.pk):
        zug = Department.objects.create(organization=club, name="Spielmannszug")
        unter = Department.objects.create(organization=club, name="Trommler", parent=zug)
        setup["book"].units.create(organization=club, department=zug)
    assert client.get(url).json()["folders"] == []
    file_url = f"/api/portal/{setup['access'].pk}/music/files/{setup['own'].pk}/"
    assert client.get(file_url).status_code == 404
    other = make_member(club, "Uli", "Beispiel", departments=[unter])
    other_user = make_user("trommel@example.org")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(organization=club, membership=other, user=other_user)
        musician = Musician.objects.create(organization=club, membership=other)
        Skill.objects.create(organization=club, musician=musician, instrument="Tenorhorn")
    rows = api(other_user).get(f"/api/portal/{access.pk}/music/folders/").json()["folders"]
    assert [f["name"] for f in rows] == ["Marschbuch"]


def test_inactive_folder_member_folder_and_module(api, club, setup):
    client = api(setup["user"])
    url = f"/api/portal/{setup['access'].pk}/music/folders/"
    with tenant_context(club.pk):
        Folder.objects.filter(organization=club).update(visibility="board")
    [book] = client.get(url).json()["folders"]
    assert all(i["scores"] == [] for i in book["items"])
    with tenant_context(club.pk):
        setup["book"].active = False
        setup["book"].save()
    assert client.get(url).json()["folders"] == []
    club.enabled_modules = [m for m in club.enabled_modules if m != "scores"]
    club.save()
    assert client.get(url).json()["folders"] == []


def test_performance_folder_in_program_order(api, club, setup, music):
    _, event = music
    with tenant_context(club.pk):
        event.starts_at = timezone.now() + datetime.timedelta(days=3)
        event.ends_at = event.starts_at + datetime.timedelta(hours=2)
        event.save()
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tenorhorn"
        )
        Assignment.objects.create(
            organization=club,
            performance=performance,
            position=position,
            musician=setup["musician"],
            status="accepted",
        )
        ProgramEntry.objects.create(
            organization=club, performance=performance, arrangement=setup["alte"], position=1
        )
        ProgramEntry.objects.create(
            organization=club, performance=performance, kind="pause", position=2
        )
    data = api(setup["user"]).get(f"/api/portal/{setup['access'].pk}/music/folders/").json()
    [row] = [e for e in data["events"] if e["type"] == "performance"]
    assert row["key"] == f"performance-{performance.pk}"
    assert [i["kind"] for i in row["items"]] == ["piece", "pause"]
    assert [s["id"] for s in row["items"][0]["scores"]] == [setup["own"].pk]
    with tenant_context(club.pk):
        event.is_cancelled = True
        event.save()
    data = api(setup["user"]).get(f"/api/portal/{setup['access'].pk}/music/folders/").json()
    [row] = [e for e in data["events"] if e["type"] == "performance"]
    assert row["cancelled"] and row["items"][0]["scores"] == []


def test_manage_folders_with_numbers_and_units(api, club, setup):
    user = make_user("notenwart@example.org")
    give_role(user, club, permissions=["scores.view", "scores.edit"], name="Notenwart")
    client = api(user)
    base = f"/api/orgs/{club.pk}/music"
    with tenant_context(club.pk):
        zug = Department.objects.create(organization=club, name="Spielmannszug")
        neu = _arrangement(club, "Preußens Gloria")
    units = client.get(f"{base}/score-folders/units/").json()
    assert {"id": zug.pk, "name": "Spielmannszug"} in units
    response = client.post(
        f"{base}/score-folders/",
        {"name": "Repertoire", "kind": "repertoire", "departments": [zug.pk]},
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    folder = response.json()
    assert folder["departments"] == [zug.pk]
    item = client.post(
        f"{base}/score-folder-items/",
        {"folder": folder["id"], "arrangement": neu.pk, "number": " 5 "},
        content_type=JSON,
    )
    assert item.status_code == 201, item.content
    assert item.json()["number"] == "5" and item.json()["position"] == 1
    duplicate = client.post(
        f"{base}/score-folder-items/",
        {"folder": setup["book"].pk, "arrangement": neu.pk, "number": "27"},
        content_type=JSON,
    )
    assert duplicate.status_code == 400
    items = [
        i["id"] for i in client.get(f"{base}/score-folders/{setup['book'].pk}/").json()["items"]
    ]
    reordered = client.post(
        f"{base}/score-folders/{setup['book'].pk}/reorder/",
        {"items": list(reversed(items))},
        content_type=JSON,
    )
    assert reordered.status_code == 200, reordered.content
    assert [i["number"] for i in reordered.json()["items"]] == ["27", "12"]
    assert (
        client.post(
            f"{base}/score-folders/{setup['book'].pk}/reorder/",
            {"items": items[:1]},
            content_type=JSON,
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"{base}/score-folders/{folder['id']}/", {"departments": []}, content_type=JSON
        ).json()["departments"]
        == []
    )
    reader = make_user("musikleser@example.org")
    give_role(reader, club, permissions=["music.view"], name="Musik lesen")
    assert api(reader).get(f"{base}/score-folders/").status_code == 200
    assert (
        api(reader).post(f"{base}/score-folders/", {"name": "X"}, content_type=JSON).status_code
        == 403
    )


def test_score_folder_rls(club, orgs, setup):
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not ScoreFolder.objects.filter(pk=setup["book"].pk).exists()
        assert not ScoreFolderItem.objects.filter(folder_id=setup["book"].pk).exists()
