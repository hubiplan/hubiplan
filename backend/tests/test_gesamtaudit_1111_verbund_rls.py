# ruff: noqa: F811
"""Gesamtaudit 11.11., S-07: Verbundtabellen mit Daten von Partnerinstanzen sind per RLS an
die eigene Einheit der Kopplung gebunden, ihre Inhalte liegen verschlüsselt. Erfundene Daten."""

import pytest
from django.db import connection

from core.encfields import EncryptedJSONField
from core.tenancy import rls_bypass, unit_context
from peering.models import Coupling, Message, RemoteMember

from .factories import make_org
from .test_verbund_kopplung import VEREIN, _setup, api, couple, net, world  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

# Postausgang und Nachweise: Inhalt verschlüsselt und nach Zustellung gelöscht (0015)
OHNE_RLS = {"peering_message"}


def test_jede_tabelle_mit_kopplung_hat_rls():
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'coupling_id'
            WHERE c.relkind = 'r' AND NOT c.relrowsecurity
            """
        )
        missing = {row[0] for row in cur.fetchall()} - OHNE_RLS
    assert missing == set()


def test_gemeldete_mitglieder_nur_fuer_die_eigene_einheit(net, world):
    lower, _upper = couple(net, world)
    with net.on(VEREIN):
        stranger = make_org("Fremder Verein Muster")
        with rls_bypass():
            RemoteMember.objects.create(coupling=lower, uid="m999", data={"hinweis": "Probe"})
        # unit_context: streng im Bereich der Einheit, ohne geerbte Umgehung (wie ein Eingang)
        with unit_context(world["club"].pk):
            row = RemoteMember.objects.get(uid="m999")
            assert row.data == {"hinweis": "Probe"}
        with unit_context(stranger.pk):
            assert not RemoteMember.objects.filter(uid="m999").exists()
            # Schreiben für eine fremde Kopplung scheitert ebenfalls
            with pytest.raises(Exception), connection.cursor() as cur:  # noqa: B017
                cur.execute(
                    "INSERT INTO peering_remotemember (coupling_id, uid, status, data, updated_at)"
                    " VALUES (%s, 'm1000', 'active', '{}'::jsonb, now())",
                    [lower.pk],
                )


def test_inhalte_liegen_verschluesselt(net, world):
    lower, _upper = couple(net, world)
    with net.on(VEREIN), rls_bypass():
        RemoteMember.objects.create(coupling=lower, uid="m998", data={"nachname": "Muster"})
        with connection.cursor() as cur:
            cur.execute("SELECT data::text FROM peering_remotemember WHERE uid = 'm998'")
            raw = cur.fetchone()[0]
    assert "Muster" not in raw and EncryptedJSONField.KEY in raw
    for model, name in ((Message, "payload"), (RemoteMember, "data")):
        assert isinstance(model._meta.get_field(name), EncryptedJSONField)
    assert Coupling.objects.filter(pk=lower.pk).exists()
