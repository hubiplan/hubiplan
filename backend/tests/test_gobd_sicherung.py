"""GoBD: Originale, Sperren, Fristbeginn und ausgegebene Fassungen."""

# ruff: noqa: F811
import base64
import csv
import datetime
import io
import zipfile
from urllib.parse import unquote

import pytest
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone

from accounts.models import User
from audit.log import record
from audit.models import AuditEntry
from billing import archive, services
from billing.models import DunningLevel, Invoice
from finance import retention
from finance.models import BankStatement, Booking, Receipt, YearClosing

from .test_m9_billing import JSON, base, c, club, members, setup, start_run, zug  # noqa: F401
from .test_storno_festschreibung import book, fin  # noqa: F401

pytestmark = pytest.mark.django_db


@override_settings(HUBIPLAN_LANGUAGES=["de", "en"])
def test_englische_oberflaeche_aendert_die_sprache_des_pruefexports_nicht(c, fin, setup):
    booking = book(c, fin, account=setup["bank"], category=setup["cat"], tax_area="ideal")
    User.objects.filter(pk=c.session["_auth_user_id"]).update(language="en")
    changed = c.patch(f"{fin}/bookings/{booking.pk}/", {"text": "Updated note"}, content_type=JSON)
    assert changed.status_code == 200
    assert "Entry" in unquote(changed["X-Change-Label"])
    assert "changed" in unquote(changed["X-Change-Label"])
    assert AuditEntry.objects.filter(object_type="Buchung", object_id=str(booking.pk)).exists()
    response = c.get(f"{fin}/export/?jahr={timezone.localdate().year}")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as exported:
        rows = list(
            csv.DictReader(
                io.StringIO(exported.read("buchungen.csv").decode("utf-8-sig")), delimiter=";"
            )
        )
    assert rows[0]["Art"] == "Einnahme"
    assert rows[0]["Steuerbereich"] == "ideeller Bereich"


def test_beleg_bleibt_bei_buchungsloeschung(c, fin, setup):
    b = book(c, fin, account=setup["bank"], category=setup["cat"])
    receipt = Receipt(organization=b.organization, booking=b, name="Original")
    receipt.file.save("beleg.txt", ContentFile(b"Original"))
    assert c.delete(f"{fin}/bookings/{b.pk}/").status_code == 400
    assert Booking.objects.filter(pk=b.pk).exists()
    with Receipt.objects.get(booking=b).file.open("rb") as fh:
        assert fh.read() == b"Original"


def test_bankoriginal_auch_ohne_zugeordnete_umsaetze_erhalten(c, fin, setup, club):
    statement = BankStatement.objects.create(
        organization=club, account_id=setup["bank"], file_name="auszug.xml"
    )
    statement.source.save("auszug.xml", ContentFile(b"Bankoriginal"))
    assert c.delete(f"{fin}/bank-statements/{statement.pk}/").status_code == 400
    statement.refresh_from_db()
    with statement.source.open("rb") as fh:
        assert fh.read() == b"Bankoriginal"


def test_zwei_pruefexporte_enthalten_versiegelte_protokolle(c, fin, setup):
    book(c, fin, account=setup["bank"], category=setup["cat"])
    for _ in range(2):
        response = c.get(f"{fin}/export/?jahr={timezone.localdate().year}")
        assert response.status_code == 200
        content = b"".join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive_file:
            rows = list(
                csv.DictReader(
                    io.StringIO(archive_file.read("protokoll.csv").decode("utf-8-sig")),
                    delimiter=";",
                )
            )
        assert rows
        assert all(row["Lfd. Nr."] and row["Prüfsumme"] for row in rows)


def test_festschreiben_nicht_rueckgaengig(c, fin, setup):
    response = c.patch(
        f"{fin}/settings/", {"locked_until": timezone.localdate().isoformat()}, content_type=JSON
    )
    assert response.status_code == 200
    assert response.get("X-Change-Undoable", "0") == "0"
    assert "X-Change-Set" not in response


def test_gebuchte_kategorie_und_alter_anfangsbestand_gesperrt(c, fin, setup):
    book(c, fin, account=setup["bank"], category=setup["cat"])
    assert (
        c.patch(
            f"{fin}/settings/",
            {"locked_until": timezone.localdate().isoformat()},
            content_type=JSON,
        ).status_code
        == 200
    )
    assert (
        c.patch(
            f"{fin}/categories/{setup['cat']}/", {"name": "Andere Zuordnung"}, content_type=JSON
        ).status_code
        == 400
    )
    assert (
        c.patch(
            f"{fin}/accounts/{setup['bank']}/", {"opening_balance": "100"}, content_type=JSON
        ).status_code
        == 400
    )


def test_frist_ab_tatsaechlicher_entstehung_und_abschluss(c, fin, setup, club):
    b = book(c, fin, account=setup["bank"], date="2025-12-31", category=setup["cat"])
    Booking.objects.filter(pk=b.pk).update(
        created_at=timezone.make_aware(datetime.datetime(2027, 1, 2))
    )
    closing = YearClosing.objects.create(organization=club, year=2025)
    YearClosing.objects.filter(pk=closing.pk).update(
        closed_at=timezone.make_aware(datetime.datetime(2028, 3, 15))
    )
    assert retention.due_dates(club, 2025) == (datetime.date(2036, 1, 1), datetime.date(2039, 1, 1))


def test_mahnung_bleibt_nach_zahlung_identisch(c, base, setup, members, club):
    run = start_run(c, base).json()
    assert c.post(f"{base}/runs/{run['id']}/finalize/").status_code == 200
    invoice = Invoice.objects.filter(organization=club, status="open").first()
    level = DunningLevel.objects.filter(organization=club).first()
    if level is None:
        level = DunningLevel.objects.create(organization=club, level=1, name="Erinnerung", days=7)
    dunning = services.dun(invoice, level, None)
    before = archive.archived_dunning(dunning)
    Invoice.objects.filter(pk=invoice.pk).update(paid=invoice.total, status="paid")
    assert archive.archived_dunning(dunning) == before
    dunning.refresh_from_db()
    assert dunning.issued_pdf_sha256


def test_spaetere_rechnungsausgabe_verlaengert_belegfrist(
    c, base, setup, members, club, monkeypatch
):
    start_run(c, base)
    invoice = Invoice.objects.filter(organization=club, status="draft").first()
    instant = timezone.make_aware(datetime.datetime(2028, 1, 2, 12))
    monkeypatch.setattr(timezone, "now", lambda: instant)
    services.finalize(invoice)
    record(club, None, "update", invoice, {"Status": ["draft", "open"]})
    assert retention.due_dates(club, invoice.year)[0] == datetime.date(2037, 1, 1)


def test_verbund_gibt_archivierte_rechnung_aus(c, base, setup, members, club):
    from peering.packet_invoices import _issue_data

    run = start_run(c, base).json()
    assert c.post(f"{base}/runs/{run['id']}/finalize/").status_code == 200
    invoice = Invoice.objects.filter(organization=club, status="open").first()
    payload = _issue_data(invoice, "probe")
    invoice.refresh_from_db()
    with invoice.issued_pdf.open("rb") as fh:
        assert base64.b64decode(payload["pdf"]) == fh.read()


@pytest.mark.django_db(transaction=True)
def test_audit_ohne_aeussere_transaktion_sofort_versiegelt(club):
    entry = record(club, None, "update", club, {"Probe": [None, "Neu"]})
    entry.refresh_from_db()
    assert entry.seq is not None and entry.hash
