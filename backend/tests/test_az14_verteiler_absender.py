"""Zeilenschutz für die Absender der Verteiler (Gesamtaudit 15.11., AZ-14; circulars 0017).

Die Zwischentabelle ``circulars_mailinglist_senders`` zeigt unter der Rolle der Anwendung nur
Zeilen, deren Verteiler zur aktiven Einheit gehört. Die Verwaltung im eigenen Verein und der
Mail-Eingang (Systemverarbeitung ohne Einheit, unter Umgehung) arbeiten weiter wie bisher.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest
from django.db import DatabaseError, connection, transaction

from circulars import inbound
from circulars.models import InboundMail, MailingList
from core.tenancy import reset_rls, rls_bypass, tenant_context

from .app_rolle import unter_app_rolle
from .factories import give_role, make_user
from .test_m12_events import JSON, cal, private_root, zug, zug2  # noqa: F401  (Fixtures)
from .test_mailverteiler import base, create_list, mail_bytes, members  # noqa: F401

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="Zeilenschutz gibt es nur unter PostgreSQL"
    ),
]

Senders = MailingList.senders.through
DOMAIN = "verein.example.org"


@pytest.fixture(autouse=True)
def verteiler_settings(settings, private_root):
    settings.INBOUND_DOMAINS = [DOMAIN]
    settings.INBOUND_SIMULATION = True
    settings.INBOUND_IMAP_HOST = ""
    settings.MAIL_RATE_PER_HOUR = 0
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"


@pytest.fixture
def lists(cal, board_a, board_b, members, api):
    """Je ein Verteiler in Verein A und B, jeweils mit einem zweiten Absender ausgewählt."""
    schrift_a = make_user("schrift-a@example.org")
    give_role(schrift_a, cal["a"])
    schrift_b = make_user("schrift-b@example.org")
    give_role(schrift_b, cal["b"])
    a = create_list(api(board_a), base(cal["a"]), local_part="alle-a")
    b = create_list(api(board_b), base(cal["b"]), local_part="alle-b")
    for board, org, data, user in (
        (board_a, cal["a"], a, schrift_a),
        (board_b, cal["b"], b, schrift_b),
    ):
        resp = api(board).patch(
            f"{base(org)}lists/{data['id']}/", {"senders": [user.pk]}, content_type=JSON
        )
        assert resp.status_code == 200, resp.json()
    return {"a": a, "b": b, "schrift_a": schrift_a, "schrift_b": schrift_b}


def _rows(list_id: int) -> set[int]:
    return set(Senders.objects.filter(mailinglist_id=list_id).values_list("user_id", flat=True))


class TestDatenbank:
    def test_nur_absender_der_eigenen_verteiler_sichtbar(self, cal, lists):
        with unter_app_rolle(), tenant_context(cal["a"].pk):
            # Absichtlich ohne Filter nach Verteiler
            assert set(Senders.objects.values_list("mailinglist_id", flat=True)) == {
                lists["a"]["id"]
            }
            assert _rows(lists["b"]["id"]) == set()
        with unter_app_rolle():
            reset_rls()
            assert not Senders.objects.exists()
            with rls_bypass():
                assert _rows(lists["b"]["id"]) == {lists["schrift_b"].pk}

    def test_fremde_absender_weder_anlegen_noch_aendern(self, cal, lists, board_a):
        with unter_app_rolle(), tenant_context(cal["a"].pk):
            with pytest.raises(DatabaseError), transaction.atomic():
                Senders.objects.create(mailinglist_id=lists["b"]["id"], user_id=board_a.pk)
            # Fremde Zeilen sind unsichtbar: Ändern und Löschen treffen nichts
            assert Senders.objects.filter(mailinglist_id=lists["b"]["id"]).delete()[0] == 0
            assert (
                Senders.objects.filter(mailinglist_id=lists["b"]["id"]).update(user_id=board_a.pk)
                == 0
            )
            # Eigene Zeile auf einen fremden Verteiler umhängen: verboten
            with pytest.raises(DatabaseError), transaction.atomic():
                Senders.objects.filter(mailinglist_id=lists["a"]["id"]).update(
                    mailinglist_id=lists["b"]["id"]
                )
        assert _rows(lists["b"]["id"]) == {lists["schrift_b"].pk}
        assert _rows(lists["a"]["id"]) == {lists["schrift_a"].pk}


class TestVerwaltung:
    def test_eigener_verein_verwaltet_absender(self, cal, lists, board_a, api):
        c = api(board_a)
        url = f"{base(cal['a'])}lists/{lists['a']['id']}/"
        assert c.get(url).json()["senders"] == [lists["schrift_a"].pk]
        resp = c.patch(url, {"senders": [board_a.pk, lists["schrift_a"].pk]}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["senders"] == sorted([board_a.pk, lists["schrift_a"].pk])
        listed = c.get(f"{base(cal['a'])}lists/").json()["items"]
        assert listed[0]["senders"] == sorted([board_a.pk, lists["schrift_a"].pk])
        resp = c.patch(url, {"senders": []}, content_type=JSON)
        assert resp.status_code == 200 and resp.json()["senders"] == []
        assert _rows(lists["a"]["id"]) == set()

    def test_fremder_verein_sieht_und_aendert_nichts(self, cal, lists, board_b, api):
        c = api(board_b)
        fremd = lists["a"]["id"]
        # Über den eigenen Verein: Verteiler von A gibt es dort nicht
        for url in (f"{base(cal['b'])}lists/{fremd}/", f"{base(cal['a'])}lists/{fremd}/"):
            assert c.get(url).status_code in (403, 404)
            resp = c.patch(url, {"senders": [board_b.pk]}, content_type=JSON)
            assert resp.status_code in (403, 404)
        assert lists["schrift_a"].pk not in {
            o["id"]
            for o in c.get(f"{base(cal['b'])}lists/{lists['b']['id']}/").json()["sender_options"]
        }
        assert _rows(fremd) == {lists["schrift_a"].pk}


class TestEingang:
    """Der Eingang läuft im Hintergrund ohne Einheit; die Absenderauswahl muss trotzdem
    greifen (nicht leer erscheinen und damit allen mit dem Recht offenstehen)."""

    def test_auswahl_greift_unter_rolle_der_anwendung(self, lists, board_a):
        with unter_app_rolle():
            reset_rls()
            entry = inbound.process_message(mail_bytes(board_a.email, to=f"alle-a@{DOMAIN}"))
            assert entry.status == InboundMail.Status.REJECTED
            entry = inbound.process_message(
                mail_bytes(lists["schrift_a"].email, to=f"alle-a@{DOMAIN}", subject="Erlaubt")
            )
            assert entry.status == InboundMail.Status.WAITING
            # Absender des anderen Vereins darf nicht an A schreiben
            entry = inbound.process_message(
                mail_bytes(lists["schrift_b"].email, to=f"alle-a@{DOMAIN}", subject="Fremd")
            )
            assert entry.status == InboundMail.Status.REJECTED

    def test_freigebende_unter_rolle_der_anwendung(self, lists):
        ml = MailingList.objects.get(pk=lists["a"]["id"])
        with unter_app_rolle():
            reset_rls()
            assert inbound.moderators(ml) == [lists["schrift_a"]]
            assert inbound.may_send(lists["schrift_a"], ml)
