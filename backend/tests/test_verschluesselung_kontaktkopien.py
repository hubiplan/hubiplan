"""Kontaktkopien: Chiffrat, Schlüsselinhaber, Versand und bestehende Daten."""

import base64
import datetime
import io
import json
import struct

import pytest
from django.core.exceptions import FieldError
from django.core.management import call_command
from django.db import connection, transaction

from billing.models import Invoice
from circulars import services
from circulars.models import Circular, CircularRecipient
from core import crypto
from core.tenancy import rls_bypass

from .factories import make_member

pytestmark = pytest.mark.django_db

EMAIL = "erika.kopie@example.org"
ADDRESS = "Lindenweg 4\n12345 Musterstadt"
VALUES = {"Vorname": "Erika", "Nachname": "Muster", "Anrede": "Guten Tag Erika Muster"}


def raw(obj, column):
    table = connection.ops.quote_name(obj._meta.db_table)
    column = connection.ops.quote_name(column)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [obj.pk])  # noqa: S608
        return cursor.fetchone()[0]


@pytest.fixture
def copies(orgs):
    member = make_member(orgs["a"], "Erika", "Muster", email=EMAIL)
    with rls_bypass():
        invoice = Invoice.objects.create(
            organization=orgs["a"],
            membership=member,
            recipient_kind="member",
            recipient_name="Erika Muster",
            recipient_address=ADDRESS,
            recipient_email=EMAIL,
            date=datetime.date(2026, 11, 3),
            due_date=datetime.date(2026, 11, 17),
        )
        circular = Circular.objects.create(
            organization=orgs["federation"], subject="Einladung", body="Hallo {Vorname}"
        )
        # Der Absender hält den Versandstand, auch bei Empfängern aus anderen Vereinen.
        recipient = CircularRecipient.objects.create(
            circular=circular,
            club=orgs["a"],
            membership=member,
            first_name="Erika",
            last_name="Muster",
            email=EMAIL,
            address=ADDRESS,
            values=VALUES,
            channel="mail",
        )
    return invoice, recipient


@pytest.mark.parametrize(
    "index,email_field,address_field",
    [(0, "recipient_email", "recipient_address"), (1, "email", "address")],
)
def test_kopien_verschluesselt_und_mit_absenderschluessel(
    copies, index, email_field, address_field
):
    obj = copies[index]
    for field in (email_field, address_field):
        cipher = raw(obj, field)
        assert cipher.startswith("enc1:")
        key_id = struct.unpack(">Q", base64.b64decode(cipher[5:])[:8])[0]
        assert key_id == crypto.key_for_org(obj.organization_id)[0]
    with rls_bypass():
        obj.refresh_from_db()
    assert getattr(obj, email_field) == EMAIL
    assert getattr(obj, address_field) == ADDRESS
    if index == 1:
        stored = raw(obj, "values")
        stored = json.loads(stored) if isinstance(stored, str) else stored
        assert set(stored) == {"enc1"}
        assert stored["enc1"].startswith("enc1:")
        assert "Erika" not in json.dumps(stored)
        assert obj.values == VALUES


@pytest.mark.parametrize("index,email_field", [(0, "recipient_email"), (1, "email")])
def test_leeren_und_versandfilter_bleiben_moeglich(copies, index, email_field):
    obj = copies[index]
    with rls_bypass():
        qs = type(obj).objects.filter(pk=obj.pk)
        assert qs.exclude(**{email_field: ""}).exists()
        with pytest.raises(FieldError), transaction.atomic():
            qs.update(**{email_field: "andere@example.org"})
        qs.update(**{email_field: ""})
        assert qs.filter(**{email_field: ""}).exists()
        obj.refresh_from_db()
    assert getattr(obj, email_field) == ""
    assert raw(obj, email_field) == ""


def test_altbestand_probe_idempotenz_und_rueckweg(copies):
    invoice, recipient = copies
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE billing_invoice SET recipient_email = %s, recipient_address = %s WHERE id = %s",
            [EMAIL, ADDRESS, invoice.pk],
        )
        cursor.execute(
            'UPDATE circulars_circularrecipient SET email = %s, address = %s, "values" = %s::jsonb '
            "WHERE id = %s",
            [EMAIL, ADDRESS, json.dumps(VALUES), recipient.pk],
        )
    with rls_bypass():
        invoice.refresh_from_db()
        recipient.refresh_from_db()
    assert invoice.recipient_email == recipient.email == EMAIL
    assert invoice.recipient_address == recipient.address == ADDRESS
    assert recipient.values == VALUES
    out = io.StringIO()
    call_command("daten_verschluesseln", "--probe", stdout=out)
    assert "billing.Invoice: 1" in out.getvalue()
    assert "circulars.CircularRecipient: 1" in out.getvalue()
    assert raw(invoice, "recipient_email") == EMAIL
    call_command("daten_verschluesseln", stdout=io.StringIO())
    encrypted = raw(invoice, "recipient_email"), raw(recipient, "values")
    assert encrypted[0].startswith("enc1:")
    call_command("daten_verschluesseln", stdout=io.StringIO())
    assert (raw(invoice, "recipient_email"), raw(recipient, "values")) == encrypted
    out = io.StringIO()
    call_command("daten_verschluesseln", "--probe", stdout=out)
    assert "0 Datensätze" in out.getvalue()
    call_command("daten_verschluesseln", "--entschluesseln", stdout=io.StringIO())
    assert raw(invoice, "recipient_email") == raw(recipient, "email") == EMAIL
    assert raw(invoice, "recipient_address") == raw(recipient, "address") == ADDRESS
    stored = raw(recipient, "values")
    assert (json.loads(stored) if isinstance(stored, str) else stored) == VALUES


def test_sammelspeicherung_und_versand_entschluesseln_snapshot(orgs, monkeypatch):
    member = make_member(orgs["c"], "Erika", "Muster", email=EMAIL)
    with rls_bypass():
        circular = Circular.objects.create(
            organization=orgs["c"], subject="Einladung", body="Hallo {Vorname} {Nachname}"
        )
        counts = services.start_sending(circular, None)
        assert counts["mail"] == 1
        recipient = circular.recipients.get(membership=member)
        assert raw(recipient, "email").startswith("enc1:")
        stored = raw(recipient, "values")
        stored = json.loads(stored) if isinstance(stored, str) else stored
        assert set(stored) == {"enc1"}
        member.person.first_name = "Geändert"
        member.person.save(update_fields=["first_name"])
        sent = []
        monkeypatch.setattr(
            services.mail, "send", lambda *args, **kwargs: sent.append(args) or True
        )
        assert services.deliver(recipient, circular, [])
        assert sent[0][0] == EMAIL
        assert "Hallo Erika Muster" in sent[0][2]
        assert "Geändert" not in sent[0][2]


def test_brief_nutzt_entschluesselte_kopie(copies, monkeypatch):
    recipient = copies[1]
    with rls_bypass():
        circular = recipient.circular
        circular.status = "sent"
        circular.save(update_fields=["status"])
        recipient.channel = "letter"
        recipient.save(update_fields=["channel"])
        captured = []
        monkeypatch.setattr(
            services, "render_letters", lambda circular, rows: captured.extend(rows) or b"pdf"
        )
        assert services.letters_pdf(circular) == b"pdf"
    assert captured == [(ADDRESS, VALUES)]
