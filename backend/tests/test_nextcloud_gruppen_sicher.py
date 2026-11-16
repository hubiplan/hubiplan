"""Nextcloud-Gruppen: Zwei-Faktor-Regel und reservierte Namen (Gesamtaudit 15.11., AUTH-03/OIDC-1).

- Ohne zweiten Faktor ruhen nach der Frist alle Verwaltungsrechte; dann zählt auch die Rolle nicht
  mehr für die Nextcloud (vorher: Gruppe „Vorstand“ weiter nur mit Passwort).
- Frei benannte Untereinheiten und Rollen ergeben keine festen Gruppen („Vorstand“,
  „Mitglieder“, Kontogruppe) und nie die Administratorgruppe „admin“.
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from access.models import Role
from accounts.models import User
from core.tenancy import tenant_context
from organizations.models import Department
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user
from .test_nextcloud_anmeldung import (  # noqa: F401  (_key: autouse-Fixture)
    _key,
    code_of,
    make_client,
    redeem,
    start,
)
from .test_nextcloud_gruppen import groups_of

pytestmark = pytest.mark.django_db


def test_vorstand_ohne_2fa_nach_frist_nicht_in_vorstandsgruppe(api, orgs, board_a):
    org = orgs["a"]
    User.objects.filter(pk=board_a.pk).update(
        mfa_required_by=timezone.now() - datetime.timedelta(days=30)
    )
    board_a.refresh_from_db()
    client, secret = make_client(org, groups_board=True)
    erste = start(api(board_a), client)
    redirect = erste.json().get("redirect", "") if erste.status_code == 200 else ""
    if "code=" not in redirect:
        return  # Anmeldung abgelehnt: Rolle zählt ohne zweiten Faktor nicht
    from .test_nextcloud_anmeldung import verify_jwt

    resp = redeem(client, secret, code_of(erste))
    assert resp.status_code == 200, resp.content
    assert "Vorstand" not in verify_jwt(resp.json()["id_token"])["groups"]


def test_untereinheit_namens_vorstand_gibt_keine_vorstandsgruppe(api, orgs):
    org = orgs["a"]
    with tenant_context(org.pk):
        unit = Department.objects.create(organization=org, name="Vorstand", founding_year=1950)
        jugend = Department.objects.create(organization=org, name="Jugend", founding_year=1950)
    membership = make_member(org, "Erika", "Muster", departments=[unit, jugend])
    user = make_user("erika-oidc1@example.org")
    with tenant_context(org.pk):
        PortalAccess.objects.create(organization=org, membership=membership, user=user)
    client, secret = make_client(org, audience="members", groups_units=True, groups_board=True)
    groups = groups_of(api, client, secret, user)
    assert "Vorstand" not in groups
    assert "Jugend" in groups  # gewöhnliche Namen bleiben


def test_rolle_namens_admin_gibt_keine_admingruppe(api, orgs):
    user = make_user("helfer-oidc1@example.org")
    give_role(user, orgs["a"], [], name="admin")
    client, secret = make_client(orgs["a"], groups_roles=True)
    assert "admin" not in groups_of(api, client, secret, user)


def test_zuordnung_auf_admin_wird_nie_gesendet(api, orgs):
    user = make_user("kasse-oidc1@example.org")
    role = give_role(user, orgs["a"], [], name="Kassierer").role
    client, secret = make_client(orgs["a"], role_groups={str(role.pk): ["admin", "Kasse"]})
    groups = groups_of(api, client, secret, user)
    assert "admin" not in groups and "Kasse" in groups


def test_rolle_namens_mitglieder_gibt_keine_mitgliedergruppe(api, orgs):
    user = make_user("mitgl-oidc1@example.org")
    give_role(user, orgs["a"], [], name="Mitglieder")
    client, secret = make_client(orgs["a"], groups_roles=True)
    assert "Mitglieder" not in groups_of(api, client, secret, user)
    assert Role.objects.filter(name="Mitglieder").exists()
