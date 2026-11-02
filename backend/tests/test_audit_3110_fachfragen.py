"""Fachfragen aus dem Audit „Datenspeicherung und Berechnungen“ vom 31.10.2026."""

import datetime
from decimal import Decimal

import pytest

from billing.models import Invoice
from billing.services import Period, rate_share
from core.tenancy import rls_bypass

from .test_audit_finanzen import invoice  # noqa: F401
from .test_m9_billing import _private, base, c, club, members, setup, start_run, zug  # noqa: F401


def period(index, months, rhythm="monthly"):
    d = datetime.date(2025, 1, 1)
    return Period(2025, index, rhythm, d, d, months, "")


class TestRestcent:
    """Fachfrage 1: alle Raten eines Jahres ergeben genau den Jahresbetrag."""

    @pytest.mark.parametrize(
        "yearly,months", [("100.00", 1), ("100.00", 3), ("120.00", 1), ("99.99", 6), ("10.01", 1)]
    )
    def test_summe_stimmt(self, yearly, months):
        count = 12 // months
        shares = [rate_share(Decimal(yearly), period(i, months)) for i in range(1, count + 1)]
        assert sum(shares) == Decimal(yearly)
        assert max(shares) - min(shares) <= Decimal("0.01")
        # Restcents vorne
        assert shares == sorted(shares, reverse=True)

    def test_beispiel(self):
        shares = [rate_share(Decimal("100.00"), period(i, 1)) for i in range(1, 13)]
        assert shares[:4] == [Decimal("8.34")] * 4 and shares[4:] == [Decimal("8.33")] * 8

    def test_jaehrlich(self):
        assert rate_share(Decimal("100.005"), period(1, 12, "yearly")) == Decimal("100.01")


@pytest.mark.django_db
class TestRechnungAbgelegt:
    """Fachfrage 4: die ausgegebene Fassung bleibt, auch wenn sich der Briefkopf ändert."""

    def test_erster_abruf_legt_ab(self, c, base, invoice, club):  # noqa: F811
        first = c.get(f"{base}/invoices/{invoice.pk}/pdf/")
        assert first.status_code == 200 and first.content.startswith(b"%PDF")
        with rls_bypass():
            stored = Invoice.objects.get(pk=invoice.pk)
        assert stored.issued_pdf and len(stored.issued_pdf_sha256) == 64
        club.name = "Ganz anderer Name"
        club.save()
        again = c.get(f"{base}/invoices/{invoice.pk}/pdf/")
        assert again.content == first.content

    def test_nachtraeglich_im_hintergrund(self, invoice):  # noqa: F811
        from billing.archive import archive_missing

        assert archive_missing() >= 1
        with rls_bypass():
            assert Invoice.objects.get(pk=invoice.pk).issued_pdf

    def test_sammel_pdf_nimmt_ausgegebene_fassung(self, c, base, members, club):  # noqa: F811
        """Audit 02.11. BP-F02: Sammel-PDF eines Laufs = abgelegte Einzelfassungen."""
        import pypdfium2 as pdfium

        run = start_run(c, base).json()
        assert c.post(f"{base}/runs/{run['id']}/finalize/").status_code == 200
        with rls_bypass():
            invoice = Invoice.objects.filter(run_id=run["id"]).order_by("pk").first()
        first = c.get(f"{base}/invoices/{invoice.pk}/pdf/").content
        club.name = "Ganz anderer Name"
        club.save()
        batch = c.get(f"{base}/runs/{run['id']}/pdf/")
        assert batch.status_code == 200, batch.content[:200]
        doc = pdfium.PdfDocument(batch.content)
        text = "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
        single = pdfium.PdfDocument(first)
        assert len(doc) >= len(single)
        # Die schon ausgegebene Rechnung erscheint mit dem alten Namen
        old = single[0].get_textpage().get_text_range()
        assert old in text
