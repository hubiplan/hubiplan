# ruff: noqa: F811
"""Small synthetic quotas; never fill storage or contact a real peer."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from django.core.files.base import ContentFile
from django.db import close_old_connections, connection, transaction

from core.tenancy import rls_bypass
from peering import quotas, services
from peering.models import Coupling, Message, RemoteInvoice

from .factories import make_org
from .test_verbund_kopplung import VERBAND, _setup, api, couple, net, world  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    "state,kind",
    [
        (Coupling.State.PAUSED, "coupling.config"),
        (Coupling.State.PAUSED, "unit.moved"),
        (Coupling.State.MOVING, "unit.moved"),
    ],
)
def test_locked_receiver_preserves_control_message_exceptions(state, kind):
    original = SimpleNamespace(peer_id=1)
    current = SimpleNamespace(peer_id=1, state=state)
    services._check_receiver(original, current, kind)


@pytest.mark.parametrize("state", [Coupling.State.PAUSED, Coupling.State.MOVING])
@pytest.mark.parametrize("kind", ["register.numbers", "register.suggest"])
def test_locked_receiver_rechecks_state_after_loading_active_object(
    net, world, monkeypatch, state, kind
):
    from peering import register

    lower, upper = couple(net, world)
    applied = []
    monkeypatch.setattr(register, "receive_numbers", lambda *args: applied.append("numbers"))
    monkeypatch.setattr(register, "receive_suggestion", lambda *args: applied.append("suggest"))
    with net.on(VERBAND), rls_bypass():
        loaded = Coupling.objects.get(pk=upper.pk)
        assert loaded.state == Coupling.State.ACTIVE
        before = loaded.received_bytes
        # The initial object remains ACTIVE, just as while waiting for the lock.
        Coupling.objects.filter(pk=loaded.pk).update(state=state)
        payload = {"kind": kind, "data": {}, "msg_id": str(uuid.uuid4()), "seq": loaded.in_seq + 1}
        with pytest.raises(services.Refused) as caught:
            services._receive(loaded, payload)
        assert caught.value.status == 423
        loaded.refresh_from_db()
        assert loaded.received_bytes == before
        assert not Message.objects.filter(msg_id=payload["msg_id"]).exists()
    assert applied == []


def test_reservation_rolls_back_and_replay_does_not_charge(net, world):
    lower, upper = couple(net, world)
    with net.on(VERBAND), rls_bypass():
        upper.refresh_from_db()
        before = upper.received_bytes
        with pytest.raises(RuntimeError), transaction.atomic():
            locked = Coupling.objects.select_for_update().get(pk=upper.pk)
            quotas.reserve(locked, {"synthetic": "test"})
            raise RuntimeError("synthetic rollback")
        upper.refresh_from_db()
        assert upper.received_bytes == before
        payload = {
            "kind": "coupling.config",
            "seq": upper.in_seq + 1,
            "msg_id": str(uuid.uuid4()),
            "data": {"packets": {}},
        }
        services._receive(upper, payload)
        upper.refresh_from_db()
        after = upper.received_bytes
        assert after > before
        assert services._receive(upper, payload)["duplicate"]
        upper.refresh_from_db()
        assert upper.received_bytes == after


def test_existing_messages_are_included_in_initialization(net, world):
    lower, upper = couple(net, world)
    with rls_bypass(), transaction.atomic():
        upper = Coupling.objects.select_for_update().get(pk=upper.pk)
        invoice = RemoteInvoice.objects.create(coupling=upper, uid="synthetic-retained-invoice")
        payload = b"%PDF-synthetic" + b"x" * (512 * 1024)
        invoice.file.save("retained.pdf", ContentFile(payload), save=True)
        upper.usage_initialized = False
        upper.received_bytes = 0
        upper.received_count = 0
        upper.save(update_fields=["usage_initialized", "received_bytes", "received_count"])
        count = Message.objects.filter(coupling=upper, direction=Message.Direction.IN).count()
        quotas.reserve(upper, {})
        assert upper.received_count == count + 1
        assert upper.received_bytes >= (count + 1) * 65536
        assert upper.received_bytes > len(payload)
        assert invoice.file.storage.exists(invoice.file.name)


def test_legacy_initialization_of_other_couplings_is_persisted_once(net, world, monkeypatch):
    lower, upper = couple(net, world)
    seen = []
    original = quotas._legacy

    def legacy(current):
        seen.append(current.pk)
        return original(current)

    monkeypatch.setattr(quotas, "_legacy", legacy)
    with rls_bypass():
        Coupling.objects.filter(pk=lower.pk).update(usage_initialized=False)
        for _ in range(2):
            with transaction.atomic():
                quotas.lock_reception()
                current = Coupling.objects.select_for_update().get(pk=upper.pk)
                quotas.reserve(current, {})
        lower.refresh_from_db()
        assert lower.usage_initialized
    assert seen.count(lower.pk) == 1


def test_budget_columns_have_persistent_defaults_for_old_writers():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, column_default FROM information_schema.columns "
            "WHERE table_name = 'peering_coupling' AND column_name IN "
            "('received_bytes', 'received_count', 'usage_initialized')"
        )
        defaults = dict(cursor.fetchall())
    assert len(defaults) == 3
    assert all(value is not None for value in defaults.values())


def test_concurrent_couplings_cannot_overrun_unit_budget(net, world, settings):
    lower, upper = couple(net, world)
    with rls_bypass():
        remote = make_org("Zweiter synthetischer Partner")
        second = Coupling.objects.create(
            local_unit=upper.local_unit,
            remote_unit=remote,
            peer=upper.peer,
            remote_uuid=uuid.uuid4(),
            direction=upper.direction,
            state=upper.state,
        )
        used = sum(
            c.received_count if c.usage_initialized else quotas._legacy(c)[1]
            for c in Coupling.objects.filter(local_unit=upper.local_unit)
        )
    settings.PEERING_RECEPTION_UNIT_MESSAGES = used + 1
    barrier = Barrier(2)

    def attempt(pk):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            with rls_bypass(), transaction.atomic():
                quotas.lock_reception()
                current = Coupling.objects.select_for_update().get(pk=pk)
                quotas.reserve(current, {"synthetic": pk})
            return True
        except services.Refused as exc:
            assert exc.status == 507
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [upper.pk, second.pk]))
    assert sorted(results) == [False, True]


def test_partner_budget_spans_different_local_recipients(net, world, settings):
    lower, upper = couple(net, world)
    with rls_bypass(), transaction.atomic():
        other_local = make_org("Anderer lokaler Empfänger")
        remote = make_org("Anderer Partnerplatzhalter")
        second = Coupling.objects.create(
            local_unit=other_local,
            remote_unit=remote,
            peer=upper.peer,
            remote_uuid=uuid.uuid4(),
            direction=upper.direction,
            state=upper.state,
        )
        total = sum(
            c.received_count if c.usage_initialized else quotas._legacy(c)[1]
            for c in Coupling.objects.filter(peer=upper.peer)
        )
        settings.PEERING_RECEPTION_PEER_MESSAGES = max(1, total)
        with pytest.raises(services.Refused) as caught:
            quotas.reserve(second, {})
        assert caught.value.status == 507


def test_move_replays_are_budgeted_once_and_do_not_repeat_side_effects(net, world, monkeypatch):
    from peering import moving

    lower, upper = couple(net, world)
    verified = []
    applied = []
    data = {
        "base_url": "https://synthetic-new.example",
        "instance_id": str(uuid.uuid4()),
        "public_key": "synthetic-public",
        "enc_public_key": "synthetic-enc",
    }

    def verify(value):
        verified.append(value)
        return value

    def apply(current, value, *, verified_info):
        applied.append(value)
        current.options = {**current.options, "move": dict(value)}
        current.state = Coupling.State.MOVING
        current.save(update_fields=["options", "state"])

    monkeypatch.setattr(moving, "verify_moved", verify)
    monkeypatch.setattr(moving, "receive_moved", apply)
    with net.on(VERBAND), rls_bypass():
        upper.refresh_from_db()
        payload = {
            "kind": "unit.moved",
            "data": data,
            "msg_id": str(uuid.uuid4()),
            "seq": upper.in_seq + 1,
        }
        services._receive(upper, payload)
        upper.refresh_from_db()
        charged = upper.received_bytes
        assert services._receive(upper, payload)["duplicate"]
        assert services._receive(upper, {**payload, "msg_id": str(uuid.uuid4())})["stale"]
        upper.refresh_from_db()
        assert upper.received_bytes == charged
        services._receive(
            upper, {**payload, "seq": payload["seq"] + 1, "msg_id": str(uuid.uuid4())}
        )
        upper.refresh_from_db()
        assert upper.received_bytes > charged
    assert verified == [data]
    assert applied == [data]
