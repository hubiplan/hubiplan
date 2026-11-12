"""Online-Mitgliedsantrag (konzepte/online-beitrittsformular.md, B1–B5). Alles erfunden."""

import datetime

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from access.models import Role, RoleAssignment
from admission import services
from admission.models import Application, ApplicationForm, KioskLink
from core.tenancy import rls_bypass, tenant_context
from members.models import ContactPerson, Membership, MemberType
from website import contact

from .factories import give_role, make_user
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db(transaction=True)

IBAN = "DE89370400440532013000"


@pytest.fixture(autouse=True)
def leichte_aufgabe(monkeypatch, settings, tmp_path):
    monkeypatch.setattr(contact, "MIN_SECONDS", 0)
    monkeypatch.setattr(contact, "DIFFICULTY", 4)
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def club(orgs, board_a, api):
    org = orgs["a"]
    org.enabled_modules = sorted({*(org.enabled_modules or []), "members", "billing", "website"})
    org.save()
    with tenant_context(org.pk):
        aktiv = MemberType.objects.create(organization=org, name="Aktiv", active=True)
        foerder = MemberType.objects.create(organization=org, name="Fördernd", active=False)
        from billing.models import FeeRate
        from billing.services import settings_for

        FeeRate.objects.create(organization=org, member_type=aktiv, amount="36.00")
        cfg = settings_for(org)
        cfg.sepa_enabled = True
        cfg.creditor_id = "DE98ZZZ09999999999"
        cfg.save()
    c = api(board_a)
    res = c.patch(
        f"/api/orgs/{org.pk}/admission/form/",
        {
            "enabled": True,
            "types": [
                {"id": aktiv.pk, "label": {"de": "Aktiv im Zug", "en": "Active"}},
                {"id": foerder.pk, "organizations": True},
            ],
            "fields": {"phone": "optional", "birth_date": "optional", "note": "optional"},
            "consents": ["club_photo", "club_photo", "photo"],
            "texts": {"intro": {"de": "Willkommen!", "en": "Welcome!"}},
        },
        "application/json",
    )
    assert res.status_code == 200, res.content
    key = res.json()["public_key"]
    return {"org": org, "aktiv": aktiv, "foerder": foerder, "key": key, "client": c}


def schema(key, **params):
    res = Client().get(f"/api/public/join/{key}/", params)
    assert res.status_code == 200, res.content
    return res.json()


def submit(key, **extra):
    data = schema(key)
    ch = data["challenge"]
    body = {
        "member_type": data["types"][0]["id"],
        "last_name": "Muster",
        "first_name": "Max",
        "email": "max.muster@example.org",
        "street": "Beispielweg 5",
        "postal_code": "12345",
        "city": "Musterstadt",
        "birth_date": "1990-05-01",
        "confirmations": ["privacy", "mandate"],
        "challenge": ch["token"],
        "nonce": contact.solve(ch["salt"], ch["difficulty"]),
        **extra,
    }
    return Client().post(f"/api/public/join/{key}/", body, "application/json")


def token_from_mail(message) -> str:
    for word in message.body.split():
        if "/antrag/" in word:
            return word.split("/antrag/")[1].split("?")[0]
    raise AssertionError("kein Link")


def app_of(org) -> Application:
    with rls_bypass():
        return Application.objects.filter(organization=org).latest("pk")


def submit_and_confirm(club, **extra) -> tuple[Application, str]:
    mail.outbox.clear()
    res = submit(club["key"], **extra)
    assert res.status_code == 201, res.content
    token = token_from_mail(mail.outbox[-1])
    res = Client().post(f"/api/public/join/application/{token}/confirm/")
    assert res.status_code == 200, res.content
    return app_of(club["org"]), token


def approve(c, base, decision="approve", **extra):
    return c.post(f"{base}approve/", {"decision": decision, **extra}, "application/json")


def member_client(org, email, *roles):
    """Konto mit den Rollen und Leserecht für Mitglieder (zum Zustimmen)."""
    u = make_user(email)
    for r in roles:
        RoleAssignment.objects.create(
            organization=org, role=r, user=u, valid_from=datetime.date(2020, 1, 1)
        )
    give_role(u, org, permissions=["members.view"], name=f"Lesen {email}")
    c = Client()
    c.force_login(u)
    return c


