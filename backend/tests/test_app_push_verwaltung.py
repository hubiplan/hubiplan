"""Push für die Verwaltung: Hinweis an Konten mit Recht, wenn etwas unter „Zu erledigen“ wartet."""
# ruff: noqa: F811  (Fixtures aus anderen Testdateien als Parameter)

import json

import pytest
from django.core.cache import cache

from core.tenancy import tenant_context
from devices import admin_push
from devices.models import Device
from portal.models import ChangeRequest

from .factories import give_role, make_user
from .test_app_devices import APP, app, pair, pairing_code
from .test_app_push import (  # noqa: F401  (Fixtures)
    Receiver,
    allow_endpoint,
    push_outbox,
    register,
)
from .test_m12_events import (  # noqa: F401  (Fixtures)
    JSON,
    cal,
    member_with_access,
    org_base,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()


def with_app(user, api, endpoint):
    """Konto verbindet die App und meldet einen Push-Endpunkt."""
    token = pair(pairing_code(api(user))).json()["token"]
    receiver = Receiver()
    assert register(token, receiver, endpoint).status_code == 200
    return token, receiver


@pytest.fixture
def cashier(cal, api, allow_endpoint):
    """Kassierer ohne Mitgliedschaft in Verein a (Kasse eingeschaltet), App mit Push."""
    cal["a"].enabled_modules = [*cal["a"].enabled_modules, "finance"]
    cal["a"].save()
    user = make_user("kasse@example.org")
    give_role(user, cal["a"], name="Kasse")
    token, receiver = with_app(user, api, "https://push.example.org/up/kasse")
    return {"user": user, "token": token, "receiver": receiver}


def payloads(outbox, receiver):
    return [json.loads(receiver.decrypt(p["body"])) for p in outbox]


def test_hinweis_ohne_namen_und_betraege(cashier, cal, push_outbox):
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 1
    (data,) = payloads(push_outbox, cashier["receiver"])
    assert data == {
        "v": 1,
        "t": "admin",
        "unit": cal["a"].pk,
        "kind": "incoming_review",
        "title": "Neue Eingangsrechnung",
        "text": cal["a"].name,
    }


def test_mehrere_kurz_nacheinander_ein_hinweis(cashier, cal, push_outbox):
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 1
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 0
    assert len(push_outbox) == 1


def test_nur_mit_recht(cal, api, allow_endpoint, push_outbox):
    cal["a"].enabled_modules = [*cal["a"].enabled_modules, "finance"]
    cal["a"].save()
    user = make_user("termine@example.org")
    give_role(user, cal["a"], ["events.view", "events.edit"], name="Termine")
    with_app(user, api, "https://push.example.org/up/termine")
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 0
    assert push_outbox == []


def test_mitglied_ohne_rolle_bekommt_nichts(cashier, cal, api, push_outbox):
    _, member, _ = member_with_access(cal["a"], "Anna")
    with_app(member, api, "https://push.example.org/up/anna")
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 1
    assert [p["url"] for p in push_outbox] == ["https://push.example.org/up/kasse"]


def test_andere_einheit_bekommt_nichts(cashier, cal, push_outbox):
    cal["b"].enabled_modules = [*cal["b"].enabled_modules, "finance"]
    cal["b"].save()
    assert admin_push.notify(cal["b"].pk, "incoming_review") == 0
    assert push_outbox == []


def test_modul_aus_kein_hinweis(cashier, cal, push_outbox):
    cal["a"].enabled_modules = [m for m in cal["a"].enabled_modules if m != "finance"]
    cal["a"].save()
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 0


def test_wer_selbst_anlegt_bekommt_nichts(cashier, cal, push_outbox):
    assert admin_push.notify(cal["a"].pk, "incoming_review", cashier["user"].pk) == 0
    assert push_outbox == []


def test_schalter_je_geraet(cashier, cal, push_outbox):
    client = app(cashier["token"])
    assert client.get(f"{APP}me/").json()["device"]["admin_push"] is True
    resp = client.put(f"{APP}devices/current/push/admin/", {"enabled": False}, content_type=JSON)
    assert resp.status_code == 200 and resp.json()["admin_push"] is False
    assert Device.objects.get().admin_push is False
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 0
    assert push_outbox == []
    client.put(f"{APP}devices/current/push/admin/", {"enabled": True}, content_type=JSON)
    assert admin_push.notify(cal["a"].pk, "incoming_review") == 1


def test_neue_datenaenderung_meldet_sich(
    cashier, cal, monkeypatch, django_capture_on_commit_callbacks
):
    """Das Anlegen eines Eintrags stößt den Hinweis an (nach dem Speichern)."""
    m, _, _ = member_with_access(cal["a"], "Erika")
    calls = []
    monkeypatch.setattr(admin_push.notify, "delay", lambda *args: calls.append(args))
    with django_capture_on_commit_callbacks(execute=True), tenant_context(cal["a"].pk):
        ChangeRequest.objects.create(organization=cal["a"], membership=m, data={"city": "Neustadt"})
    assert calls == [(cal["a"].pk, "change_request", None)]


def test_funktion_gemeldet():
    from django.test import Client

    assert "app-push-verwaltung" in Client().get(f"{APP}instance/").json()["features"]
