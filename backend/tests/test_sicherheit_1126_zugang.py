"""Sicherheitsprüfung 26.11.2026, Paket 1: Anmeldung, Rechte, Mitgliederbereich, Verbund."""

# ruff: noqa: F811  (Fixtures als Parameter)
from __future__ import annotations

import datetime
import io

import pytest
from django.test import RequestFactory
from django.utils import timezone

from accounts.mfa import encrypt
from accounts.models import User
from core import safehttp
from core.tenancy import rls_bypass, tenant_context
from devices import devicekey
from members.models import ContactPerson, DepartmentRoleHolder
from organizations.models import Department, DepartmentRole
from portal.models import PortalAccess
from portal.services import department_contexts

from .factories import give_portal_access, give_role, make_member, make_user
from .test_nextcloud_anmeldung import make_client
from .test_partnerapi import chef, club, create  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _totp(user):
    from allauth.mfa.models import Authenticator

    return Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={})


# --- A-H01: Zwei-Faktor-Anmeldung nur zurücksetzen, wenn das Konto allein hierher gehört ---


@pytest.mark.parametrize("fremd", ["mitgliederbereich", "kuenftige_rolle"])
def test_reset_mfa_nicht_bei_zugang_in_anderem_verein(orgs, api, board_a, fremd):
    from allauth.mfa.models import Authenticator

    ziel = make_user("ziel@example.org")
    if fremd == "mitgliederbereich":
        mitglied = make_member(orgs["b"], "Zoe", "Ziel")
        give_portal_access(orgs["b"], mitglied, ziel)
    else:
        morgen = timezone.localdate() + datetime.timedelta(days=30)
        give_role(ziel, orgs["b"], valid_from=morgen)
    zuordnung = give_role(ziel, orgs["a"], name="Beisitz")
    _totp(ziel)
    _totp(board_a)
    board = User.objects.get(pk=board_a.pk)
    resp = api(board).post(f"/api/orgs/{orgs['a'].pk}/assignments/{zuordnung.pk}/reset-mfa/")
    assert resp.status_code == 400, resp.json()
    assert "Plattform" in resp.json()["detail"]
    assert Authenticator.objects.filter(user=ziel).exists()


def test_reset_mfa_mit_mitgliederzugang_im_eigenen_verein(orgs, api, board_a):
    from allauth.mfa.models import Authenticator

    ziel = make_user("eigen@example.org")
    mitglied = make_member(orgs["a"], "Emil", "Eigen")
    give_portal_access(orgs["a"], mitglied, ziel)
    zuordnung = give_role(ziel, orgs["a"], name="Beisitz")
    _totp(ziel)
    _totp(board_a)
    board = User.objects.get(pk=board_a.pk)
    resp = api(board).post(f"/api/orgs/{orgs['a'].pk}/assignments/{zuordnung.pk}/reset-mfa/")
    assert resp.status_code == 200, resp.json()
    assert not Authenticator.objects.filter(user=ziel).exists()


# --- A-H03: App-Passwort der Nextcloud wandert nie an eine andere Adresse ---