class TestFormular:
    def test_aufbau(self, club):
        data = schema(club["key"])
        assert data["intro"] == "Willkommen!"
        assert [t["label"] for t in data["types"]] == ["Aktiv im Zug", "Fördernd"]
        assert data["types"][0]["fee"] == "36,00"
        assert data["sepa"] == "offer"
        assert "DE98ZZZ09999999999" in data["mandate"]["text"]
        assert [c["key"] for c in data["consents"]] == ["club_photo", "photo"]
        assert data["challenge"]["token"]
        assert schema(club["key"], lang="en")["types"][0]["label"] in ("Active", "Aktiv im Zug")

    def test_aus_heisst_404(self, club):
        form = ApplicationForm.objects.get(organization=club["org"])
        form.enabled = False
        form.save()
        assert Client().get(f"/api/public/join/{club['key']}/").status_code == 404

    def test_pflichtfelder_und_art(self, club):
        res = submit(club["key"], member_type=999999, first_name="")
        assert res.status_code == 400
        assert {"member_type", "first_name"} <= set(res.json())
        res = submit(club["key"], confirmations=[])
        assert res.status_code == 400 and "confirmations" in res.json()

    def test_organisation_nur_bei_freigegebener_art(self, club):
        res = submit(club["key"], kind="organization", first_name="")
        assert res.status_code == 400 and "kind" in res.json()
        res = submit(
            club["key"], kind="organization", first_name="", member_type=club["foerder"].pk
        )
        assert res.status_code == 201, res.content

    def test_honigtopf_still(self, club):
        res = submit(club["key"], homepage="https://spam.example")
        assert res.status_code == 201
        with rls_bypass():
            assert not Application.objects.exists()

    def test_aufgabe_nur_einmal(self, club):
        data = schema(club["key"])
        ch = data["challenge"]
        body = {
            "member_type": data["types"][0]["id"],
            "last_name": "Muster",
            "first_name": "Max",
            "email": "max@example.org",
            "street": "Weg 1",
            "postal_code": "12345",
            "city": "Musterstadt",
            "confirmations": ["privacy"],
            "challenge": ch["token"],
            "nonce": contact.solve(ch["salt"], ch["difficulty"]),
        }
        url = f"/api/public/join/{club['key']}/"
        assert Client().post(url, body, "application/json").status_code == 201
        assert Client().post(url, body, "application/json").status_code == 400


