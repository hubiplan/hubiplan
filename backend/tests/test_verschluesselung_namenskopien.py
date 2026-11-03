"""Namenskopien: Umfang, Schlüssel, historische Werte und gezielter Rückweg."""

import ast
import base64
import datetime
import inspect
import io
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor

from billing.models import Invoice
from circulars.models import Circular, CircularRecipient
from competitions.models import CertificateTemplate, Competition, Starter
from core import crypto
from core.encfields import EncryptedJSONField, update_encrypted
from core.management.commands.daten_verschluesseln import encrypted_fields
from core.namecopies import FIELDS
from core.tenancy import rls_bypass
from members.personsearch import name_ids, ordered

from .factories import make_member

DAY = datetime.date(2026, 11, 3)
SNAPSHOT = [{"name": "Erika Muster", "function": "Vorstand"}]


def raw(obj, field):
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {quote(field)} FROM {quote(obj._meta.db_table)} WHERE id = %s",  # noqa: S608
            [obj.pk],
        )
        return cursor.fetchone()[0]


def run(*args):
    out = io.StringIO()
    call_command("namenskopien_verschluesseln", *args, stdout=out)
    return out.getvalue()


def records(orgs):
    m = make_member(orgs["a"], "Erika", "Muster")
    invoice = Invoice.objects.create(
        organization=orgs["a"],
        membership=m,
        recipient_kind="member",
        recipient_name="Erika Muster",
        recipient_email="erika@example.org",
        date=DAY,
        due_date=DAY,
    )
    circular = Circular.objects.create(
        organization=orgs["federation"], subject="Einladung", body="Hallo"
    )
    recipient = CircularRecipient.objects.create(
        organization=orgs["federation"],
        circular=circular,
        club=orgs["a"],
        membership=m,
        first_name="Erika",
        last_name="Muster",
        channel="letter",
        values={"Name": "Erika Muster"},
    )
    comp = Competition.objects.create(organization=orgs["a"], title="Testwettbewerb", date=DAY)
    starter = Starter.objects.create(organization=orgs["a"], competition=comp, name="Erika Muster")
    template = CertificateTemplate.objects.create(
        organization=orgs["a"], name="Urkunde", signers=SNAPSHOT
    )
    return m, invoice, recipient, starter, template


def target_backend(tmp_path):
    target = tmp_path / "backend"
    target.mkdir()
    for model, _ in encrypted_fields():
        source = Path(inspect.getfile(model))
        dest = target / source.relative_to(settings.BASE_DIR)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tree = ast.parse(source.read_text())
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            fields = FIELDS.get(f"{model._meta.app_label}.{cls.name}", ())
            for node in cls.body:
                if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                    continue
                if not any(
                    isinstance(name, ast.Name) and name.id in fields for name in node.targets
                ):
                    continue
                kind = (
                    "JSONField"
                    if ast.unparse(node.value.func) == "EncryptedJSONField"
                    else "CharField"
                )
                node.value.func = ast.Attribute(
                    value=ast.Name(id="models", ctx=ast.Load()), attr=kind, ctx=ast.Load()
                )
                node.value.keywords = [k for k in node.value.keywords if k.arg != "strict"]
        dest.write_text(ast.unparse(tree))
    return target


@pytest.mark.django_db
@pytest.mark.parametrize(
    "label,field_name", [(label, name) for label, fields in FIELDS.items() for name in fields]
)
def test_inventar_hat_textspalten_und_getrennte_schluessel(orgs, label, field_name):
    model = apps.get_model(label)
    field = model._meta.get_field(field_name)
    value = SNAPSHOT if isinstance(field, EncryptedJSONField) else "Erika Muster"
    with rls_bypass():
        obj = model(organization=orgs["a"])
        cipher = field.stored_value(obj, value)
        text = cipher["enc1"] if isinstance(field, EncryptedJSONField) else cipher
        assert text.startswith("enc1:") and "Erika" not in text
        assert (
            int.from_bytes(base64.b64decode(text[5:])[:8], "big")
            == crypto.key_for_org(orgs["a"].pk)[0]
        )
        other = field.stored_value(model(organization=orgs["b"]), value)
        assert cipher != other
        encoded = json.dumps(cipher) if isinstance(field, EncryptedJSONField) else cipher
        assert field.from_db_value(encoded, None, connection) == value
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                [model._meta.db_table, field.column],
            )
            assert cursor.fetchone()[0] == (
                "jsonb" if isinstance(field, EncryptedJSONField) else "text"
            )


