"""Geheime Abstimmung: Stimmzettel nicht über xmin oder Reihenfolge zuordenbar (GEH-1).

Gesamtaudit 15.11.: „Hat abgestimmt“ (mit Teilnahme) und Stimmzettel entstanden in derselben
Transaktion und trugen dieselbe Transaktionsnummer; mit Lesezugriff auf die Datenbank oder eine
Sicherung war die geheime Wahl nicht geheim. Jetzt mischt HUBIplan die Stimmzettel beim Schließen
der Abstimmung sofort und offene geheime Abstimmungen stündlich. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

from unittest import mock

import pytest
from django.db import connection, connections

from core.tenancy import rls_bypass
from meetings import live
from meetings.models import Ballot, Poll

from .test_versammlung_live import checkin, start_poll, vote, world  # noqa: F401
from .test_versammlungen import JSON, ok, setup  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ohne_broker(settings):
    # Mit echten Transaktionen laufen on_commit-Aufgaben; ohne Broker im Testaufbau gleich im
    # Prozess ausführen
    settings.CELERY_TASK_ALWAYS_EAGER = True


def _xmin_matches(poll_id: int) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM meetings_votecast c JOIN meetings_ballot b "
            "ON b.xmin = c.xmin AND b.poll_id = c.poll_id WHERE c.poll_id = %s",
            [poll_id],
        )
        return cursor.fetchone()[0]


def _secret_poll(w):
    code = ok(w["chef"].post(w["live"], {"open": True}, content_type=JSON))["code"]
    for who in ("Anna", "Bernd", "Carla"):
        ok(checkin(w, who, code=code))
    return start_poll(w, w["item"], question="Entlastung des Vorstands", secret=True)


def test_schliessen_mischt_sofort_und_zaehlung_bleibt(world):
    w = world
    poll = _secret_poll(w)
    ok(vote(w, "Anna", poll, ["Ja"]))
    ok(vote(w, "Bernd", poll, ["Nein"]))
    ok(vote(w, "Carla", poll, ["Ja"]))
    with rls_bypass():
        # Vorher: jede Stimme zuordenbar
        assert _xmin_matches(poll["id"]) == 3
    data = ok(w["chef"].post(f"{w['polls']}{poll['id']}/", {"action": "close"}, content_type=JSON))
    result = {r["label"]: r["votes"] for r in data["polls"][0]["result"]}
    assert result == {"Ja": 2, "Nein": 1, "Enthaltung": 0}
    with rls_bypass():
        assert _xmin_matches(poll["id"]) == 0
        assert Ballot.objects.filter(poll_id=poll["id"]).count() == 3


def test_stundenlauf_mischt_offene_und_wartet_bei_sperre(world):
    w = world
    poll = _secret_poll(w)
    ok(vote(w, "Anna", poll, ["Ja"]))
    ok(vote(w, "Bernd", poll, ["Nein"]))
    other = connections.create_connection("default")
    try:
        other.set_autocommit(False)
        with other.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
            cursor.execute(
                "SELECT id FROM meetings_meeting WHERE id = %s FOR UPDATE", [w["meeting"]["id"]]
            )
        # Jemand stimmt gerade ab: nächster Lauf
        assert live.mix_open_polls() == 0
        with rls_bypass():
            assert _xmin_matches(poll["id"]) == 2
    finally:
        other.rollback()
        other.close()
    assert live.mix_open_polls() == 1
    with rls_bypass():
        assert _xmin_matches(poll["id"]) == 0
        before = live.tally(Poll.objects.get(pk=poll["id"]))
    assert {r["label"]: r["votes"] for r in before}["Ja"] == 1


def test_stimme_zwischen_lesen_und_loeschen_bleibt(world):
    w = world
    poll = _secret_poll(w)
    ok(vote(w, "Anna", poll, ["Ja"]))
    with rls_bypass():
        obj = Poll.objects.get(pk=poll["id"])
        first = Ballot.objects.get(poll=obj)
        real_shuffle = live.secrets.SystemRandom.shuffle

        def shuffle_and_vote(self, rows):
            real_shuffle(self, rows)
            Ballot.objects.create(
                organization_id=first.organization_id,
                meeting_id=first.meeting_id,
                poll=obj,
                option_id=first.option_id,
            )

        with mock.patch.object(live.secrets.SystemRandom, "shuffle", shuffle_and_vote):
            assert live.mix_ballots(obj) == 1
        assert Ballot.objects.filter(poll=obj).count() == 2


def test_offene_abstimmung_bleibt_unberuehrt(world):
    w = world
    code = ok(w["chef"].post(w["live"], {"open": True}, content_type=JSON))["code"]
    ok(checkin(w, "Anna", code=code))
    poll = start_poll(w, w["item"], question="Satzungsänderung", secret=False)
    ok(vote(w, "Anna", poll, ["Ja"]))
    with rls_bypass():
        ids = set(Ballot.objects.filter(poll_id=poll["id"]).values_list("pk", flat=True))
    assert live.mix_open_polls() == 0
    with rls_bypass():
        assert set(Ballot.objects.filter(poll_id=poll["id"]).values_list("pk", flat=True)) == ids
        assert Ballot.objects.filter(poll_id=poll["id"], attendance__isnull=False).exists()
