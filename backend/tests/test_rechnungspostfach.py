"""Rechnungspostfach: E-Rechnungen aus Mails übernehmen (#374, billing/incoming_mail.py)."""
# ruff: noqa: F811

import datetime
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

import pytest
from django.utils import timezone

from billing import einvoice_validator, incoming_mail
from billing.incoming_mail import Result
from billing.models import BusinessPartner, IncomingInvoice, IncomingMail, IncomingMailbox
from core import virenscan
from core.tenancy import rls_bypass, tenant_context

from .test_e_rechnung import simple_pdf, zugferd_pdf
from .test_m9_billing import JSON, c, club  # noqa: F401

pytestmark = pytest.mark.django_db

XML = (Path(__file__).parent / "data" / "einvoice-en16931.xml").read_bytes()


@pytest.fixture(autouse=True)
def postfach(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"
    settings.EINVOICE_IMAP_HOST = "imap.example.org"
    settings.EINVOICE_IMAP_USER = "rechnung@example.org"
    settings.EINVOICE_IMAP_ADDRESS = ""
    settings.EINVOICE_IMAP_DONE_FOLDER = "INBOX.Verarbeitet"


@pytest.fixture(autouse=True)
def checks(monkeypatch):
    monkeypatch.setattr(
        einvoice_validator,
        "validate",
        lambda xml, timeout=None: ({"status": "valid", "validator": "Test", "messages": []}, b""),
    )


def address(club) -> str:
    with tenant_context(club.pk):
        return incoming_mail.address_for(club)


def mail(to, attachments=(), sender="buchhaltung@lieferant.example.com", **headers) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"Lieferant <{sender}>"
    msg["To"] = to
    msg["Subject"] = "Ihre Rechnung"
    msg["Message-ID"] = headers.pop("message_id", "<r1@lieferant.example.com>")
    for key, value in headers.items():
        msg[key.replace("_", "-")] = value
    msg.set_content("Anbei die Rechnung.")
    for name, data, maintype, subtype in attachments:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()


def xml_part(data=XML, name="rechnung.xml"):
    return (name, data, "application", "xml")


def pdf_part(data, name="rechnung.pdf"):
    return (name, data, "application", "pdf")


def invoices(club):
    with tenant_context(club.pk):
        return list(IncomingInvoice.objects.filter(organization=club).select_related("mail"))


def mails(club):
    with tenant_context(club.pk):
        return list(IncomingMail.objects.filter(organization=club))


class TestAdresse:
    def test_plus_adresse_je_verein(self, club):
        first = address(club)
        assert first.startswith("rechnung+") and first.endswith("@example.org")
        assert address(club) == first  # bleibt gleich
        with tenant_context(club.pk):
            incoming_mail.mailbox_of(club, renew=True)
        assert address(club) != first

    def test_api_zeigt_und_erneuert(self, c, club):
        url = f"/api/orgs/{club.pk}/finance/incoming/mailbox/"
        shown = c.get(url).json()
        assert shown["enabled"] and shown["address"] == address(club)
        renewed = c.post(url, {}, content_type=JSON).json()
        assert renewed["address"] != shown["address"]

    def test_ohne_postfach_keine_adresse(self, c, club, settings):
        settings.EINVOICE_IMAP_HOST = ""
        shown = c.get(f"/api/orgs/{club.pk}/finance/incoming/mailbox/").json()
        assert shown == {"enabled": False, "address": ""}
        assert incoming_mail.fetch() == 0

    def test_fremde_domain_und_alte_kennung_zaehlen_nicht(self, club):
        tag = address(club).split("+", 1)[1].split("@")[0]
        assert incoming_mail.find_org_id([f"rechnung+{tag}@example.net"]) is None
        assert incoming_mail.find_org_id([f"andere+{tag}@example.org"]) is None
        assert incoming_mail.find_org_id([f"rechnung+{tag}@example.org"]) == club.pk


class TestEineMail:
    def test_xml_wird_uebernommen(self, club):
        raw = mail(address(club), [xml_part()])
        assert incoming_mail.process_message(raw) == Result.MOVE
        [item] = invoices(club)
        assert item.validation == "pending" and item.data["payable"] == "119.00"
        assert item.mail.sender == "buchhaltung@lieferant.example.com"
        assert not item.mail.sender_known and item.mail.dismissed_at is not None
        assert item.created_by is None

    def test_zugferd_ja_einfache_pdf_nein(self, club):
        raw = mail(
            address(club),
            [pdf_part(zugferd_pdf(XML)), pdf_part(simple_pdf(), "anschreiben.pdf")],
        )
        assert incoming_mail.process_message(raw) == Result.MOVE
        [item] = invoices(club)
        assert item.content_type == "application/pdf" and item.data
        assert item.mail.skipped == [{"name": "anschreiben.pdf", "reason": "plain_pdf"}]

    def test_bekannter_absender(self, club):
        with tenant_context(club.pk):
            BusinessPartner.objects.create(
                organization=club,
                name="Lieferant",
                is_supplier=True,
                details={"email": "Buchhaltung@Lieferant.example.com"},
            )
        incoming_mail.process_message(mail(address(club), [xml_part()]))
        assert invoices(club)[0].mail.sender_known

    def test_ohne_e_rechnung_bleibt_als_hinweis(self, c, club):
        raw = mail(address(club), [pdf_part(simple_pdf())])
        assert incoming_mail.process_message(raw) == Result.KEEP
        assert invoices(club) == []
        [entry] = mails(club)
        assert entry.status == IncomingMail.Status.NO_INVOICE and entry.dismissed_at is None
        url = f"/api/orgs/{club.pk}/finance/incoming/mails/"
        [shown] = c.get(url).json()
        assert shown["sender"] == "buchhaltung@lieferant.example.com"
        assert c.post(f"{url}{entry.pk}/dismiss/", {}, content_type=JSON).status_code == 200
        assert c.get(url).json() == []

    def test_unbekannte_adresse_bleibt_liegen(self, club):
        raw = mail("rechnung+unbekannt99@example.org", [xml_part()])
        assert incoming_mail.process_message(raw) == Result.KEEP
        with rls_bypass():
            assert not IncomingInvoice.objects.exists() and not IncomingMail.objects.exists()

    def test_spam_wird_nicht_uebernommen(self, club):
        raw = mail(address(club), [xml_part()], X_Spam_Flag="YES")
        assert incoming_mail.process_message(raw) == Result.KEEP
        assert invoices(club) == [] and mails(club)[0].status == IncomingMail.Status.SPAM

    def test_schadsoftware(self, club):
        def scan(data, name, source):
            return b"BOESE" not in data

        raw = mail(address(club), [xml_part(), xml_part(XML + b"<!-- BOESE -->", "b.xml")])
        with mock.patch.object(virenscan, "inbound_ok", side_effect=scan):
            assert incoming_mail.process_message(raw) == Result.KEEP
        [item] = invoices(club)
        assert item.mail.skipped == [{"name": "b.xml", "reason": "virus"}]
        assert item.mail.dismissed_at is None  # Hinweis bleibt offen

    def test_doppelte_mail_und_datei(self, club):
        incoming_mail.process_message(mail(address(club), [xml_part()]))
        # Dieselbe Mail noch einmal: nichts Neues
        assert incoming_mail.process_message(mail(address(club), [xml_part()])) == Result.MOVE
        assert len(mails(club)) == 1
        # Dieselbe Datei in einer anderen Mail: kein zweiter Eingang
        incoming_mail.process_message(
            mail(address(club), [xml_part()], message_id="<r2@lieferant.example.com>")
        )
        assert len(invoices(club)) == 1 and len(mails(club)) == 2

    def test_alte_eintraege_werden_geloescht(self, club):
        incoming_mail.process_message(mail(address(club), [pdf_part(simple_pdf())]))
        incoming_mail.process_message(
            mail(address(club), [xml_part()], message_id="<r3@lieferant.example.com>")
        )
        old = timezone.now() - datetime.timedelta(days=incoming_mail.RETENTION_DAYS + 1)
        with rls_bypass():
            IncomingMail.objects.update(received_at=old)
        assert incoming_mail.purge_old() == 1
        # Die Mail mit übernommener Rechnung bleibt, solange es die Rechnung gibt
        assert [m.status for m in mails(club)] == [IncomingMail.Status.IMPORTED]


class TestAbholen:
    def _imap(self, bodies, copy_ok=True):
        imap = mock.MagicMock()
        imap.__enter__.return_value = imap

        def uid(cmd, *args):
            if cmd == "search":
                return ("OK", [b" ".join(bodies)])
            if cmd == "fetch":
                number, what = args
                if what == "(RFC822.SIZE)":
                    size = str(len(bodies[number])).encode()
                    return ("OK", [number + b" (UID " + number + b" RFC822.SIZE " + size + b")"])
                return ("OK", [(number + b" (BODY[] {1}", bodies[number]), b")"])
            if cmd == "copy":
                return ("OK" if copy_ok else "NO", [b""])
            return ("OK", [b""])

        imap.uid.side_effect = uid
        return imap

    def test_verschiebt_nur_uebernommene(self, club):
        bodies = {
            b"7": mail(address(club), [xml_part()]),
            b"8": mail(
                address(club), [pdf_part(simple_pdf())], message_id="<r4@lieferant.example.com>"
            ),
        }
        imap = self._imap(bodies)
        with mock.patch("billing.incoming_mail.imaplib.IMAP4_SSL", return_value=imap):
            assert incoming_mail.fetch() == 2
        imap.uid.assert_any_call("copy", b"7", '"INBOX.Verarbeitet"')
        imap.uid.assert_any_call("store", b"7", "+FLAGS", "(\\Deleted)")
        imap.uid.assert_any_call("store", b"8", "+FLAGS", "(\\Seen)")
        assert ("store", b"8", "+FLAGS", "(\\Deleted)") not in [
            call.args for call in imap.uid.call_args_list
        ]
        imap.expunge.assert_called_once()
        assert len(invoices(club)) == 1

    def test_ohne_ordner_nur_gelesen(self, club):
        imap = self._imap({b"7": mail(address(club), [xml_part()])}, copy_ok=False)
        with mock.patch("billing.incoming_mail.imaplib.IMAP4_SSL", return_value=imap):
            assert incoming_mail.fetch() == 1
        imap.create.assert_called_once()
        imap.expunge.assert_not_called()
        assert len(invoices(club)) == 1

    def test_scanner_aus_mail_bleibt_ungelesen(self, club):
        imap = self._imap({b"7": mail(address(club), [xml_part()])})
        with (
            mock.patch("billing.incoming_mail.imaplib.IMAP4_SSL", return_value=imap),
            mock.patch.object(virenscan, "inbound_ok", side_effect=virenscan.ScanUnavailable()),
        ):
            assert incoming_mail.fetch() == 0
        assert not [c for c in imap.uid.call_args_list if c.args[0] == "store"]
        assert invoices(club) == []

    def test_zu_grosse_mail_nur_kopf(self, club):
        raw = mail(address(club), [xml_part()])
        imap = self._imap({b"7": raw})
        with (
            mock.patch.object(incoming_mail, "MAX_RAW_BYTES", 100),
            mock.patch("billing.incoming_mail.imaplib.IMAP4_SSL", return_value=imap),
        ):
            assert incoming_mail.fetch() == 1
        [entry] = mails(club)
        assert entry.status == IncomingMail.Status.ERROR and invoices(club) == []


def test_kennung_ist_rls_geschuetzt(club, orgs):
    address(club)
    with tenant_context(orgs["b"].pk):
        assert not IncomingMailbox.objects.exists()
