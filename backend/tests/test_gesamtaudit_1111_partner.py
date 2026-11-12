"""Gesamtaudit 11.11.2026, Fachfrage 6: Kassenprüfer lesen Partner, nehmen aber keine Liste mit."""
# ruff: noqa: F811

import pytest

from .factories import give_role, make_user
from .test_geschaeftspartner import JSON, base, c, club, create  # noqa: F401

pytestmark = pytest.mark.django_db


def test_kasse_lesen_ohne_export_und_verteiler(api, club, c, base):
    partner = create(c, base, roles=["sponsor"])
    pruefer = make_user("pruefer@example.org")
    give_role(pruefer, club, ["finance.view"], name="Kassenprüfer")
    other = api(pruefer)
    assert other.get(f"{base}{partner['id']}/").status_code == 200
    assert other.get(base).status_code == 200
    for response in (
        other.get(f"{base}export/"),
        other.get(f"{base}mailing/?role=sponsor"),
        other.post(f"{base}mailing/", {"subject": "X", "text": "Y"}, content_type=JSON),
    ):
        assert response.status_code == 403, response.content
        assert "Geschäftspartner" in response.json()["detail"]


def test_recht_geschaeftspartner_darf_exportieren(api, club, base, c):
    create(c, base)
    user = make_user("fest@example.org")
    give_role(user, club, ["partners.view"], name="Festausschuss")
    response = api(user).get(f"{base}export/")
    assert response.status_code == 200
    assert response["Content-Disposition"].endswith('geschaeftspartner.xlsx"')
