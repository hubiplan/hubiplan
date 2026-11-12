# ruff: noqa: F811
"""Gesamtaudit 11.11., S-05: Falsche Typen von einer Partnerinstanz führen zu 400 statt zu
einer Ausnahme, Vorschläge sind je Partner begrenzt. Erfundene Daten, kein echter Partner."""

import uuid

import pytest

from core.tenancy import rls_bypass
from peering import register, services
from peering.models import Coupling
from portal.models import ChangeRequest

from .factories import make_member
from .test_verbund_kopplung import VEREIN, _setup, api, couple, net, world  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _lower(net, world):
    lower, _upper = couple(net, world)
    lower.refresh_from_db()
    assert lower.direction == Coupling.Direction.PARENT
    return lower


def _uid(world) -> str:
    return f"m{make_member(world['club'], 'Mira', 'Muster').pk}"


@pytest.mark.parametrize(
    "data",
    [
        {"uid": "m1", "data": ["last_name"]},
        {"uid": "m1", "data": "Muster"},
        {"uid": ["m1"], "data": {"last_name": "Neu"}},
        {"uid": "m1", "data": {"last_name": {"x": 1}}, "previous": [1, 2]},
        {"uid": "m1", "data": {"last_name": "Neu"}, "previous": "alt", "message": ["x"]},
    ],
)
def test_vorschlag_mit_falschen_typen_ohne_ausnahme(net, world, data):
    lower = _lower(net, world)
    with net.on(VEREIN), rls_bypass():
        data = {**data, "uid": _uid(world)} if data["uid"] == "m1" else data
        register.receive_suggestion(lower, data)
        for item in ChangeRequest.objects.all():
            assert isinstance(item.previous, dict) and isinstance(item.message, str)


def test_nummern_mit_falschem_typ_ohne_ausnahme(net, world):
    lower = _lower(net, world)
    with net.on(VEREIN), rls_bypass():
        for numbers in (["m1", 5], "m1", 7):
            register.receive_numbers(lower, {"numbers": numbers})


def test_vorschlaege_je_mitglied_begrenzt(net, world):
    lower = _lower(net, world)
    with net.on(VEREIN), rls_bypass():
        uid = _uid(world)
        made = sum(
            register.receive_suggestion(lower, {"uid": uid, "data": {"first_name": f"Mira{i}"}})
            for i in range(register.MAX_OPEN_PER_MEMBER + 2)
        )
        assert made == register.MAX_OPEN_PER_MEMBER
        assert ChangeRequest.objects.filter(status="pending").count() == made


def test_unerwartete_ausnahme_wird_zu_400(net, world, monkeypatch):
    lower = _lower(net, world)

    def broken(*args):
        raise AttributeError("'list' object has no attribute 'items'")

    monkeypatch.setattr(register, "receive_numbers", broken)
    with net.on(VEREIN), rls_bypass():
        lower.refresh_from_db()
        payload = {
            "kind": "register.numbers",
            "data": {"numbers": []},
            "msg_id": str(uuid.uuid4()),
            "seq": lower.in_seq + 1,
        }
        with pytest.raises(services.Refused) as caught:
            services._receive(lower, payload)
    assert caught.value.status == 400