class TestAblauf:
    def test_bestaetigen_annehmen_mit_mandat(self, club, board_a):
        res = submit(
            club["key"],
            mandate={"holder": "Max Muster", "iban": IBAN},
            consents=["club_photo"],
            phone="0123 456",
        )
        assert res.status_code == 201, res.content
        app = app_of(club["org"])
        assert app.status == "unconfirmed"
        # Unbestätigt sieht der Vorstand nichts
        listed = club["client"].get(f"/api/orgs/{club['org'].pk}/admission/").json()
        assert listed["results"] == []
        token = token_from_mail(mail.outbox[-1])
        mail.outbox.clear()
        res = Client().post(f"/api/public/join/application/{token}/confirm/")
        assert res.json()["status"] == "open"
        subjects = [m.subject for m in mail.outbox]
        assert any("eingegangen" in s for s in subjects)
        assert any("Neuer Mitgliedsantrag" in s for s in subjects)
        assert IBAN not in "".join(m.body for m in mail.outbox)

        c = club["client"]
        base = f"/api/orgs/{club['org'].pk}/admission/"
        listed = c.get(base).json()["results"]
        assert [r["name"] for r in listed] == ["Max Muster"]
        detail = c.get(f"{base}{app.pk}/").json()
        assert detail["mandate"]["iban"].endswith("3000") and IBAN not in str(detail)
        assert detail["may_decide"] is True
        mail.outbox.clear()
        res = c.post(f"{base}{app.pk}/accept/", {"invite": False}, "application/json")
        assert res.status_code == 200, res.content
        assert res.json()["status"] == "accepted"
        app.refresh_from_db()
        assert app.mandate == {}
        with tenant_context(club["org"].pk):
            membership = Membership.objects.get(pk=app.membership_id)
            assert membership.person.last_name == "Muster"
            assert membership.photo_consent_source == "member"
            from billing.models import Mandate

            mandate = Mandate.objects.get(membership=membership)
            assert mandate.source == "application" and mandate.iban == IBAN
        assert any("Willkommen" in m.subject for m in mail.outbox)

    def test_zurueckziehen_und_loeschen(self, club):
        app, token = submit_and_confirm(club)
        res = Client().post(f"/api/public/join/application/{token}/withdraw/")
        assert res.json()["status"] == "withdrawn"
        app.refresh_from_db()
        assert app.purge_after > timezone.localdate()
        services.purge(timezone.now() + datetime.timedelta(days=400))
        with rls_bypass():
            assert not Application.objects.filter(pk=app.pk).exists()

    def test_unbestaetigt_nach_48_stunden_weg(self, club):
        submit(club["key"])
        app = app_of(club["org"])
        services.purge(timezone.now() + datetime.timedelta(hours=47))
        with rls_bypass():
            assert Application.objects.filter(pk=app.pk).exists()
        services.purge(timezone.now() + datetime.timedelta(hours=49))
        with rls_bypass():
            assert not Application.objects.filter(pk=app.pk).exists()

    def test_ablehnen_mit_mail(self, club):
        app, _ = submit_and_confirm(club)
        mail.outbox.clear()
        base = f"/api/orgs/{club['org'].pk}/admission/{app.pk}/"
        res = club["client"].post(
            f"{base}reject/", {"note": "Satzung", "send_mail": True}, "application/json"
        )
        assert res.json()["status"] == "rejected"
        assert len(mail.outbox) == 1 and "leider" in mail.outbox[0].body

    def test_rueckfrage(self, club, board_a):
        app, _ = submit_and_confirm(club)
        mail.outbox.clear()
        base = f"/api/orgs/{club['org'].pk}/admission/{app.pk}/"
        res = club["client"].post(f"{base}ask/", {"text": "Welcher Zug?"}, "application/json")
        assert res.json()["status"] == "query"
        assert mail.outbox[0].reply_to == [board_a.email]
        assert club["client"].post(f"{base}resume/").json()["status"] == "open"

    def test_korrektur_setzt_zustimmungen_zurueck(self, club, orgs):
        org = club["org"]
        chair = Role.objects.create(organization=org, name="1. Vorsitzender", permissions=[])
        sec = Role.objects.create(organization=org, name="Schriftführer", permissions=[])
        club["client"].patch(
            f"/api/orgs/{org.pk}/admission/form/",
            {"rule": {"mode": "rule", "roles": [chair.pk, sec.pk]}},
            "application/json",
        )
        app, _ = submit_and_confirm(club)
        c1 = member_client(org, "vorsitz@example.org", chair)
        base = f"/api/orgs/{org.pk}/admission/{app.pk}/"
        assert (
            c1.post(f"{base}approve/", {"decision": "approve"}, "application/json").status_code
            == 200
        )
        club["client"].patch(base, {"city": "Neustadt"}, "application/json")
        assert app.approvals.count() == 0


