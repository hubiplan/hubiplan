"""Noten und Programme: Bestandsabgleich, Reihenfolge, Export und Rechte."""
# ruff: noqa: F811

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from documents.models import Document, Folder
from music.models import (
    Arrangement,
    Assignment,
    Musician,
    Performance,
    Piece,
    Position,
)

from .factories import give_role, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture
def repertoire(c, club, music):
    base, event = music

    def create(endpoint, **values):
        response = c.post(f"{base}/{endpoint}/", values, content_type=JSON)
        assert response.status_code == 201, response.content
        return response.json()["id"]

    piece = create("pieces", title="=Musterlied", composer="Alex Beispiel")
    arrangement = create("arrangements", piece=piece, name="Konzertfassung", duration_seconds=180)
    create(
        "parts",
        arrangement=arrangement,
        instrument="Trompete",
        register="1",
        kind="part",
        paper_format="concert",
        copies=1,
        required_players=2,
        location="Schrank A",
    )
    create(
        "parts",
        arrangement=arrangement,
        instrument="Trompete",
        register="1",
        kind="part",
        paper_format="march",
        copies=10,
        required_players=2,
    )
    with tenant_context(club.pk):
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club,
            performance=performance,
            instrument="Trompete",
            register="1",
            required=2,
        )
        player = Musician.objects.create(organization=club, name="Mika Beispiel")
        Assignment.objects.create(
            organization=club,
            performance=performance,
            position=position,
            musician=player,
            status="accepted",
        )
    return base, performance, arrangement


def add(c, url, arrangement=None, kind="piece", duration=None, **extra):
    return c.post(
        url,
        {
            "arrangement": arrangement,
            "kind": kind,
            "duration_seconds": duration,
            "paper_format": "concert",
            **extra,
        },
        content_type=JSON,
    )


def test_program_order_duration_stock_and_csv(c, club, repertoire):
    base, performance, arrangement = repertoire
    url = f"{base}/performances/{performance.pk}/program/"
    response = add(c, url, arrangement)
    assert response.status_code == 200, response.content
    voice = response.json()["preparation"][0]["voices"][0]
    assert (voice["required"], voice["planned"], voice["accepted"]) == (2, 2, 1)
    assert voice["missing_copies"] == voice["missing_players"] == 1
    assert voice["copies"] == 1  # Marschbuch-Exemplare zählen nicht im Konzertformat.
    assert add(c, url, kind="pause", duration=60).status_code == 200
    result = add(c, url, arrangement, kind="encore", duration=90).json()
    assert (result["total_seconds"], result["regular_seconds"], result["encore_seconds"]) == (
        330,
        240,
        90,
    )
    assert len(result["preparation"]) == 1  # Gleicher Notensatz wird nur einmal vorbereitet.
    ids = [e["id"] for e in result["entries"]]
    r = c.post(url, {"action": "reorder", "ids": list(reversed(ids))}, content_type=JSON)
    assert [e["id"] for e in r.json()["entries"]] == list(reversed(ids))
    assert (
        c.post(url, {"action": "reorder", "ids": [ids[0], ids[0]]}, content_type=JSON).status_code
        == 400
    )
    exported = c.get(url + "?export=program")
    assert exported.status_code == 200
    assert "'=Musterlied" in exported.content.decode("utf-8-sig")
    assert "Schrank A" in c.get(url + "?export=parts").content.decode("utf-8-sig")


def test_foreign_arrangement_and_calendar_rights(api, c, club, orgs, repertoire):
    base, performance, _ = repertoire
    with tenant_context(orgs["b"].pk):
        piece = Piece.objects.create(organization=orgs["b"], title="Fremdes Stück")
        arrangement = Arrangement.objects.create(
            organization=orgs["b"], piece=piece, name="Fremde Fassung"
        )
    url = f"{base}/performances/{performance.pk}/program/"
    assert add(c, url, arrangement.pk).status_code == 404
    with tenant_context(club.pk):
        event = performance.event
        event.visibility = "board"
        event.save()
    user = make_user("musik-lesen@example.org")
    give_role(user, club, permissions=["music.view"], name="Musikleser")
    client = api(user)
    assert client.get(url).status_code == 403
    assert client.post(f"{base}/pieces/", {"title": "Neu"}, content_type=JSON).status_code == 403
    with as_app_role(), tenant_context(club.pk):
        assert not Arrangement.objects.filter(pk=arrangement.pk).exists()


def test_documents_need_their_own_rights_and_live_visibility(api, c, club, repertoire):
    base, _, arrangement = repertoire
    with tenant_context(club.pk):
        folder = Folder.objects.create(organization=club, name="Noten", public_key=Folder.new_key())
        document = Document.objects.create(
            organization=club, folder=folder, title="Partitur Beispiel"
        )
    r = c.post(
        f"{base}/score-documents/",
        {"arrangement": arrangement, "document": document.pk},
        content_type=JSON,
    )
    assert r.status_code == 201, r.content
    link = r.json()["id"]
    user = make_user("noten-leser@example.org")
    give_role(user, club, permissions=["music.view"], name="Notenleser")
    client = api(user)
    assert client.get(f"{base}/score-documents/").json() == []
    assert client.get(f"{base}/score-documents/{link}/download/").status_code == 404
    with tenant_context(club.pk):
        document.deleted_at = timezone.now()
        document.save()
    assert c.get(f"{base}/score-documents/").json() == []


def test_pause_rules_and_archived_arrangement(c, club, repertoire):
    base, performance, arrangement = repertoire
    url = f"{base}/performances/{performance.pk}/program/"
    assert add(c, url).status_code == 400
    assert add(c, url, kind="pause").status_code == 400
    assert add(c, url, arrangement, kind="pause", duration=60).status_code == 400
    with tenant_context(club.pk):
        Arrangement.objects.filter(pk=arrangement).update(active=False)
    assert add(c, url, arrangement).status_code == 400
