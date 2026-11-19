# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Namensschilder und Aufkleber mit wählbaren Angaben, Material ausgeben und zurücknehmen,
auch über Scan-Links (Anmeldung A6). Alle Daten erfunden."""

import pytest
from django.test import Client

from core.tenancy import tenant_context
from registrations import tickets
from registrations.models import Participant

from .test_anmeldungen import JSON, einrichten, fest, ok, soon  # noqa: F401
from .test_anmeldungen_scanlinks import FREE, _anmelden, _token
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

QUESTIONS = [{"text": "Firma", "kind": "text", "per": "person"}]


def test_aufkleber_mit_gewaehlten_angaben(c, fest, club):
    einrichten(c, fest, prices=FREE, questions=QUESTIONS)
    _anmelden(fest, "Anna", meal=False)
    data = ok(c.get(f"{fest['url']}materials/"))
    labels = data["labels"]
    assert labels["formats"] == ["badge", "label24", "label8"]
    q = labels["questions"][0]["id"]
    for fmt in ("badge", "label24", "label8"):
        resp = c.get(
            f"{fest['url']}badges/?format={fmt}&fields=name,club,event,price,number,qr,q{q}"
        )
        assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    # Unbekanntes wird ignoriert, Vorgabe bleibt
    resp = c.get(f"{fest['url']}badges/?format=quatsch&fields=passwort")
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")


def test_material_ausgeben_zuruecknehmen_und_scannen(c, fest, club):
    einrichten(c, fest, prices=FREE)
    _anmelden(fest, "Anna", meal=False)
    url = f"{fest['url']}materials/"
    tag = ok(c.post(url, {"name": "Namensschild"}, content_type=JSON))
    radio = ok(c.post(url, {"name": "Funkgerät", "returnable": True}, content_type=JSON))
    with tenant_context(club.pk):
        anna = Participant.objects.get(membership=fest["anna"])
        code = tickets.code(anna)
    # In der Verwaltung abhaken
    board = ok(
        c.post(
            f"{url}handout/",
            {"participant": anna.pk, "material": tag["id"], "action": "out"},
            content_type=JSON,
        )
    )
    row = board["rows"][0]
    assert row["items"][str(tag["id"])]["handed_out_at"]
    assert row["items"][str(radio["id"])] is None
    # Rückgabe nur bei Material mit Rückgabe
    resp = c.post(
        f"{url}handout/",
        {"participant": anna.pk, "material": tag["id"], "action": "return"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Über Scan-Links: Ausgabe und Rückgabe des Funkgeräts
    links = f"{fest['url']}scan-links/"
    assert [m["name"] for m in ok(c.get(links))["materials"]] == ["Namensschild", "Funkgerät"]
    out = ok(c.post(links, {"label": "Ausgabe", "material": radio["id"]}, content_type=JSON))
    back = ok(
        c.post(
            links,
            {"label": "Rückgabe", "material": radio["id"], "material_return": True},
            content_type=JSON,
        )
    )
    assert out["kind"] == "material_out" and back["kind"] == "material_return"
    staff = Client()
    back_api = f"/api/public/scan/{_token(back['url'])}/"
    out_api = f"/api/public/scan/{_token(out['url'])}/"
    early = ok(staff.post(back_api, {"code": code}, content_type=JSON))
    assert early["result"] == "not_out"
    got = ok(staff.post(out_api, {"code": code}, content_type=JSON))
    assert got["result"] == "ok"
    items = {m["name"]: m for m in got["card"]["materials"]}
    assert items["Funkgerät"]["handed_out_at"] and items["Namensschild"]["handed_out_at"]
    assert ok(staff.post(out_api, {"code": code}, content_type=JSON))["result"] == "already"
    ret = ok(staff.post(back_api, {"code": code}, content_type=JSON))
    assert ret["result"] == "ok"
    assert ok(staff.post(back_api, {"code": code}, content_type=JSON))["result"] == "already"
    board = ok(c.get(url))
    item = board["rows"][0]["items"][str(radio["id"])]
    assert item["returned_at"] and item["via"] == "Ausgabe"
    assert board["counts"][str(radio["id"])] == {"out": 1, "returned": 1}
    # Material mit Ausgaben löschen: nur ausblenden, Scan-Links gesperrt
    assert c.delete(f"{url}{radio['id']}/").status_code == 204
    assert [m["name"] for m in ok(c.get(url))["materials"]] == ["Namensschild"]
    assert staff.get(out_api).status_code == 404
