"""Nextcloud-Anmeldung: Gruppen für Rollen („1. Kassierer“ und „2. Kassierer“ → „Kassierer“)."""

from __future__ import annotations

import datetime

from access.models import Role, RoleAssignment
from core.tenancy import tenant_context
from oidc.models import clean_groups
from organizations.models import Department, DepartmentRole
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user
from .test_nextcloud_anmeldung import (  # noqa: F401
    CLOUD,
    JSON,
    _key,
    code_of,
    make_client,
    redeem,
    start,
    verify_jwt,
)


def groups_of(api, client, secret, user) -> list[str]:
    token = redeem(client, secret, code_of(start(api(user), client))).json()["id_token"]
    return verify_jwt(token)["groups"]


def holder(org, name: str, email: str):
    user = make_user(email)
    return user, give_role(user, org, [], name=name).role


def test_gruppen_bereinigen():
    assert clean_groups(" Kassierer ,  Kasse, ,Kassierer") == ["Kassierer", "Kasse"]
    assert clean_groups(["A", " A ", "B  C"]) == ["A", "B C"]
    assert clean_groups(None) == []


def test_zwei_rollen_eine_gruppe(api, orgs):
    erster, k1 = holder(orgs["a"], "1. Kassierer", "k1@example.org")
    zweiter, k2 = holder(orgs["a"], "2. Kassierer", "k2@example.org")
    vorsitz, v1 = holder(orgs["a"], "1. Vorsitzender", "v1@example.org")
    mapping = {
        str(k1.pk): ["Kassierer"],
        str(k2.pk): ["Kassierer"],
        str(v1.pk): ["Kassierer", "Schriftführer"],
    }
    client, secret = make_client(orgs["a"], role_groups=mapping)
    assert groups_of(api, client, secret, erster) == ["Vorstand", "Kassierer"]
    assert groups_of(api, client, secret, zweiter) == ["Vorstand", "Kassierer"]
    assert groups_of(api, client, secret, vorsitz) == ["Vorstand", "Kassierer", "Schriftführer"]


def test_umbenennen_aendert_nichts(api, orgs):
    user, role = holder(orgs["a"], "1. Kassierer", "k1@example.org")
    client, secret = make_client(orgs["a"], role_groups={str(role.pk): ["Kassierer"]})
    with tenant_context(orgs["a"].pk):
        Role.objects.filter(pk=role.pk).update(name="Erster Kassierer")
    assert groups_of(api, client, secret, user) == ["Vorstand", "Kassierer"]


def test_gilt_auch_ohne_gruppen_je_rolle(api, orgs):
    # Nur die zugeordneten Gruppen, nicht die übrigen Rollennamen
    user, role = holder(orgs["a"], "1. Kassierer", "k1@example.org")
    give_role(user, orgs["a"], [], name="Adjutant")
    client, secret = make_client(
        orgs["a"], groups_roles=False, role_groups={str(role.pk): ["Kassierer"]}
    )
    assert groups_of(api, client, secret, user) == ["Vorstand", "Kassierer"]


def test_ohne_eintrag_wie_bisher(api, orgs):
    user, _ = holder(orgs["a"], "Major", "major@example.org")
    client, secret = make_client(orgs["a"], role_groups={})
    assert groups_of(api, client, secret, user) == ["Vorstand", "Major"]


def test_amt_in_untereinheit(api, orgs):
    with tenant_context(orgs["a"].pk):
        zug = Department.objects.create(organization=orgs["a"], name="Jäger", founding_year=1950)
        role = DepartmentRole.objects.create(department=zug, name="Zugführer")
    membership = make_member(orgs["a"], "Erika", "Muster", departments=[zug])
    user = make_user("erika@example.org")
    with tenant_context(orgs["a"].pk):
        PortalAccess.objects.create(organization=orgs["a"], membership=membership, user=user)
        RoleAssignment.all_objects.create(
            organization=orgs["a"],
            role=role,
            membership=membership,
            valid_from=datetime.date(2020, 1, 1),
        )
    client, secret = make_client(
        orgs["a"], groups_units=False, role_groups={str(role.pk): ["Zugführer"]}
    )
    assert groups_of(api, client, secret, user) == ["Zugführer", "Mitglieder"]


def test_einstellen_und_pruefen(api, orgs, board_a):
    _, k1 = holder(orgs["a"], "1. Kassierer", "k1@example.org")
    _, fremd = holder(orgs["b"], "Nur in B", "b@example.org")
    c = api(board_a)
    base = f"/api/orgs/{orgs['a'].pk}/nextcloud/"
    created = c.post(base, {"base_url": CLOUD}, JSON).json()
    assert created["role_groups"] == {}
    choices = {r["id"]: r for r in created["role_choices"]}
    assert choices[k1.pk]["name"] == "1. Kassierer" and fremd.pk not in choices
    url = f"{base}{created['id']}/"
    value = {str(k1.pk): " Kassierer,  Kasse ", str(fremd.pk): ["X"], "999999": ["Y"]}
    resp = c.patch(url, {"role_groups": value}, JSON)
    assert resp.status_code == 200, resp.content
    # Fremde und unbekannte Rollen fallen weg
    assert resp.json()["role_groups"] == {str(k1.pk): ["Kassierer", "Kasse"]}
    # Leer heißt: wie bisher
    resp = c.patch(url, {"role_groups": {str(k1.pk): ""}}, JSON)
    assert resp.json()["role_groups"] == {}
    for bad in ({str(k1.pk): ["x" * 65]}, ["Kassierer"], {str(k1.pk): 5}):
        assert c.patch(url, {"role_groups": bad}, JSON).status_code == 400, bad
