"""Musik: Auftrittsart (#713), Uniform als Auswahl (#712) und ein Vertrag für mehrere Tage (#711).

Alles erfunden (Musterkapelle, Musterstadt).
"""
# ruff: noqa: F811

import datetime
import json
import uuid

import pytest
from django.utils import timezone

from billing.models import BusinessPartner
from core.tenancy import tenant_context
from events.models import Event
from finance.models import Project
from music.models import (
    Assignment,
    Musician,
    Performance,
    PerformanceAccount,
    PerformanceKind,
    Position,
    Uniform,
)
from music.performance_tasks import fingerprint
from portal.models import PortalAccess

from .factories import make_member, make_user
from .test_music import JSON, c, club, music  # noqa: F401

pytestmark = pytest.mark.django_db


def day(club, title, offset, project=None):
    start = timezone.now() + datetime.timedelta(days=offset)
    return Event.objects.create(
        organization=club,
        title=title,
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=3),
        project=project,
    )


def post(c, url, data, status=201):
    r = c.post(url, data, content_type=JSON)
    assert r.status_code == status, r.content
    return r.json()


def patch(c, url, data, status=200):
    r = c.patch(url, data, content_type=JSON)
    assert r.status_code == status, r.content
    return r.json()


def test_auftrittsarten_vorbelegt_und_vorschlag(c, club, music):
    base, event = music
    kinds = c.get(f"{base}/performance-kinds/").json()
    names = [k["name"] for k in kinds]
    assert {"Umzug", "Zapfenstreich", "Konzert", "Frühschoppen"} <= set(names)
    # Zweiter Abruf legt nichts doppelt an
    assert len(c.get(f"{base}/performance-kinds/").json()) == len(kinds)
    own = post(c, f"{base}/performance-kinds/", {"name": "Schützenball", "formation": "seated"})
    post(c, f"{base}/performance-kinds/", {"name": "Schützenball"}, status=400)
    performance = post(c, f"{base}/performances/", {"event": event.pk, "kind": own["id"]})
    assert performance["kind_name"] == "Schützenball"
    # Verwendete Art lässt sich nicht löschen, nur archivieren
    assert c.delete(f"{base}/performance-kinds/{own['id']}/").status_code == 400
    patch(c, f"{base}/performance-kinds/{own['id']}/", {"active": False})
    with tenant_context(club.pk):
        other = Event.objects.create(
            organization=club,
            title="Zweites Musterkonzert",
            starts_at="2026-12-02T18:00:00Z",
            ends_at="2026-12-02T20:00:00Z",
        )
    post(c, f"{base}/performances/", {"event": other.pk, "kind": own["id"]}, status=400)


def test_uniform_auswahl_mit_checkliste_im_mitgliederbereich(api, c, club, music):
    base, event = music
    uniform = post(
        c,
        f"{base}/uniforms/",
        {
            "name": "Sommeruniform",
            "description": "Kurzarmhemd mit Vereinsabzeichen",
            "checklist": ["Mütze", " ", "weiße Handschuhe"],
        },
    )
    assert uniform["checklist"] == ["Mütze", "weiße Handschuhe"]
    post(c, f"{base}/uniforms/", {"name": "Zu lang", "checklist": ["x"] * 31}, status=400)
    performance = post(
        c,
        f"{base}/performances/",
        {"event": event.pk, "uniform_choice": uniform["id"], "uniform": "ohne Jacke"},
    )
    assert performance["uniform_text"] == "Sommeruniform · ohne Jacke"
    assert performance["uniform_details"]["checklist"] == ["Mütze", "weiße Handschuhe"]

    member = make_member(club, "Alex", "Muster")
    user = make_user("uniform-musik@example.org")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
        musician = Musician.objects.create(organization=club, membership=member)
        row = Performance.objects.get(pk=performance["id"])
        position = Position.objects.create(organization=club, performance=row, instrument="Tuba")
        Assignment.objects.create(
            organization=club, performance=row, position=position, musician=musician
        )
    client = api(user)
    [own] = client.get(f"/api/portal/{access.pk}/music/").json()
    assert own["uniform"] == "Sommeruniform · ohne Jacke"
    assert own["uniform_details"]["description"] == "Kurzarmhemd mit Vereinsabzeichen"
    # Ohne Bild gibt es nichts; fremde Uniformen bleiben verborgen
    assert (
        client.get(f"/api/portal/{access.pk}/music/uniforms/{uniform['id']}/image/").status_code
        == 404
    )
    assert c.delete(f"{base}/uniforms/{uniform['id']}/").status_code == 400


def test_fingerabdruck_alter_auftritte_bleibt_gleich(club, music):
    _, event = music
    with tenant_context(club.pk):
        performance = Performance.objects.create(
            organization=club, event=event, uniform="Vereinshemd"
        )
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba"
        )
        musician = Musician.objects.create(organization=club, name="Muster Gast")
        row = Assignment.objects.create(
            organization=club, performance=performance, position=position, musician=musician
        )
        before = fingerprint(row)
        assert len(before) == 64
        uniform = Uniform.objects.create(organization=club, name="Tracht")
        performance.uniform_choice = uniform
        performance.save()
        row.refresh_from_db()
        assert fingerprint(row) != before