def test_nextcloud_adresse_aendern_verwirft_app_passwort(api, orgs, board_a):
    client, _ = make_client(
        orgs["a"],
        service_user="hubiplan-dienst",
        service_password=encrypt("app-passwort", purpose="nextcloud"),
    )
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/"
    # Gleiche Adresse: das Passwort bleibt
    resp = api(board_a).patch(url, {"base_url": client.base_url}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    client.refresh_from_db()
    assert client.service_password
    resp = api(board_a).patch(
        url, {"base_url": "https://fremd.example.net", "service_password": ""}, content_type=JSON
    )
    assert resp.status_code == 200, resp.content
    client.refresh_from_db()
    assert client.base_url.startswith("https://fremd.example.net")
    assert client.service_password == "" and not resp.json()["has_service_password"]


# --- A-H05: Ansprechpartner erben keine Ämter und sehen Rechnungen nur mit Freigabe ---


@pytest.fixture
def ansprechpartner(orgs):
    club = orgs["a"]
    club.department_access_enabled = True
    club.member_portal_enabled = True
    club.save()
    with rls_bypass(), tenant_context(club.pk):
        dept = Department.objects.create(organization=club, name="Zug 1", self_managed=True)
        mitglied = make_member(club, "Maria", "Muster", departments=[dept])
        role = DepartmentRole.objects.create(
            organization=club, department=dept, name="Leitung", permissions=["roles.edit"]
        )
        DepartmentRoleHolder.objects.create(
            organization=club,
            membership=mitglied,
            role=role,
            valid_from=datetime.date(2020, 1, 1),
        )
        kontakt = ContactPerson.objects.create(
            organization=club,
            membership=mitglied,
            last_name="Beispiel",
            first_name="Bernd",
            receives_invoices=False,
            represents=False,
            member_access=True,
        )
        user = make_user("ansprech@example.org")
        access = PortalAccess.objects.create(
            organization=club, membership=mitglied, contact_person=kontakt, user=user
        )
    return {"user": user, "access": access, "dept": dept, "kontakt": kontakt, "mitglied": mitglied}


def test_ansprechpartner_erbt_kein_amt_der_untereinheit(ansprechpartner):
    assert department_contexts(ansprechpartner["user"]) == {}
    # Das Mitglied selbst behält seine Rechte
    selbst = make_user("maria@example.org")
    with rls_bypass():
        PortalAccess.objects.create(
            organization=ansprechpartner["access"].organization,
            membership=ansprechpartner["mitglied"],
            user=selbst,
        )
    assert ansprechpartner["dept"].pk in department_contexts(selbst)


def test_ansprechpartner_ohne_rechnungsfreigabe(api, ansprechpartner):
    c = api(ansprechpartner["user"])
    base = f"/api/portal/{ansprechpartner['access'].pk}"
    resp = c.get(f"{base}/invoices/")
    assert resp.status_code == 200 and resp.json() == {"invoices": [], "collective": []}
    mandat = c.get(f"{base}/mandate/")
    assert mandat.status_code == 200 and mandat.json()["available"] is False
    assert mandat.json()["mandate"] is None
    assert c.post(f"{base}/mandate/", {}, content_type=JSON).status_code == 403
    assert c.delete(f"{base}/mandate/").status_code == 403
    assert c.post(f"{base}/cancellation/", {}, content_type=JSON).status_code == 403


# --- A-M05, A-L: kleinere Härtungen ---


def test_safehttp_sperrt_lokales_nat64_und_multicast():
    assert not safehttp.is_public("64:ff9b:1::192.0.2.1")
    assert not safehttp.is_public("224.0.0.1")
    assert not safehttp.is_public("ff02::1")
    assert safehttp.is_public("93.184.216.34")


def test_signierter_rumpf_begrenzt_und_laenge_geprueft():
    rf = RequestFactory()
    req = rf.post("/api/app/v1/admin/u/1/", data=b"abc", content_type="application/octet-stream")
    req.META["CONTENT_LENGTH"] = "keine-zahl"
    with pytest.raises(devicekey.BodyTooLarge):
        devicekey.request_body(req)
    req = rf.post("/api/app/v1/admin/u/1/", data=b"x" * 10, content_type="application/octet-stream")
    req.META["CONTENT_LENGTH"] = str(devicekey.MAX_SIGNED_BODY + 1)
    with pytest.raises(devicekey.BodyTooLarge):
        devicekey.request_body(req)
    # Ohne Längenangabe (stückweise gesendet) wird trotzdem nicht unbegrenzt gelesen
    req = rf.post("/api/app/v1/admin/u/1/", data=b"", content_type="application/octet-stream")
    req._stream = io.BytesIO(b"a" * (devicekey.MAX_SIGNED_BODY + 5))
    req.META["CONTENT_LENGTH"] = "0"
    with pytest.raises(devicekey.BodyTooLarge):
        devicekey.request_body(req)


def test_einladung_gilt_nicht_ueber_abmeldung_ueberall_hinaus():
    from accounts.tokens import InvitationTokenGenerator, _LegacyInvitationTokenGenerator

    user = make_user("neu@example.org")
    user.set_unusable_password()
    user.save()
    gen = InvitationTokenGenerator()
    token = gen.make_token(user)
    alt = _LegacyInvitationTokenGenerator().make_token(user)
    assert gen.check_token(user, token)
    # Einladungen aus der Fassung davor bleiben in ihrer Frist gültig
    assert gen.check_token(user, alt)
    User.objects.filter(pk=user.pk).update(auth_version=user.auth_version + 1)
    user.refresh_from_db()
    assert not gen.check_token(user, token)


# --- A-M03: Partner-Schnittstelle weiter öffnen nur mit frischem zweiten Faktor ---


def test_partnerzugang_oeffnen_braucht_frische_bestaetigung(api, club, chef, settings):
    from partnerapi.models import ApiAccess

    assert create(api, chef, club, allowed_networks=["203.0.113.7"]).status_code == 201
    with rls_bypass():
        access = ApiAccess.objects.get(organization=club)
    url = f"/api/orgs/{club.pk}/api-accesses/{access.pk}/"
    settings.MFA_STEP_UP = True
    # Umbenennen gibt nichts Neues nach außen
    assert api(chef).patch(url, {"name": "Anders"}, content_type=JSON).status_code == 200
    resp = api(chef).patch(url, {"allowed_networks": ["198.51.100.0/24"]}, content_type=JSON)
    assert resp.status_code == 403 and resp.json().get("step_up"), resp.content
    with rls_bypass():
        access.refresh_from_db()
    assert access.allowed_networks == ["203.0.113.7/32"]
