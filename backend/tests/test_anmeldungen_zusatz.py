# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Zusatzleistungen, Zusatzfragen, Gesundheitsangaben und Erziehungsberechtigte
(konzepte/veranstaltungen-anmeldung-gebuehr.md, Stufe A5, F11, F13). Alle Daten erfunden."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from registrations.extras import purge_health_due
from registrations.models import Participant, Registration

from .test_anmeldungen import JSON, einrichten, fest, ok, soon  # noqa: F401
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

ADDONS = [
    {
        "name": "Busfahrt",
        "per": "person",
        "choices": [{"name": "Busfahrt", "amount": "12.00", "capacity": 1}],
    },
    {
        "name": "Menü",
        "kind": "meal",
        "per": "person",
        "required": True,
        "choices": [{"name": "Schnitzel", "amount": "0"}, {"name": "Lachs", "amount": "3.00"}],
    },
]
QUESTIONS = [
    {"text": "Tischwunsch", "kind": "text", "per": "registration"},
    {"text": "Allergien", "kind": "health"},
]


def _ids(offer):
    bus, menu = offer["addons"]
    return {
        "bus": (bus["id"], bus["choices"][0]["id"]),
        "schnitzel": (menu["id"], menu["choices"][0]["id"]),
        "lachs": (menu["id"], menu["choices"][1]["id"]),
        "table": offer["questions"][0]["id"],
        "health": offer["questions"][1]["id"],
        "adult": offer["prices"][0]["id"],
        "kids": offer["prices"][1]["id"],
    }


def _pick(*choices):
    return {str(a): ch for a, ch in choices}


def test_zusatzleistungen_fragen_und_gesundheit(c, fest, club):
    data = einrichten(c, fest, addons=ADDONS, questions=QUESTIONS)
    assert data["offer"]["health_allowed"] is True
    client, url = fest["portals"]["Anna"]
    offer = ok(client.get(f"{url}registration/"))["offer"]
    ids = _ids(offer)
    anna = {
        "membership_id": fest["anna"].pk,
        "price_id": ids["adult"],
        "addons": _pick(ids["bus"], ids["lachs"]),
        "health": "Nüsse",
    }
    kim = {"membership_id": fest["kind"].pk, "price_id": ids["kids"]}
    # Menü ist Pflicht
    resp = client.post(f"{url}registration/", {"persons": [anna, kim]}, content_type=JSON)
    assert resp.status_code == 400 and "Menü" in resp.content.decode()
    kim["addons"] = _pick(ids["schnitzel"])
    # Gesundheitsangabe nur mit Einwilligung
    body = {"persons": [anna, kim], "answers": {str(ids["table"]): "am Fenster"}}
    resp = client.post(f"{url}registration/", body, content_type=JSON)
    assert resp.status_code == 400 and "Allergien" in resp.content.decode()
    mine = ok(
        client.post(f"{url}registration/", {**body, "health_consent": True}, content_type=JSON)
    )["mine"][0]
    persons = {p["name"]: p for p in mine["participants"]}
    assert [b["name"] for b in persons["Anna Muster"]["bookings"]] == ["Busfahrt", "Menü: Lachs"]
    assert "health" not in persons["Anna Muster"]
    assert mine["answers"] == {str(ids["table"]): "am Fenster"}
    base_amount = sum(Decimal(p["amount"]) for p in mine["participants"])
    assert Decimal(mine["total"]) == base_amount + Decimal("15.00")
    assert Decimal(mine["invoice"]["total"]) == Decimal(mine["total"])
    # Verwaltung sieht die Gesundheitsangabe und die Zählung
    board = ok(c.get(fest["url"]))
    row = next(p for p in board["registrations"][0]["participants"] if p["name"] == "Anna Muster")
    assert row["health"] == "Nüsse"
    bus, menu = board["offer"]["addons"]
    assert bus["choices"][0]["taken"] == 1 and bus["choices"][0]["free"] == 0
    assert [ch["taken"] for ch in menu["choices"]] == [1, 1]
    # Bus ausgebucht
    client, url = fest["portals"]["Bernd"]
    bernd = {
        "membership_id": fest["bernd"].pk,
        "price_id": ids["adult"],
        "addons": _pick(ids["bus"], ids["schnitzel"]),
    }
    resp = client.post(f"{url}registration/", {"persons": [bernd]}, content_type=JSON)
    assert resp.status_code == 400 and "ausgebucht" in resp.content.decode()
    # Teilabmeldung: Rest-Rechnung behält die Zusatzleistungen der Bleibenden
    reg_id = board["registrations"][0]["id"]
    kim_id = persons["Kim Muster"]["id"]
    quote = ok(c.get(f"{fest['url']}{reg_id}/cancel/?participants={persons['Anna Muster']['id']}"))
    assert Decimal(quote["base"]) == Decimal(persons["Anna Muster"]["amount"]) + Decimal("15.00")
    ok(c.post(f"{fest['url']}{reg_id}/cancel/", {"participants": [kim_id]}, content_type=JSON))
    with tenant_context(club.pk):
        reg = Registration.objects.get(pk=reg_id)
        assert reg.total == Decimal(persons["Anna Muster"]["amount"]) + Decimal("15.00")
        assert reg.invoice.total == reg.total
    # Teilnehmerliste: Gesundheit nur auf Wunsch
    plain = c.get(f"{fest['url']}export/")
    assert plain.status_code == 200
    import io

    from openpyxl import load_workbook

    head = [x.value for x in load_workbook(io.BytesIO(plain.content)).active[1]]
    assert "Busfahrt" in head and "Tischwunsch" in head
    assert "Allergien und Unverträglichkeiten" not in head
    full = load_workbook(io.BytesIO(c.get(f"{fest['url']}export/?health=1").content)).active
    assert "Allergien und Unverträglichkeiten" in [x.value for x in full[1]]