class TestZustimmungen:
    def setup_rule(self, club, **rule):
        org = club["org"]
        chair = Role.objects.create(organization=org, name="1. Vorsitzender", permissions=[])
        sec = Role.objects.create(organization=org, name="Schriftführer", permissions=[])
        res = club["client"].patch(
            f"/api/orgs/{org.pk}/admission/form/",
            {"rule": {"mode": "rule", "roles": [chair.pk, sec.pk], **rule}},
            "application/json",
        )
        assert res.status_code == 200, res.content
        return chair, sec

    def person(self, org, email, *roles):
        return member_client(org, email, *roles)

    def test_beide_rollen_noetig(self, club):
        org = club["org"]
        chair, sec = self.setup_rule(club)
        app, _ = submit_and_confirm(club)
        base = f"/api/orgs/{org.pk}/admission/{app.pk}/"
        c = club["client"]
        assert c.post(f"{base}accept/").status_code == 400
        vorsitz = self.person(org, "v@example.org", chair)
        assert (
            vorsitz.post(f"{base}approve/", {"decision": "approve"}, "application/json").status_code
            == 200
        )
        detail = c.get(base).json()
        assert detail["approvals_met"] is False and "Schriftführer" in detail["missing"]
        schrift = self.person(org, "s@example.org", sec)
        schrift.post(f"{base}approve/", {"decision": "approve"}, "application/json")
        assert c.get(base).json()["approvals_met"] is True
        assert c.post(f"{base}accept/").json()["status"] == "accepted"

    def test_eine_person_deckt_nicht_zwei_rollen(self, club):
        org = club["org"]
        chair, sec = self.setup_rule(club)
        app, _ = submit_and_confirm(club)
        base = f"/api/orgs/{org.pk}/admission/{app.pk}/"
        beide = self.person(org, "beide@example.org", chair, sec)
        beide.post(f"{base}approve/", {"decision": "approve"}, "application/json")
        assert club["client"].get(base).json()["approvals_met"] is False

    def test_fremde_duerfen_nicht_zustimmen(self, club):
        org = club["org"]
        self.setup_rule(club)
        app, _ = submit_and_confirm(club)
        base = f"/api/orgs/{org.pk}/admission/{app.pk}/"
        fremd = self.person(org, "f@example.org")
        res = fremd.post(f"{base}approve/", {"decision": "approve"}, "application/json")
        assert res.status_code == 400

    def test_ablehnung_haelt_an_und_automatisch_aufnehmen(self, club):
        org = club["org"]
        chair, sec = self.setup_rule(club, auto_admit=True)
        app, _ = submit_and_confirm(club)
        base = f"/api/orgs/{org.pk}/admission/{app.pk}/"
        vorsitz = self.person(org, "v@example.org", chair)
        schrift = self.person(org, "s@example.org", sec)
        res = vorsitz.post(f"{base}approve/", {"decision": "reject"}, "application/json")
        assert res.status_code == 400  # Ablehnung braucht eine Begründung
        vorsitz.post(
            f"{base}approve/", {"decision": "reject", "note": "kennt keiner"}, "application/json"
        )
        schrift.post(f"{base}approve/", {"decision": "approve"}, "application/json")
        detail = club["client"].get(base).json()
        assert detail["disputed"] is True and detail["status"] == "open"
        # Meinung geändert: letzte Zustimmung nimmt automatisch auf
        res = vorsitz.post(f"{base}approve/", {"decision": "approve"}, "application/json")
        assert res.json()["status"] == "accepted"

    def test_versammlung_braucht_beschluss(self, club):
        org = club["org"]
        club["client"].patch(
            f"/api/orgs/{org.pk}/admission/form/",
            {"rule": {"mode": "assembly"}},
            "application/json",
        )
        app, _ = submit_and_confirm(club)
        base = f"/api/orgs/{org.pk}/admission/{app.pk}/"
        assert club["client"].post(f"{base}accept/").status_code == 400
        res = club["client"].post(f"{base}accept/", {"note": "JHV vom 01.03."}, "application/json")
        assert res.json()["status"] == "accepted"


class TestMinderjaehrige:
    def test_ohne_erziehungsberechtigte_abgelehnt(self, club):
        res = submit(club["key"], birth_date=f"{timezone.localdate().year - 10}-01-01")
        assert res.status_code == 400 and "guardians" in res.json()

    def test_mit_erziehungsberechtigten(self, club):
        mail.outbox.clear()
        res = submit(
            club["key"],
            birth_date=f"{timezone.localdate().year - 10}-01-01",
            guardians=[
                {"last_name": "Muster", "first_name": "Maria", "email": "maria@example.org"}
            ],
            confirmations=["privacy", "guardian"],
        )
        assert res.status_code == 201, res.content
        assert mail.outbox[-1].to == ["maria@example.org"]
        token = token_from_mail(mail.outbox[-1])
        Client().post(f"/api/public/join/application/{token}/confirm/")
        app = app_of(club["org"])
        club["client"].post(f"/api/orgs/{club['org'].pk}/admission/{app.pk}/accept/")
        app.refresh_from_db()
        with tenant_context(club["org"].pk):
            cp = ContactPerson.objects.get(membership_id=app.membership_id)
            assert cp.first_name == "Maria" and cp.is_primary

    def test_mindestalter(self, club):
        club["client"].patch(
            f"/api/orgs/{club['org'].pk}/admission/form/", {"min_age": 16}, "application/json"
        )
        res = submit(
            club["key"],
            birth_date=f"{timezone.localdate().year - 10}-01-01",
            guardians=[{"last_name": "M", "first_name": "M", "email": "m@example.org"}],
            confirmations=["privacy", "guardian"],
        )
        assert res.status_code == 400 and "birth_date" in res.json()


