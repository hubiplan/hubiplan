"""API für andere Programme, Stufe 3 (docs/api.md): Schreiben mit eigens angekreuzten
Bereichen, Schreibgrenze, Wiederholungsschutz, eigene Kennung, Termine, Ergebnisse,
Anwesenheit, Vorschläge zu Mitgliedern, Ausweisprüfung, Rundschreiben als Entwurf.

Alle Daten erfunden.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from audit.models import AuditEntry
from billing.models import BusinessPartner
from cards.models import MemberCard
from circulars.models import Circular
from competitions.models import Competition, Score, Scoring, Starter
from core.tenancy import rls_bypass, tenant_context
from events.models import Event
from members.models import Person
from organizations.models import Department
from partnerapi.models import ApiAccess, IdempotencyKey, ReadLog, WrittenRecord
from portal.models import ChangeRequest
from training.models import Attendance, TrainingSession

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)

JSON = "application/json"
BASE = "/api/partner/v1/"


@pytest.fixture(autouse=True)
def _leerer_zwischenspeicher():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = [
        "members",
        "events",
        "competitions",
        "training",
        "cards",
        "circulars",
        "api",
    ]
    org.save()
    return org


@pytest.fixture
def chef(club):
    user = make_user("api-schreiben@example.org", first_name="Vera", last_name="Vorstand")
    give_role(user, club)
    return user


@pytest.fixture
def partner(club):
    with rls_bypass(), tenant_context(club.pk):
        return BusinessPartner.objects.create(
            organization=club,
            name="Musterbund Software GmbH",
            roles=["service"],
            bank={},
            details={"name": "Musterbund Software GmbH"},
        )


def in_days(days: int) -> str:
    return (timezone.localdate() + datetime.timedelta(days=days)).isoformat()


def create(api, user, org, **fields):
    body = {"name": "Verbandssoftware", "expires_at": in_days(200), **fields}
    return api(user).post(f"/api/orgs/{org.pk}/api-accesses/", json.dumps(body), JSON)


def personal(recipient, *scopes, **fields) -> dict:
    return {
        "scopes": ["mitglieder.lesen", *scopes],
        "partner": recipient.pk,
        "legal_basis": "processing",
        "legal_confirmed": True,
        **fields,
    }


def get(key: str, path: str = ""):
    return Client().get(BASE + path, HTTP_AUTHORIZATION=f"Bearer {key}")


def send(key: str, path: str, body: dict, *, method: str = "post", idem: str = ""):
    extra = {"HTTP_AUTHORIZATION": f"Bearer {key}"}
    if idem:
        extra["HTTP_IDEMPOTENCY_KEY"] = idem
    return getattr(Client(), method)(BASE + path, json.dumps(body), JSON, **extra)


def termin(**fields) -> dict:
    return {"title": "Kreismeisterschaft", "starts_at": "2027-05-08T10:00:00+02:00", **fields}


def test_schreiben_wird_eigens_angekreuzt_und_gemeldet(api, club, chef, settings):
    # Der Schlüssel im Quelltext einer fremden Webseite schreibt nie
    nein = create(api, chef, club, scopes=["termine.schreiben"], embeddable=True)
    assert nein.status_code == 400 and "embeddable" in nein.content.decode()
    made = create(api, chef, club, scopes=["termine.lesen"])
    assert made.status_code == 201, made.content
    data = made.json()
    assert data["writes"] is False and data["write_count"] == 0
    assert not any("schreiben" in m.subject for m in mail.outbox)
    listing = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()
    by_code = {s["scope"]: s for s in listing["scopes"]}
    assert by_code["termine.schreiben"]["write"] is True
    assert by_code["termine.lesen"]["write"] is False
    assert listing["writes_per_hour"] == 60
    # Nur lesen: Anlegen wird abgelehnt und nennt den fehlenden Bereich
    ohne = send(data["key"], "events/", termin())
    assert ohne.status_code == 403 and ohne.json()["scope"] == "termine.schreiben"
    # Schreiben nachträglich einschalten: frischer zweiter Faktor und Mail an die Verwalter
    url = f"/api/orgs/{club.pk}/api-accesses/{data['id']}/"
    body = json.dumps({"scopes": ["termine.lesen", "termine.schreiben"]})
    settings.MFA_STEP_UP = True
    gesperrt = api(chef).patch(url, body, JSON)
    assert gesperrt.status_code == 403 and gesperrt.json().get("step_up")
    settings.MFA_STEP_UP = False
    changed = api(chef).patch(url, body, JSON)
    assert changed.status_code == 200 and changed.json()["writes"] is True
    text = next(m.body for m in mail.outbox if "schreiben" in m.subject)
    assert "Termine anlegen und ändern" in text and "Vera Vorstand" in text
    assert send(data["key"], "events/", termin()).status_code == 201
    info = get(data["key"]).json()["access"]
    assert info["limits"]["writes_per_hour"] == 60


def test_termin_anlegen_aendern_absagen(api, club, chef):
    key = create(api, chef, club, scopes=["termine.lesen", "termine.schreiben"]).json()["key"]
    made = send(key, "events/", termin(location="Schießhalle", external_id="km-2027"))
    assert made.status_code == 201, made.content
    event = made.json()
    assert event["title"] == "Kreismeisterschaft" and event["external_id"] == "km-2027"
    assert event["visibility"] == "members" and event["is_cancelled"] is False
    with rls_bypass():
        row = Event.objects.get(pk=int(event["id"]))
        assert row.organization_id == club.pk and row.created_by_id is None
        entry = AuditEntry.objects.filter(organization=club, action="create").latest("pk")
        assert entry.via == "API-Zugang Verbandssoftware" and entry.user_id is None
    # Die eigene Kennung ist je Zugang eindeutig und lässt sich nachschlagen
    doppelt = send(key, "events/", termin(external_id="km-2027"))
    assert doppelt.status_code == 409 and doppelt.json()["code"] == "external_id_exists"
    assert doppelt.json()["id"] == event["id"]
    found = get(key, "lookup/?kind=event&external_id=km-2027")
    assert found.status_code == 200 and found.json()["id"] == event["id"]
    assert get(key, "lookup/?kind=event&external_id=fehlt").status_code == 404
    # Ändern: nur die gesendeten Felder
    patched = send(
        key,
        f"events/{event['id']}/",
        {"starts_at": "2027-05-09T11:00:00+02:00", "visibility": "public"},
        method="patch",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["visibility"] == "public" and patched.json()["location"] == "Schießhalle"
    # Nur der Beginn kam: Das Ende zieht mit (Vorgabe zwei Stunden)
    assert patched.json()["ends_at"].startswith("2027-05-09T")
    with rls_bypass():
        moved = Event.objects.get(pk=int(event["id"]))
        assert moved.ends_at - moved.starts_at == datetime.timedelta(hours=2)
    listed = get(key, "events/?from=2027-05-01&to=2027-05-31").json()["events"]
    assert [e["event_id"] for e in listed] == [event["id"]]
    # Absagen statt löschen
    cancelled = send(
        key,
        f"events/{event['id']}/",
        {"is_cancelled": True, "cancel_note": "Halle gesperrt"},
        method="patch",
    )
    assert cancelled.json()["is_cancelled"] is True
    assert cancelled.json()["cancel_note"] == "Halle gesperrt"
    assert (
        Client()
        .delete(f"{BASE}events/{event['id']}/", HTTP_AUTHORIZATION=f"Bearer {key}")
        .status_code
        == 405
    )
    with rls_bypass():
        assert Event.objects.filter(pk=int(event["id"])).exists()
    # Ungültige Angaben: 400 als Problem
    falsch = send(key, "events/", {"title": "Ohne Beginn"})
    assert falsch.status_code == 400 and falsch.json()["code"] == "invalid_request"
    shown = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()["accesses"][0]
    assert shown["write_count"] == 3 and shown["last_write_at"]


def test_nur_selbst_angelegte_termine_und_nie_nur_vorstand(api, club, chef):
    key = create(api, chef, club, scopes=["termine.lesen", "termine.schreiben"]).json()["key"]
    other = create(api, chef, club, name="Zeitmessung", scopes=["termine.schreiben"]).json()["key"]
    with rls_bypass():
        hand = Event.objects.create(
            organization=club,
            title="Vorstandssitzung",
            starts_at=timezone.now() + datetime.timedelta(days=5),
            ends_at=timezone.now() + datetime.timedelta(days=5, hours=2),
            visibility="public",
        )
    assert send(key, f"events/{hand.pk}/", {"title": "Gekapert"}, method="patch").status_code == 404
    event = send(key, "events/", termin()).json()
    # Ein anderer Zugang derselben Einheit ändert ihn nicht
    fremd = send(other, f"events/{event['id']}/", {"title": "Fremd"}, method="patch")
    assert fremd.status_code == 404
    assert send(key, "events/", termin(visibility="board")).status_code == 400
    # In HUBIplan auf „nur Vorstand“ gestellt: Die API ändert ihn nicht mehr
    with rls_bypass():
        Event.objects.filter(pk=int(event["id"])).update(visibility="board")
    locked = send(key, f"events/{event['id']}/", {"title": "Neu"}, method="patch")
    assert locked.status_code == 409 and locked.json()["code"] == "record_locked"
    with rls_bypass():
        assert Event.objects.get(pk=hand.pk).title == "Vorstandssitzung"
        assert Event.objects.get(pk=int(event["id"])).title == "Kreismeisterschaft"


def test_termin_eines_zugangs_fuer_eine_untereinheit(api, club, chef):
    with rls_bypass():
        zug = Department.objects.create(organization=club, parent=club, name="Jägerzug")
        other = Department.objects.create(organization=club, parent=club, name="Schützenzug")
    key = create(api, chef, club, unit=zug.pk, scopes=["termine.schreiben"]).json()["key"]
    event = send(key, "events/", termin())
    assert event.status_code == 201 and event.json()["unit"] == str(zug.uuid)
    fremd = send(key, "events/", termin(unit=str(other.uuid)))
    assert fremd.status_code == 400 and "unit" in fremd.content.decode()


def test_wiederholte_anfrage_legt_nichts_doppelt_an(api, club, chef):
    key = create(api, chef, club, scopes=["termine.schreiben"]).json()["key"]
    first = send(key, "events/", termin(), idem="anfrage-1")
    again = send(key, "events/", termin(), idem="anfrage-1")
    assert first.status_code == 201 and again.status_code == 201
    assert again.json() == first.json() and again["Idempotency-Replayed"] == "true"
    assert "Idempotency-Replayed" not in first
    with rls_bypass():
        assert Event.objects.filter(organization=club).count() == 1
    # Derselbe Schlüssel mit anderem Inhalt ist ein Fehler des Aufrufers
    other = send(key, "events/", termin(title="Etwas anderes"), idem="anfrage-1")
    assert other.status_code == 409 and other.json()["code"] == "idempotency_conflict"
    # Eine abgelehnte Anfrage belegt den Schlüssel nicht
    assert send(key, "events/", {"title": "Ohne Beginn"}, idem="anfrage-2").status_code == 400
    assert send(key, "events/", termin(title="Zweiter"), idem="anfrage-2").status_code == 201
    assert send(key, "events/", termin(), idem="x" * 101).status_code == 400
    # Nach 24 Stunden räumt der nächtliche Lauf auf
    from partnerapi.tasks import purge_logs

    with rls_bypass():
        assert IdempotencyKey.objects.count() == 2
        IdempotencyKey.objects.filter(key="anfrage-1").update(
            created_at=timezone.now() - datetime.timedelta(hours=25)
        )
    purge_logs()
    with rls_bypass():
        assert list(IdempotencyKey.objects.values_list("key", flat=True)) == ["anfrage-2"]


def test_schreibgrenze_und_einbettbarer_zugang(api, club, chef, monkeypatch):
    from partnerapi import views

    monkeypatch.setattr(views, "WRITE_LIMIT", 2)
    made = create(api, chef, club, scopes=["termine.lesen", "termine.schreiben"]).json()
    key = made["key"]
    assert send(key, "events/", termin()).status_code == 201
    assert send(key, "events/", termin()).status_code == 201
    zu_viel = send(key, "events/", termin())
    assert zu_viel.status_code == 429 and zu_viel.json()["code"] == "too_many_requests"
    # Lesen zählt nicht gegen die Schreibgrenze
    assert get(key, "events/").status_code == 200
    cache.clear()
    # Auch wenn der Schalter an der Verwaltung vorbei gesetzt wäre: einbettbar schreibt nie
    with rls_bypass():
        ApiAccess.objects.filter(pk=made["id"]).update(embeddable=True)
    gesperrt = send(key, "events/", termin())
    assert gesperrt.status_code == 403 and gesperrt.json()["code"] == "write_not_allowed"


def test_ergebnisse_einliefern(api, club, chef, partner):
    erika = make_member(club, "Erika", "Muster")
    with rls_bypass():
        comp = Competition.objects.create(
            organization=club, title="Pokalschießen", date="2027-06-01", status="laeuft"
        )
        scoring = Scoring.objects.create(
            organization=club,
            competition=comp,
            name="Einzelwertung",
            unit_label="Ringe",
            decimals=1,
        )
        done = Competition.objects.create(
            organization=club, title="Vorjahr", date="2026-06-01", status="endgueltig"
        )
    key = create(api, chef, club, **personal(partner, "ergebnisse.schreiben")).json()["key"]
    offen = get(key, "result-entry/")
    assert offen.status_code == 200, offen.content
    comps = offen.json()["competitions"]
    assert [c["title"] for c in comps] == ["Pokalschießen"]
    assert comps[0]["scorings"] == [
        {
            "id": str(scoring.pk),
            "name": "Einzelwertung",
            "unit_label": "Ringe",
            "decimals": 1,
            "higher_better": True,
        }
    ]
    member_id = get(key, "members/").json()["members"][0]["id"]
    rows = [
        {"scoring": str(scoring.pk), "value": "98.5", "member": member_id},
        {"scoring": str(scoring.pk), "value": "91", "name": "Gerd Gast", "club": "SV Beispiel"},
        {"scoring": "999999", "value": "90", "name": "Falsche Wertung"},
        {"scoring": str(scoring.pk), "value": "viel", "name": "Kein Wert"},
        {"scoring": str(scoring.pk), "value": "88", "external_id": "gast-7", "name": "Ina Gast"},
    ]
    sent = send(key, f"result-entry/{comp.pk}/", {"results": rows})
    assert sent.status_code == 200, sent.content
    out = sent.json()
    assert out["accepted"] == 3 and [r["index"] for r in out["rejected"]] == [2, 3]
    with rls_bypass():
        scores = {s.starter.name: s.value for s in Score.objects.filter(scoring=scoring)}
        assert scores == {
            "Erika Muster": Decimal("98.5"),
            "Gerd Gast": Decimal("91"),
            "Ina Gast": Decimal("88"),
        }
        assert Starter.objects.get(competition=comp, membership=erika).name == "Erika Muster"
    # Noch einmal mit geänderten Werten: dieselben Starter, kein zweiter Gast
    rows = [
        {"scoring": str(scoring.pk), "value": "92", "name": "gerd gast", "club": "SV Beispiel"},
        {"scoring": str(scoring.pk), "value": "89", "external_id": "gast-7", "name": "Ina G."},
    ]
    assert send(key, f"result-entry/{comp.pk}/", {"results": rows}).json()["accepted"] == 2
    with rls_bypass():
        assert Starter.objects.filter(competition=comp).count() == 3
        values = sorted(Score.objects.filter(scoring=scoring).values_list("value", flat=True))
        assert values == [Decimal("89"), Decimal("92"), Decimal("98.5")]
    # Abgeschlossene Wettbewerbe nehmen nichts mehr an
    zu = send(key, f"result-entry/{done.pk}/", {"results": rows})
    assert zu.status_code == 404
    assert send(key, "result-entry/unsinn/", {"results": rows}).status_code == 404


def test_training_und_anwesenheit(api, club, chef, partner):
    make_member(club, "Erika", "Muster")
    make_member(club, "Max", "Beispiel")
    key = create(api, chef, club, **personal(partner, "anwesenheit.schreiben")).json()["key"]
    members = {m["last_name"]: m["id"] for m in get(key, "members/").json()["members"]}
    made = send(
        key,
        "trainings/",
        {
            "date": "2027-03-04",
            "title": "Übungsabend",
            "starts_at": "19:30",
            "external_id": "ua-0304",
        },
    )
    assert made.status_code == 201, made.content
    training = made.json()
    assert training["title"] == "Übungsabend" and training["present"] == []
    unknown = "00000000-0000-0000-0000-000000000000"
    sent = send(
        key,
        f"trainings/{training['id']}/attendance/",
        {"present": [members["Muster"], members["Beispiel"], unknown]},
    )
    assert sent.status_code == 200, sent.content
    assert sent.json()["changed"] == 2 and sent.json()["unknown"] == [unknown]
    weg = send(key, f"trainings/{training['id']}/attendance/", {"absent": [members["Beispiel"]]})
    assert weg.json()["changed"] == 1 and weg.json()["present"] == [members["Muster"]]
    assert get(key, f"trainings/{training['id']}/").json()["present"] == [members["Muster"]]
    with rls_bypass():
        session = TrainingSession.objects.get(pk=int(training["id"]))
        assert session.shooting is False and session.created_by_id is None
        assert Attendance.objects.filter(session=session).count() == 1
        hand = TrainingSession.objects.create(
            organization=club, date="2027-03-05", title="Von Hand angelegt"
        )
    # Nur Trainingstermine dieses Zugangs
    fremd = send(key, f"trainings/{hand.pk}/attendance/", {"present": [members["Muster"]]})
    assert fremd.status_code == 404
    with rls_bypass():
        assert not Attendance.objects.filter(session=hand).exists()
    # Ohne bestätigte Rechtsgrundlage keine Anwesenheit
    with rls_bypass():
        ApiAccess.objects.update(legal_confirmed_at=None)
    ohne = send(key, f"trainings/{training['id']}/attendance/", {"present": []})
    assert ohne.status_code == 403 and ohne.json()["code"] == "legal_basis_missing"


def test_aenderung_am_mitglied_nur_als_vorschlag(api, club, chef, partner):
    erika = make_member(club, "Erika", "Muster", email="erika@example.org")
    key = create(api, chef, club, **personal(partner, "mitglieder.schreiben")).json()["key"]
    member_id = get(key, "members/").json()["members"][0]["id"]
    path = f"members/{member_id}/proposals/"
    made = send(
        key,
        path,
        {
            "last_name": "Muster-Beispiel",
            "email": "erika@example.org",
            "city": "Neustadt",
            "message": "Heirat",
            "external_id": "v-1",
        },
    )
    assert made.status_code == 201, made.content
    proposal = made.json()
    # Die unveränderte E-Mail gehört nicht zum Vorschlag
    assert proposal["status"] == "pending" and proposal["changed"] == ["city", "last_name"]
    with rls_bypass():
        # Nichts gilt, bevor der Verein übernimmt
        assert Person.objects.get(pk=erika.person_id).last_name == "Muster"
        cr = ChangeRequest.objects.get(pk=int(proposal["id"]))
        assert cr.user_id is None and cr.membership_id == erika.pk
        assert cr.data == {"last_name": "Muster-Beispiel", "city": "Neustadt"}
        assert cr.previous["last_name"] == "Muster"
        assert cr.message == "Vorschlag über den API-Zugang Verbandssoftware: Heirat"
    assert send(key, path, {"last_name": "Muster"}).status_code == 400
    assert send(key, path, {"city": "Altdorf", "external_id": "v-1"}).status_code == 409
    assert send(key, path, {"city": "Altdorf"}).status_code == 201
    assert send(key, path, {"city": "Dritte"}).status_code == 201
    voll = send(key, path, {"city": "Vierte"})
    assert voll.status_code == 409 and voll.json()["code"] == "too_many_open"
    fremd = send(key, "members/00000000-0000-0000-0000-000000000000/proposals/", {"city": "X"})
    assert fremd.status_code == 404
    # Der Verein lehnt ab: Der Dritte sieht den Stand
    with rls_bypass():
        ChangeRequest.objects.filter(pk=cr.pk).update(status="rejected", decided_at=timezone.now())
    stand = get(key, f"proposals/{proposal['id']}/")
    assert stand.status_code == 200 and stand.json()["status"] == "rejected"
    assert stand.json()["decided_at"]
    assert get(key, "proposals/999999/").status_code == 404


def test_ausweis_pruefen_ohne_namen(api, club, chef, partner, orgs):
    erika = make_member(club, "Erika", "Muster")
    other_club = orgs["b"]
    other_club.enabled_modules = sorted({*other_club.enabled_modules, "members", "cards"})
    other_club.save()
    fremd = make_member(other_club, "Frieda", "Fremd")
    with rls_bypass(), tenant_context(club.pk):
        card = MemberCard.objects.create(organization=club, membership=erika)
    with rls_bypass(), tenant_context(other_club.pk):
        foreign = MemberCard.objects.create(organization=other_club, membership=fremd)
    made = create(api, chef, club, **personal(partner, "ausweis.pruefen"))
    assert made.status_code == 201, made.content
    key = made.json()["key"]
    ok = send(key, "card-check/", {"code": f"https://verein.example.org/ausweis/{card.token}"})
    assert ok.status_code == 200, ok.content
    assert ok.json() == {"valid": True, "status": "active", "member_type": "aktiv"}
    assert "Muster" not in ok.content.decode()
    assert send(key, "card-check/", {"code": card.token}).json()["valid"] is True
    # Ausweise anderer Vereine und unbekannte Codes verraten nichts
    for code in (foreign.token, "gibt-es-nicht"):
        answer = send(key, "card-check/", {"code": code}).json()
        assert answer == {"valid": False, "status": "unknown", "member_type": None}
    with rls_bypass():
        logs = list(ReadLog.objects.filter(scope="ausweis.pruefen").values_list("count", flat=True))
        # Abfragen zählen nicht als Schreiben
        assert ApiAccess.objects.get(pk=made.json()["id"]).write_count == 0
    assert logs == [1, 1]


def test_rundschreiben_nur_als_entwurf(api, club, chef):
    key = create(api, chef, club, scopes=["rundschreiben.schreiben"]).json()["key"]
    before = len(mail.outbox)
    made = send(
        key,
        "circular-drafts/",
        {"subject": "Ausschreibung Kreispokal", "body": "Meldeschluss ist der **1. Mai**."},
    )
    assert made.status_code == 201, made.content
    assert made.json()["status"] == "draft"
    with rls_bypass():
        circular = Circular.objects.get(pk=int(made.json()["id"]))
        assert circular.status == "draft" and circular.created_by_id is None
        assert circular.subject == "Ausschreibung Kreispokal" and circular.sent_at is None
        assert WrittenRecord.objects.filter(kind="circular", object_id=circular.pk).exists()
    # Die API versendet nie
    assert len(mail.outbox) == before
    assert send(key, "circular-drafts/", {"subject": "Ohne Text"}).status_code == 400


def test_schreibbereiche_haengen_am_modul_und_an_der_art_der_einheit(api, club, chef, orgs):
    club.enabled_modules = ["members", "events", "api"]
    club.save()
    listing = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()
    codes = {s["scope"] for s in listing["scopes"]}
    assert "termine.schreiben" in codes and "mitglieder.schreiben" in codes
    assert not codes & {"ergebnisse.schreiben", "anwesenheit.schreiben", "ausweis.pruefen"}
    assert "rundschreiben.schreiben" not in codes
    # Vorschläge zu Mitgliedern setzen das Lesen voraus
    made = create(api, chef, club, scopes=["mitglieder.schreiben"])
    assert made.status_code == 400 and "partner" in made.content.decode()