def test_gesundheit_nur_mit_essen_und_loeschfrist(c, fest, club):
    resp = c.put(
        fest["url"],
        {
            "closes_at": soon(30),
            "prices": einrichten(c, fest)["offer"]["prices"],
            "questions": QUESTIONS,
        },
        content_type=JSON,
    )
    assert resp.status_code == 400 and "Essen" in resp.content.decode()
    data = einrichten(c, fest, catering=True, questions=QUESTIONS)
    offer = data["offer"]
    client, url = fest["portals"]["Anna"]
    health = offer["questions"][1]["id"]
    ok(
        client.post(
            f"{url}registration/",
            {
                "persons": [
                    {
                        "membership_id": fest["anna"].pk,
                        "price_id": offer["prices"][0]["id"],
                        "health": "Laktose",
                    }
                ],
                "health_consent": True,
            },
            content_type=JSON,
        )
    )
    with tenant_context(club.pk):
        assert Participant.objects.get().health == "Laktose"
        assert Registration.objects.get().health_consent_at is not None
    # Verpflegung wieder entfernt: Frage aus, Angaben gelöscht
    data = einrichten(c, fest, catering=False)
    assert not data["offer"]["health_allowed"]
    assert next(q for q in data["offer"]["questions"] if q["id"] == health)["is_active"] is False
    with tenant_context(club.pk):
        assert Participant.objects.get().health == ""
        p = Participant.objects.get()
        p.health = "Laktose"
        p.save(update_fields=["health"])
    # 14 Tage nach dem Ende gelöscht
    later = timezone.now() + datetime.timedelta(days=60)
    assert purge_health_due(later) == 1
    with tenant_context(club.pk):
        assert Participant.objects.get().health == ""


def test_minderjaehrige_mit_erziehungsberechtigten(c, fest, club):
    offer = einrichten(c, fest, minors=True)["offer"]
    assert offer["minors"] is True
    client, url = fest["portals"]["Anna"]
    kim = {"membership_id": fest["kind"].pk, "price_id": offer["prices"][1]["id"]}
    resp = client.post(f"{url}registration/", {"persons": [kim]}, content_type=JSON)
    assert resp.status_code == 400 and "unter 18" in resp.content.decode()
    kim["guardians"] = [{"name": "Anna Muster", "phone": "0123 456789"}]
    resp = client.post(f"{url}registration/", {"persons": [kim]}, content_type=JSON)
    assert resp.status_code == 400
    kim["guardians"][0]["email"] = "anna@example.org"
    mine = ok(client.post(f"{url}registration/", {"persons": [kim]}, content_type=JSON))["mine"]
    assert mine[0]["participants"][0]["guardians"][0]["phone"] == "0123 456789"
    # Gast ohne Geburtsdatum: im Mitgliederbereich Pflicht
    guest = {"name": "Gerd Gast", "price_id": offer["prices"][2]["id"]}
    resp = client.post(f"{url}registration/", {"persons": [guest]}, content_type=JSON)
    assert resp.status_code == 400 and "Geburtsdatum" in resp.content.decode()