class TestUnterschrift:
    def strokes(self):
        return {"width": 600, "height": 200, "strokes": [[[10, 10], [300, 150], [590, 20]]]}

    def test_nachreichen_und_pdf(self, club):
        club["client"].patch(
            f"/api/orgs/{club['org'].pk}/admission/form/",
            {"signature": "required"},
            "application/json",
        )
        app, token = submit_and_confirm(club)
        assert app.status == "unsigned"
        pdf = Client().get(f"/api/public/join/application/{token}/pdf/")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        res = Client().post(
            f"/api/public/join/application/{token}/sign/",
            {"signature": self.strokes()},
            "application/json",
        )
        assert res.json()["status"] == "open" and res.json()["signed"] is True
        pdf = club["client"].get(f"/api/orgs/{club['org'].pk}/admission/{app.pk}/pdf/")
        assert pdf.content.startswith(b"%PDF")

    def test_papier_eingegangen(self, club):
        club["client"].patch(
            f"/api/orgs/{club['org'].pk}/admission/form/",
            {"signature": "required"},
            "application/json",
        )
        app, _ = submit_and_confirm(club)
        res = club["client"].post(f"/api/orgs/{club['org'].pk}/admission/{app.pk}/signed/")
        assert res.json()["status"] == "open"


class TestStand:
    def test_stand_ohne_bestaetigung(self, club):
        org = club["org"]
        res = club["client"].post(
            f"/api/orgs/{org.pk}/admission/kiosk/",
            {"label": "Schützenfest", "hours": 8},
            "application/json",
        )
        assert res.status_code == 201, res.content
        token = res.json()["url"].rsplit("/", 1)[1]
        data = Client().get(f"/api/public/join/kiosk/{token}/").json()
        assert data["kiosk"] == "Schützenfest"
        mail.outbox.clear()
        res = Client().post(
            f"/api/public/join/kiosk/{token}/",
            {
                "member_type": data["types"][0]["id"],
                "last_name": "Stand",
                "first_name": "Sina",
                "email": "sina@example.org",
                "street": "Platz 1",
                "postal_code": "12345",
                "city": "Musterstadt",
                "confirmations": ["privacy"],
            },
            "application/json",
        )
        assert res.status_code == 201, res.content
        assert set(res.json()) == {"status", "number"}
        app = app_of(org)
        assert app.status == "open" and app.source == "kiosk"
        link = KioskLink.objects.get(organization=org)
        club["client"].delete(f"/api/orgs/{org.pk}/admission/kiosk/{link.pk}/")
        assert Client().get(f"/api/public/join/kiosk/{token}/").status_code == 404


class TestEinbindung:
    def test_fremder_verein_sieht_nichts(self, club, orgs, board_b, api):
        app, _ = submit_and_confirm(club)
        other = api(board_b)
        assert other.get(f"/api/orgs/{club['org'].pk}/admission/").status_code == 404
        with as_app_role(), tenant_context(orgs["b"].pk):
            assert not Application.objects.filter(pk=app.pk).exists()

    def test_zu_erledigen(self, club):
        app, _ = submit_and_confirm(club)
        items = club["client"].get(f"/api/orgs/{club['org'].pk}/open-tasks/").json()["items"]
        found = [i for i in items if i["kind"] == "application"]
        assert found and found[0]["link"] == f"/mitglieder/antraege/{app.pk}"

    def test_webseite_baustein_und_seite(self, club):
        from website.models import Website

        org = club["org"]
        site = Website.objects.create(organization=org, public_key="seite-a", state="public")
        info = Client().get("/api/public/site/v1/seite-a/").json()
        assert info["blocks"]["join"] is True
        data = Client().get("/api/public/site/v1/seite-a/join/").json()
        assert data["form_url"].endswith(f"/mitglied-werden/{club['key']}")
        assert data["types"][0]["fee"] == "36,00"
        form = ApplicationForm.objects.get(organization=org)
        form.enabled = False
        form.save()
        site.refresh_from_db()
        assert Client().get("/api/public/site/v1/seite-a/").json()["blocks"]["join"] is False
        assert Client().get("/api/public/site/v1/seite-a/join/").status_code == 404

    def test_qr_code(self, club):
        res = club["client"].get(f"/api/orgs/{club['org'].pk}/admission/qr/")
        assert res.status_code == 200 and b"<svg" in res.content
