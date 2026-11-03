"""Einladung zum Festlegen des Passworts erneut senden (erfundene Daten)."""

import datetime

import pytest

pytestmark = pytest.mark.django_db


def _eingeladen(orgs, email="neu@example.org", **kwargs):
    from .factories import give_role, make_user

    ziel = make_user(email)
    ziel.set_unusable_password()
    ziel.save(update_fields=["password"])
    return ziel, give_role(ziel, orgs["a"], name="Beisitz", **kwargs)


def _url(orgs, zuordnung):
    return f"/api/orgs/{orgs['a'].pk}/assignments/{zuordnung.pk}/resend-invitation/"


def test_liste_zeigt_offene_einladung(orgs, api, board_a):
    ziel, zuordnung = _eingeladen(orgs)
    resp = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/assignments/")
    assert resp.status_code == 200
    data = resp.json()
    rows = data["results"] if isinstance(data, dict) else data
    by_email = {r["user_email"]: r for r in rows}
    assert by_email["neu@example.org"]["awaiting_password"] is True
    assert by_email["vorstand-a@example.org"]["awaiting_password"] is False


def test_einladung_erneut_senden(orgs, api, board_a, mailoutbox):
    from audit.models import AuditEntry

    ziel, zuordnung = _eingeladen(orgs)
    resp = api(board_a).post(_url(orgs, zuordnung))
    assert resp.status_code == 200, resp.json()
    assert resp.json()["invited"] is True
    assert mailoutbox[-1].to == ["neu@example.org"]
    assert "Beisitz" in mailoutbox[-1].body
    assert "http" in mailoutbox[-1].body
    assert AuditEntry.objects.filter(organization=orgs["a"]).exists()


def test_neuer_link_funktioniert_nach_abgelaufener_frist(orgs, api, board_a, mailoutbox):
    """Alter Link (älter als die Einladungsfrist) ist ungültig, der neue gültig."""
    from allauth.account import app_settings as account_settings

    from accounts.tokens import INVITATION_DAYS

    ziel, zuordnung = _eingeladen(orgs)
    gen = account_settings.PASSWORD_RESET_TOKEN_GENERATOR()
    jetzt = datetime.datetime.now()
    alt = gen._make_token_with_timestamp(
        ziel, gen._num_seconds(jetzt - datetime.timedelta(days=INVITATION_DAYS + 1)), gen.secret
    )
    assert not gen.check_token(ziel, alt)
    assert api(board_a).post(_url(orgs, zuordnung)).status_code == 200
    assert gen.check_token(ziel, gen.make_token(ziel))


def test_nicht_bei_konto_mit_passwort(orgs, api, board_a, mailoutbox):
    from .factories import give_role, make_user

    ziel = make_user("hat-passwort@example.org")
    zuordnung = give_role(ziel, orgs["a"], name="Beisitz")
    resp = api(board_a).post(_url(orgs, zuordnung))
    assert resp.status_code == 400
    assert "Passwort vergessen" in resp.json()["detail"]
    assert not mailoutbox


def test_nicht_bei_beendeter_rolle(orgs, api, board_a, mailoutbox):
    gestern = datetime.date.today() - datetime.timedelta(days=1)
    ziel, zuordnung = _eingeladen(
        orgs, valid_from=gestern - datetime.timedelta(days=10), valid_until=gestern
    )
    resp = api(board_a).post(_url(orgs, zuordnung))
    assert resp.status_code == 400
    assert not mailoutbox


def test_nur_mit_rollenverwaltung(orgs, api, mailoutbox):
    from .factories import give_role, make_user

    leser = make_user("leser@example.org")
    give_role(leser, orgs["a"], permissions=["roles.view"], name="Leser")
    ziel, zuordnung = _eingeladen(orgs)
    resp = api(leser).post(_url(orgs, zuordnung))
    assert resp.status_code in (403, 404)
    assert not mailoutbox


def test_fremder_verein_darf_nicht(orgs, api, board_b, mailoutbox):
    ziel, zuordnung = _eingeladen(orgs)
    resp = api(board_b).post(_url(orgs, zuordnung))
    assert resp.status_code in (403, 404)
    assert not mailoutbox
