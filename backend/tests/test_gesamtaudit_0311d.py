"""Gesamtaudit 03.11.2026: GA-F08 (Ausweise mit Leserecht) und GA-S09 (CAMT in UTF-16).

Erfundene Daten."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from cards.models import MemberCard
from core.tenancy import tenant_context
from finance import camt

from .factories import give_role, make_member, make_user
from .test_cards import JSON, _private, card_url, club, erika, zug  # noqa: F401

pytestmark = pytest.mark.django_db

# --- GA-F08: „Ausweise sehen“ genügt zum Lesen ---


@pytest.fixture
def leser(club):
    user = make_user("ausweisleser@example.org")
    give_role(user, club, permissions=["members.view", "cards.view"], name="Ausweise lesen")
    return user


def test_leser_sieht_vorhandenen_ausweis(club, erika, api, board_a, leser):
    resp = api(board_a).post(card_url(club, erika), {"action": "create"}, content_type=JSON)
    assert resp.status_code == 200
    c = api(leser)
    resp = c.get(card_url(club, erika))
    assert resp.status_code == 200, resp.json()
    assert resp.json()["state"] == "active"
    # Sperren und neu erzeugen bleibt dem Bearbeitungsrecht vorbehalten
    for action in ("revoke", "renew", "create"):
        resp = c.post(card_url(club, erika), {"action": action}, content_type=JSON)
        assert resp.status_code == 403


def test_leser_druckt_nur_vorhandene(club, erika, api, board_a, leser):
    api(board_a).post(card_url(club, erika), {"action": "create"}, content_type=JSON)
    make_member(club, "Otto", "Ohne")
    resp = api(leser).get(f"/api/orgs/{club.pk}/cards/pdf/")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    with tenant_context(club.pk):
        # Für Otto legt der Leser keinen Ausweis an
        assert list(MemberCard.objects.values_list("membership_id", flat=True)) == [erika.pk]


def test_leser_untereinheit(club, zug, erika, api, board_a):
    from members.models import DepartmentRoleHolder
    from organizations.models import DepartmentRole
    from portal.models import PortalAccess

    role = DepartmentRole.objects.create(
        organization=club,
        department=zug,
        name="Schriftwart",
        permissions=["members.view", "cards.view"],
    )
    m = make_member(club, "Karl", "Lese", "karl@example.org", departments=[zug])
    DepartmentRoleHolder.objects.create(
        organization=club, membership=m, role=role, valid_from="2020-01-01"
    )
    api(board_a).post(f"/api/orgs/{club.pk}/members/{m.pk}/access/")
    c = api(PortalAccess.objects.get(membership=m).user)
    url = f"/api/depts/{zug.pk}/members/{erika.pk}/card/"
    assert c.get(url).json() == {"state": "none"}
    assert c.post(url, {"action": "create"}, content_type=JSON).status_code == 403
    api(board_a).post(card_url(club, erika), {"action": "create"}, content_type=JSON)
    assert c.get(url).json()["state"] == "active"
    assert c.get(f"/api/depts/{zug.pk}/cards/pdf/").status_code == 200
    with tenant_context(club.pk):
        # Karl (ohne Ausweis) bekommt durch den Leser keinen
        assert list(MemberCard.objects.values_list("membership_id", flat=True)) == [erika.pk]


# --- GA-S09: DTD wird auch in UTF-16 erkannt ---


@pytest.mark.parametrize(
    ("codec", "declared"),
    [("utf-16", "UTF-16"), ("utf-16-le", "UTF-16"), ("utf-16-be", "UTF-16"), ("utf-8", "UTF-8")],
)
def test_dtd_in_jeder_kodierung_abgelehnt(codec, declared):
    text = (
        f'<?xml version="1.0" encoding="{declared}"?>'
        '<!DOCTYPE x [<!ENTITY a "b">]><Document>&a;</Document>'
    )
    with pytest.raises(camt.CamtError, match="DTD"):
        camt.parse(text.encode(codec))


def test_unlesbare_kodierung_ist_fehlermeldung():
    text = '<?xml version="1.0" encoding="UTF-16-LE"?><Document/>'
    with pytest.raises(camt.CamtError, match="kein gültiges XML"):
        camt.parse(text.encode("utf-16-le"))


def test_utf16_ohne_dtd_wird_gelesen():
    from .test_kontoauszug import camt_xml, entry

    data = camt_xml([entry("3.00")])
    text = data.decode("utf-8").replace('encoding="UTF-8"', 'encoding="UTF-16"')
    assert len(camt.parse(text.encode("utf-16"))) == 1