@pytest.fixture
def festival(club, music):
    base, _ = music
    with tenant_context(club.pk):
        project = Project.objects.create(
            organization=club, name="Musterfest 2027", starts_on=timezone.localdate()
        )
        partner = BusinessPartner.objects.create(
            organization=club,
            name="Muster Schützenverein",
            details={
                "name": "Muster Schützenverein",
                "street": "Festplatz 1",
                "postcode": "12345",
                "city": "Musterstadt",
                "country": "DE",
            },
        )
        days = [day(club, f"Musterfest Tag {n}", 10 + n, project) for n in range(1, 4)]
    return base, project, partner, days


def test_ein_vertrag_fuer_alle_tage(c, club, festival):
    base, project, partner, days = festival
    first = post(c, f"{base}/performances/", {"event": days[0].pk, "customer": partner.pk})
    second = post(c, f"{base}/performances/", {"event": days[1].pk})
    third = post(c, f"{base}/performances/", {"event": days[2].pk})
    assert first["project"] == project.pk
    # Weiterer Tag erbt den Auftraggeber
    row = patch(c, f"{base}/performances/{second['id']}/", {"main": first["id"]})
    assert row["customer"] == partner.pk
    # Kein weiterer Tag an einem weiteren Tag
    patch(c, f"{base}/performances/{third['id']}/", {"main": second["id"]}, status=400)
    # Zusammenfassen hängt den Rest der Veranstaltung an
    result = post(c, f"{base}/performances/{first['id']}/combine/", {}, status=200)
    assert result["added"] == [third["id"]] and result["skipped"] == []
    lead = c.get(f"{base}/performances/").json()
    assert next(p for p in lead if p["id"] == first["id"])["days"] == sorted(
        [second["id"], third["id"]]
    )

    # Abrechnung eines Tages ist die des Hauptauftritts
    settle = f"{base}/performances/{third['id']}/settlement/"
    r = c.post(
        settle,
        {"action": "agreement", "fee": "1500", "travel": "100", "extras": "0"},
        content_type=JSON,
    )
    assert r.status_code == 200, r.content
    data = r.json()
    assert data["performance"] == first["id"]
    assert [d["id"] for d in data["days"]] == [first["id"], second["id"], third["id"]]
    with tenant_context(club.pk):
        assert not PerformanceAccount.objects.filter(performance_id=third["id"]).exists()
        musician = Musician.objects.create(organization=club, name="Muster Gast")
        perf = Performance.objects.get(pk=second["id"])
        position = Position.objects.create(organization=club, performance=perf, instrument="Tuba")
        assignment = Assignment.objects.create(
            organization=club, performance=perf, position=position, musician=musician
        )
    r = c.post(
        settle,
        {
            "action": "claim",
            "assignment": assignment.pk,
            "fee": "80",
            "allowance": "0",
            "expenses": "0",
            "attended": True,
        },
        content_type=JSON,
    )
    assert r.status_code == 200, r.content
    assert [row["performance"] for row in r.json()["claims"]] == [second["id"]]

    # Angebot nennt alle Tage
    engagement = f"{base}/performances/{second['id']}/engagement/"
    r = c.post(
        engagement,
        {
            "action": "offer",
            "valid_until": (timezone.localdate() + datetime.timedelta(days=5)).isoformat(),
            "terms": "Drei Tage Blasmusik nach Absprache.",
        },
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert r.status_code == 200, r.content
    snapshot = r.json()["snapshot"]
    assert [d["title"] for d in snapshot["days"]] == [d.title for d in days]
    assert snapshot["total"] == "1600.00"
    # Angenommen: Tage lassen sich weder lösen noch ändern
    r = c.post(
        engagement,
        {"action": "accept", "document": r.json()["id"], "acceptance_note": "Musterzusage"},
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert r.status_code == 200, r.content
    patch(c, f"{base}/performances/{third['id']}/", {"main": None}, status=400)


def test_tag_mit_eigener_abrechnung_bleibt_eigenstaendig(c, club, festival):
    base, _, _, days = festival
    first = post(c, f"{base}/performances/", {"event": days[0].pk})
    second = post(c, f"{base}/performances/", {"event": days[1].pk})
    with tenant_context(club.pk):
        PerformanceAccount.objects.create(
            organization=club, performance_id=second["id"], fee=200, date=timezone.localdate()
        )
    patch(c, f"{base}/performances/{second['id']}/", {"main": first["id"]}, status=400)
    result = post(c, f"{base}/performances/{first['id']}/combine/", {}, status=200)
    assert result["added"] == []
    assert [s["id"] for s in result["skipped"]] == [second["id"]]


def test_art_auf_der_webseite(club, music):
    from website.public_views import _performance_kind

    _, event = music
    with tenant_context(club.pk):
        kind = PerformanceKind.objects.create(organization=club, name="Zapfenstreich")
        Performance.objects.create(organization=club, event=event, kind=kind)
        event.refresh_from_db()
        assert _performance_kind(event) is None
        kind.on_website = True
        kind.save()
        event = Event.objects.get(pk=event.pk)
        assert _performance_kind(event) == "Zapfenstreich"


def test_daten_sind_json(club, music):
    # Die Checkliste bleibt eine einfache Liste (Datenexport, KI-Schnittstelle)
    with tenant_context(club.pk):
        uniform = Uniform.objects.create(organization=club, name="Tracht", checklist=["Hut"])
    assert json.loads(json.dumps(uniform.checklist)) == ["Hut"]
