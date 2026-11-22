"""API für andere Programme, Stufe 2 (docs/api.md): Personendaten nur mit Empfänger und
Rechtsgrundlage, Verbandsmeldung, Mitglieder, Ehrungen, Qualifikationen, Abrufprotokoll,
Benachrichtigungen.

Alle Daten erfunden.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from billing.models import BusinessPartner
from core import safehttp
from core.tenancy import rls_bypass, tenant_context
from members.models import (
    ContactDetails,
    HonoraryTitle,
    HonoraryTitleAward,
    Membership,
    MemberType,
    Person,
)
from organizations.models import Department
from partnerapi import webhooks
from partnerapi.models import ApiAccess, ReadLog, RecordRef, WebhookDelivery
from qualifications.models import Qualification, QualificationType

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)

JSON = "application/json"
BASE = "/api/partner/v1/"
HOOK = "https://verband.example.org/hubiplan"


@pytest.fixture(autouse=True)
def _leerer_zwischenspeicher():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "awards", "qualifications", "api"]
    org.save()
    return org


@pytest.fixture
def chef(club):
    user = make_user("api-vorstand@example.org", first_name="Vera", last_name="Vorstand")
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


def personal(recipient, **fields) -> dict:
    return {
        "scopes": ["mitglieder.lesen"],
        "partner": recipient.pk,
        "legal_basis": "processing",
        "legal_confirmed": True,
        **fields,
    }


def call(key: str, path: str = ""):
    return Client().get(BASE + path, HTTP_AUTHORIZATION=f"Bearer {key}")


def leave(club, membership, when: datetime.date) -> None:
    with rls_bypass(), tenant_context(club.pk):
        period = membership.periods.get()
        period.exit_date = when
        period.exit_reason = "exclusion"
        period.save()


def test_personendaten_nur_mit_empfaenger_und_bestaetigter_rechtsgrundlage(
    api, club, chef, partner
):
    assert create(api, chef, club, scopes=["mitglieder.lesen"]).status_code == 400
    ohne = create(api, chef, club, **personal(partner, legal_confirmed=False))
    assert ohne.status_code == 400 and "legal_confirmed" in ohne.content.decode()
    assert create(api, chef, club, **personal(partner, legal_basis="")).status_code == 400
    assert create(api, chef, club, **personal(partner, partner=999999)).status_code == 400
    # Der Schlüssel für Personendaten steht nie im Quelltext einer fremden Webseite
    assert create(api, chef, club, **personal(partner, embeddable=True)).status_code == 400
    made = create(api, chef, club, **personal(partner, member_fields=["contact"]))
    assert made.status_code == 201, made.content
    data = made.json()
    assert data["personal"] is True and data["legal_basis"] == "processing"
    assert data["partner"] == {"id": partner.pk, "name": "Musterbund Software GmbH"}
    assert data["legal_confirmed_at"] and data["legal_confirmed_by"] == "Vera Vorstand"
    assert data["member_fields"] == ["contact"] and data["only_active"] is True
    # Auftragsverarbeitung: Der Empfänger steht damit im Verzeichnis der Verarbeitungen
    with rls_bypass(), tenant_context(club.pk):
        assert "processor" in BusinessPartner.objects.get(pk=partner.pk).roles
    subjects = [m.subject for m in mail.outbox]
    assert any("Personendaten" in s for s in subjects)
    body = next(m.body for m in mail.outbox if "Personendaten" in m.subject)
    assert "Musterbund Software GmbH" in body and data["key"] not in body
    listing = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()
    assert listing["partners"] == [
        {"id": partner.pk, "name": "Musterbund Software GmbH", "processor": True}
    ]
    assert listing["member_fields"] == ["contact", "membership", "units"]


def test_anderer_empfaenger_braucht_neue_bestaetigung(api, club, chef, partner, settings):
    made = create(api, chef, club, **personal(partner)).json()
    with rls_bypass(), tenant_context(club.pk):
        other = BusinessPartner.objects.create(
            organization=club, name="Beispiel IT", bank={}, details={"name": "Beispiel IT"}
        )
    url = f"/api/orgs/{club.pk}/api-accesses/{made['id']}/"
    ohne = api(chef).patch(url, json.dumps({"partner": other.pk}), JSON)
    assert ohne.status_code == 400 and "legal_confirmed" in ohne.content.decode()
    # Verlängern allein fragt nicht erneut
    assert api(chef).patch(url, json.dumps({"expires_at": in_days(300)}), JSON).status_code == 200
    settings.MFA_STEP_UP = True
    body = json.dumps({"partner": other.pk, "legal_confirmed": True})
    resp = api(chef).patch(url, body, JSON)
    assert resp.status_code == 403 and resp.json().get("step_up")
    assert api(chef).patch(url, json.dumps({"name": "Neu"}), JSON).status_code == 200


def test_mitglieder_nur_gewaehlte_feldgruppen_und_abrufprotokoll(api, club, chef, partner):
    erika = make_member(club, "Erika", "Muster", birth_date=datetime.date(1980, 5, 17))
    make_member(club, "Max", "Beispiel", birth_date=datetime.date(1975, 3, 1))
    key = create(api, chef, club, **personal(partner)).json()["key"]
    response = call(key, "members/")
    assert response.status_code == 200, response.content
    members = response.json()["members"]
    assert [m["last_name"] for m in members] == ["Muster", "Beispiel"]
    first = members[0]
    assert first["first_name"] == "Erika" and first["birth_date"] == "1980-05-17"
    assert first["status"] == "active" and first["kind"] == "person"
    assert "contact" not in first and "membership" not in first and "units" not in first
    assert "Lindenweg" not in response.content.decode()
    # Nach außen geht nie die interne Nummer, und die Kennung bleibt gleich
    assert first["id"] != str(erika.pk)
    assert call(key, "members/").json()["members"][0]["id"] == first["id"]
    one = call(key, f"members/{first['id']}/")
    assert one.status_code == 200 and one.json()["last_name"] == "Muster"
    assert call(key, "members/00000000-0000-0000-0000-000000000000/").status_code == 404
    assert call(key, "members/unsinn/").status_code == 404
    with rls_bypass():
        logs = list(ReadLog.objects.order_by("pk").values_list("scope", "count"))
        assert RecordRef.objects.filter(kind="member").count() == 2
    assert logs == [("mitglieder.lesen", 2), ("mitglieder.lesen", 2), ("mitglieder.lesen", 1)]
    shown = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()["accesses"][0]
    assert shown["records_read"] == 5 and len(shown["reads"]) == 3
    info = call(key).json()["access"]
    assert info["personal_data"] is True and info["member_fields"] == []


def test_feldgruppen_kontakt_mitgliedschaft_untereinheiten(api, club, chef, partner):
    with rls_bypass():
        zug = Department.objects.create(organization=club, parent=club, name="Jägerzug")
    make_member(club, "Erika", "Muster", departments=[zug])
    fields = ["units", "contact", "membership"]
    key = create(api, chef, club, **personal(partner, member_fields=fields)).json()["key"]
    member = call(key, "members/").json()["members"][0]
    assert member["contact"]["street"] == "Lindenweg 4" and member["contact"]["city"]
    assert member["contact"]["email"] == "erika@example.org"
    assert member["membership"]["entry_date"] == "2015-01-01"
    assert member["membership"]["exit_date"] is None
    assert member["membership"]["member_type"]["name"] == "aktiv"
    assert [u["name"] for u in member["units"]] == ["Jägerzug"]
    assert member["units"][0]["id"] == str(zug.uuid)
    text = json.dumps(member)
    assert "iban" not in text and "note" not in text and "photo" not in text


def test_nur_aktuelle_und_nur_volljaehrige(api, club, chef, partner):
    make_member(club, "Erika", "Muster")
    gone = make_member(club, "Max", "Beispiel")
    year = timezone.localdate().year
    make_member(club, "Jona", "Jung", birth_date=datetime.date(year - 10, 1, 1))
    leave(club, gone, timezone.localdate() - datetime.timedelta(days=30))
    eng = create(api, chef, club, **personal(partner, adults_only=True)).json()["key"]
    assert [m["last_name"] for m in call(eng, "members/").json()["members"]] == ["Muster"]
    # Die Begrenzung am Zugang gilt, was auch immer der Aufrufer verlangt
    assert [m["last_name"] for m in call(eng, "members/?status=all").json()["members"]] == [
        "Muster"
    ]
    weit = create(
        api, chef, club, **personal(partner, only_active=False, member_fields=["membership"])
    ).json()["key"]
    alle = call(weit, "members/?status=all").json()["members"]
    assert [m["last_name"] for m in alle] == ["Muster", "Beispiel", "Jung"]
    former = call(weit, "members/?status=former").json()["members"]
    assert [m["last_name"] for m in former] == ["Beispiel"]
    assert former[0]["status"] == "former" and former[0]["membership"]["exit_date"]
    # Ausschluss, Streichung und Tod gehen nicht nach außen
    assert former[0]["membership"]["periods"][0]["exit_reason"] == "other"
    assert call(weit, "members/?status=unsinn").status_code == 400


def test_ohne_gueltige_rechtsgrundlage_keine_personendaten(api, club, chef, partner):
    make_member(club, "Erika", "Muster")
    key = create(api, chef, club, **personal(partner)).json()["key"]
    assert call(key, "members/").status_code == 200
    with rls_bypass(), tenant_context(club.pk):
        BusinessPartner.objects.filter(pk=partner.pk).update(is_active=False)
    response = call(key, "members/")
    assert response.status_code == 403 and response.json()["code"] == "legal_basis_missing"
    assert "Muster" not in response.content.decode()
    # Ohne den Bereich: 403 wie in Stufe 1
    other = create(api, chef, club, scopes=["einheit.lesen"]).json()["key"]
    assert call(other, "members/").json()["code"] == "missing_scope"


def test_geaendert_seit_findet_auch_den_austritt(api, club, chef, partner):
    make_member(club, "Erika", "Muster")
    gone = make_member(club, "Max", "Beispiel")
    long_ago = timezone.now() - datetime.timedelta(days=10)
    with rls_bypass():
        Membership.objects.filter(organization=club).update(updated_at=long_ago)
        Person.objects.filter(pk__in=[gone.person_id]).update(updated_at=long_ago)
        ContactDetails.objects.filter(person_id=gone.person_id).update(updated_at=long_ago)
    since = (timezone.now() - datetime.timedelta(days=1)).isoformat().replace("+", "%2B")
    key = create(api, chef, club, **personal(partner, only_active=False)).json()["key"]
    leave(club, gone, timezone.localdate() - datetime.timedelta(days=2))
    names = [
        m["last_name"]
        for m in call(key, f"members/?status=all&changed_since={since}").json()["members"]
    ]
    assert "Beispiel" in names


def test_zugang_einer_untereinheit_sieht_nur_ihre_mitglieder(api, club, chef, partner):
    with rls_bypass():
        zug = Department.objects.create(organization=club, parent=club, name="Jägerzug")
    make_member(club, "Erika", "Muster", departments=[zug])
    make_member(club, "Max", "Beispiel")
    made = create(api, chef, club, unit=zug.pk, **personal(partner))
    assert made.status_code == 201, made.content
    key = made.json()["key"]
    assert [m["last_name"] for m in call(key, "members/").json()["members"]] == ["Muster"]
    whole = create(api, chef, club, **personal(partner)).json()["key"]
    filtered = call(whole, f"members/?unit={zug.uuid}").json()["members"]
    assert [m["last_name"] for m in filtered] == ["Muster"]
    # Die Verbandsmeldung gibt es nur für den ganzen Verein
    report = create(api, chef, club, unit=zug.pk, scopes=["verbandsmeldung.lesen"])
    assert report.status_code == 400


def test_verbandsmeldung_zahlen_und_namentlich(api, club, chef, partner):
    with rls_bypass(), tenant_context(club.pk):
        gemeldet = MemberType.objects.create(
            organization=club, name="Schütze", active=True, reported=True
        )
        still = MemberType.objects.create(
            organization=club, name="Fördermitglied", active=False, reported=False
        )
    make_member(club, "Erika", "Muster", member_type=gemeldet)
    make_member(club, "Max", "Beispiel", member_type=still)
    zahlen = create(api, chef, club, scopes=["verbandsmeldung.lesen"])
    assert zahlen.status_code == 201, zahlen.content
    response = call(zahlen.json()["key"], "federation-report/")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["level"] == "a" and data["total"] == 1 and "persons" not in data
    assert data["counts"] == [{"kind": "active", "birth_month": "1980-05", "count": 1}]
    assert "Muster" not in response.content.decode()
    assert call(zahlen.json()["key"], "federation-report/?date=kein-datum").status_code == 400
    # Namentlich nur mit Empfänger und Rechtsgrundlage
    fields = {"scopes": ["verbandsmeldung.lesen"], "report_level": "b"}
    assert create(api, chef, club, **fields).status_code == 400
    named = create(api, chef, club, **personal(partner, legal_basis="transfer", **fields))
    assert named.status_code == 201, named.content
    data = call(named.json()["key"], "federation-report/").json()
    assert data["level"] == "b" and [p["last_name"] for p in data["persons"]] == ["Muster"]
    assert data["persons"][0]["member_type"] == "Schütze"
    assert "contact" not in data["persons"][0] and "street" not in json.dumps(data)
    with rls_bypass(), tenant_context(club.pk):
        # Übermittlung an einen eigenen Verantwortlichen: kein Auftragsverarbeiter
        assert "processor" not in BusinessPartner.objects.get(pk=partner.pk).roles
        assert ReadLog.objects.filter(scope="verbandsmeldung.lesen").count() == 1


def test_ehrungen_und_qualifikationen(api, club, chef, partner):
    erika = make_member(club, "Erika", "Muster")
    with rls_bypass(), tenant_context(club.pk):
        title = HonoraryTitle.objects.create(organization=club, name="Ehrenmitglied")
        HonoraryTitleAward.objects.create(
            organization=club,
            person_id=erika.person_id,
            title=title,
            valid_from=datetime.date(2020, 1, 1),
            note="vertraulich",
        )
        leiter = QualificationType.objects.create(organization=club, name="Jugendleiter")
        zeugnis = QualificationType.objects.create(
            organization=club, name="Führungszeugnis", inspection_only=True
        )
        for kind in (leiter, zeugnis):
            Qualification.objects.create(
                organization=club,
                person_id=erika.person_id,
                kind=kind,
                acquired_on=datetime.date(2023, 5, 1),
                note="vertraulich",
            )
    scopes = ["mitglieder.lesen", "ehrungen.lesen", "qualifikationen.lesen"]
    key = create(api, chef, club, **personal(partner, scopes=scopes)).json()["key"]
    member = call(key, "members/").json()["members"][0]
    honors = call(key, "honors/")
    assert honors.status_code == 200, honors.content
    rows = honors.json()["honors"]
    assert [(r["honor"], r["last_name"], r["valid_from"]) for r in rows] == [
        ("Ehrenmitglied", "Muster", "2020-01-01")
    ]
    assert rows[0]["member"] == member["id"] and "vertraulich" not in honors.content.decode()
    response = call(key, "qualifications/")
    assert response.status_code == 200, response.content
    quals = response.json()["qualifications"]
    # Arten mit bloßem Einsichtsvermerk (Führungszeugnis) gehen nie nach außen
    assert [q["qualification"] for q in quals] == ["Jugendleiter"]
    assert quals[0]["member"] == member["id"]
    assert "vertraulich" not in response.content.decode()


# --- Benachrichtigungen ---


def hooked(api, chef, club, partner, **fields):
    body = personal(
        partner,
        scopes=["mitglieder.lesen", "termine.lesen"],
        webhook_url=HOOK,
        webhook_events=["member.created", "member.changed", "member.left", "event.created"],
        **fields,
    )
    return create(api, chef, club, **body)


def pending():
    with rls_bypass():
        return list(WebhookDelivery.objects.order_by("pk").values_list("event", flat=True))


def test_benachrichtigung_geheimnis_einmal_und_adresse_geprueft(api, club, chef, partner):
    bad = create(api, chef, club, **personal(partner, webhook_url="http://verband.example.org/x"))
    assert bad.status_code == 400 and "webhook_url" in bad.content.decode()
    made = hooked(api, chef, club, partner)
    assert made.status_code == 201, made.content
    data = made.json()
    assert data["webhook_secret"].startswith("hpw_") and data["webhook_state"] == "ok"
    listing = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()
    assert "webhook_secret" not in listing["accesses"][0]
    assert data["webhook_secret"] not in json.dumps(listing)
    # Ereignisse ohne passenden Bereich fallen weg
    nur = create(
        api,
        chef,
        club,
        scopes=["termine.lesen"],
        webhook_url=HOOK,
        webhook_events=["member.changed", "event.created"],
    ).json()
    assert nur["webhook_events"] == ["event.created"]
    again = api(chef).post(f"/api/orgs/{club.pk}/api-accesses/{data['id']}/webhook-secret/")
    assert again.status_code == 200 and again.json()["webhook_secret"] != data["webhook_secret"]


def test_benachrichtigung_schlank_unterschrieben_und_wiederholt(
    api, club, chef, partner, monkeypatch
):
    made = hooked(api, chef, club, partner).json()
    secret = made["webhook_secret"]
    assert pending() == []
    erika = make_member(club, "Erika", "Muster")
    events = pending()
    # „geändert“ gleich nach „angelegt“ ergibt eine einzige Nachricht
    assert events == ["member.created"]
    sent: list[dict] = []
    answers = [503, 200]

    def fake(method, url, *, headers=None, body=None, **kwargs):
        sent.append({"method": method, "url": url, "headers": headers, "body": body})
        return safehttp.Response(status=answers[len(sent) - 1], headers={}, body=b"")

    monkeypatch.setattr(safehttp, "request", fake)
    assert webhooks.deliver_due() == 0
    with rls_bypass():
        delivery = WebhookDelivery.objects.get()
        access = ApiAccess.objects.get(pk=made["id"])
    assert delivery.attempts == 1 and delivery.last_error == "HTTP 503"
    assert delivery.next_try_at > timezone.now() and access.webhook_failing_since is not None
    shown = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()["accesses"][0]
    assert shown["webhook_state"] == "failing" and shown["webhook_last_error"] == "HTTP 503"
    # Noch nicht wieder fällig
    assert webhooks.deliver_due() == 0 and len(sent) == 1
    with rls_bypass():
        WebhookDelivery.objects.update(next_try_at=timezone.now())
    assert webhooks.deliver_due() == 1
    with rls_bypass():
        assert WebhookDelivery.objects.get().delivered_at is not None
        assert ApiAccess.objects.get(pk=made["id"]).webhook_failing_since is None
    last = sent[-1]
    assert last["method"] == "POST" and last["url"] == HOOK
    body = json.loads(last["body"])
    member = call(made["key"], "members/").json()["members"][0]
    assert body["type"] == "member.created" and body["unit"] == str(club.uuid)
    assert body["object"] == {"type": "member", "id": member["id"]}
    # Schlank: keine Inhalte, nie die interne Nummer
    assert "Muster" not in last["body"].decode() and str(erika.person_id) != body["object"]["id"]
    assert set(body) == {"id", "type", "occurred_at", "unit", "object"}
    assert last["headers"]["X-HUBIplan-Event"] == "member.created"
    stamp, digest = (
        part.split("=", 1)[1] for part in last["headers"]["X-HUBIplan-Signature"].split(",")
    )
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + last["body"], hashlib.sha256)
    assert digest == expected.hexdigest()
    # Austritt
    leave(club, erika, timezone.localdate())
    assert "member.left" in pending()


def test_benachrichtigung_nur_was_der_zugang_sehen_darf(api, club, chef, partner):
    from events.models import Event

    hooked(api, chef, club, partner)
    start = timezone.now() + datetime.timedelta(days=3)
    with rls_bypass():
        for title, visibility in (("Fest", "public"), ("Intern", "members"), ("Sitzung", "board")):
            Event.objects.create(
                organization=club,
                title=title,
                starts_at=start,
                ends_at=start + datetime.timedelta(hours=1),
                visibility=visibility,
            )
    # Ohne „termine.mitglieder“ nur der öffentliche Termin
    assert pending() == ["event.created"]


def test_benachrichtigung_ruht_nach_sieben_tagen_und_probe(api, club, chef, partner, monkeypatch):
    made = hooked(api, chef, club, partner).json()
    make_member(club, "Erika", "Muster")
    with rls_bypass():
        ApiAccess.objects.filter(pk=made["id"]).update(
            webhook_failing_since=timezone.now() - datetime.timedelta(days=8)
        )

    def down(*args, **kwargs):
        raise safehttp.SafeHTTPError("nicht erreichbar")

    monkeypatch.setattr(safehttp, "request", down)
    mail.outbox.clear()
    assert webhooks.deliver_due() == 0
    shown = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()["accesses"][0]
    assert shown["webhook_state"] == "paused"
    assert any("ruhen" in m.subject for m in mail.outbox)
    url = f"/api/orgs/{club.pk}/api-accesses/{made['id']}/"
    test = api(chef).post(url + "webhook-test/")
    assert test.status_code == 200 and test.json() == {"ok": False, "error": "nicht erreichbar"}
    resumed = api(chef).patch(url, json.dumps({"webhook_resume": True}), JSON)
    assert resumed.status_code == 200 and resumed.json()["webhook_state"] == "ok"


def test_protokoll_wird_nach_90_tagen_geloescht(api, club, chef, partner):
    from partnerapi.tasks import purge_logs

    make_member(club, "Erika", "Muster")
    key = create(api, chef, club, **personal(partner)).json()["key"]
    call(key, "members/")
    call(key, "members/")
    with rls_bypass():
        first = ReadLog.objects.order_by("pk").first()
        ReadLog.objects.filter(pk=first.pk).update(at=timezone.now() - datetime.timedelta(days=91))
    assert purge_logs() == 1
    with rls_bypass():
        assert ReadLog.objects.count() == 1


def test_verzeichnis_nennt_die_weitergabe(club):
    from privacy.catalog import suggestions

    assert "api" in {a.key for a in suggestions(club)}