@pytest.mark.django_db
def test_versandstand_bleibt_erhalten_und_gehoert_dem_absender(orgs):
    with rls_bypass():
        member, invoice, recipient, starter, template = records(orgs)
        before = [
            raw(obj, field)
            for obj, field in (
                (invoice, "recipient_name"),
                (recipient, "first_name"),
                (starter, "name"),
            )
        ]
        assert raw(recipient, "first_name").startswith("enc1:")
        assert (
            int.from_bytes(base64.b64decode(raw(recipient, "first_name")[5:])[:8], "big")
            == crypto.key_for_org(orgs["federation"].pk)[0]
        )
        member.person.first_name = "Else"
        member.person.save(update_fields=["first_name"])
        invoice.refresh_from_db()
        recipient.refresh_from_db()
        assert invoice.recipient_name == "Erika Muster" and recipient.first_name == "Erika"
        assert [
            raw(obj, field)
            for obj, field in (
                (invoice, "recipient_name"),
                (recipient, "first_name"),
                (starter, "name"),
            )
        ] == before
        template.refresh_from_db()
        assert template.signers == SNAPSHOT
        run("--pruefen")


@pytest.mark.django_db
def test_bestand_und_rueckweg_lassen_personennamen_verschluesselt(orgs, tmp_path):
    with rls_bypass():
        member, invoice, _, _, template = records(orgs)
        person_cipher = raw(member.person, "last_name")
        email_cipher = raw(invoice, "recipient_email")
        stamp = invoice.updated_at
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE billing_invoice SET recipient_name = 'Erika Muster' WHERE id = %s",
                [invoice.pk],
            )
        with pytest.raises(CommandError):
            run("--pruefen")
        run()
        run("--pruefen")
        saved = raw(invoice, "recipient_name")
        run()
        assert raw(invoice, "recipient_name") == saved
        target = target_backend(tmp_path)
        call_command("daten_verschluesseln", "--rueckweg-zu", str(target), stdout=io.StringIO())
        assert raw(invoice, "recipient_name") == "Erika Muster"
        assert raw(member.person, "last_name") == person_cipher
        assert raw(invoice, "recipient_email") == email_cipher
        decoded = raw(template, "signers")
        assert (json.loads(decoded) if isinstance(decoded, str) else decoded) == SNAPSHOT
        run()
        run("--pruefen")
        invoice.refresh_from_db()
        assert invoice.updated_at == stamp


@pytest.mark.django_db
def test_sammelloeschung_hat_je_organisation_den_richtigen_schluessel(orgs):
    with rls_bypass():
        comps = [
            Competition.objects.create(organization=orgs[key], title="Test", date=DAY)
            for key in ("a", "b")
        ]
        rows = [
            Starter.objects.create(
                organization=comp.organization, competition=comp, name="Erika Muster"
            )
            for comp in comps
        ]
        untouched = Starter.objects.create(
            organization=orgs["a"], competition=comps[0], name="Else Beispiel"
        )
        assert (
            update_encrypted(
                Starter.objects.filter(pk__in=[r.pk for r in rows]), name="Name auf Wunsch entfernt"
            )
            == 2
        )
        for row in rows:
            row.refresh_from_db()
            assert row.name == "Name auf Wunsch entfernt"
            assert (
                int.from_bytes(base64.b64decode(raw(row, "name")[5:])[:8], "big")
                == crypto.key_for_org(row.organization_id)[0]
            )
        untouched.refresh_from_db()
        assert untouched.name == "Else Beispiel"
        allowed = Starter.objects.filter(organization=orgs["a"])
        assert name_ids(allowed, "entfernt", fields=("name",)) == {rows[0].pk}
        assert list(ordered(allowed, "name").values_list("pk", flat=True)) == [
            untouched.pk,
            rows[0].pk,
        ]


@pytest.mark.langsam
@pytest.mark.django_db(transaction=True)
def test_rueckmigration_der_kopien_erfordert_gezielten_rueckweg(orgs, tmp_path):
    with rls_bypass():
        member, invoice, _, _, _ = records(orgs)
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [("billing", "0012_mahnung_archiv")]
        cipher = raw(member.person, "last_name")
        try:
            with pytest.raises(DatabaseError, match="Namenskopien entschlüsseln"):
                executor.migrate(previous)
            call_command(
                "daten_verschluesseln",
                "--rueckweg-zu",
                str(target_backend(tmp_path)),
                stdout=io.StringIO(),
            )
            MigrationExecutor(connection).migrate(previous)
            assert raw(invoice, "recipient_name") == "Erika Muster"
            assert raw(member.person, "last_name") == cipher
        finally:
            MigrationExecutor(connection).migrate(latest)
        run()
        run("--pruefen")
