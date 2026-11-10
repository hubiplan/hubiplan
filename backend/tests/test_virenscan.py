"""Fachfrage 4 (31.10.b): Virenprüfung beim Hochladen mit clamd (hier ein nachgebauter
clamd über einen Unix-Socket; erfundene Daten)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import socket
import struct
import threading

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile

from core import virenscan

from .test_documents import base, board_fed, folder, pdf, private_root, setup  # noqa: F401

pytestmark = pytest.mark.django_db
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class FakeClamd:
    """Antwortet wie clamd auf zINSTREAM: FOUND bei der EICAR-Testzeichenkette."""

    def __init__(self, path):
        self.path = str(path)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(5)
        self.scanned = []
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                data = b""
                while not data.endswith(b"\0"):
                    data += conn.recv(1)
                assert data == b"zINSTREAM\0"
                body = b""
                while True:
                    head = b""
                    while len(head) < 4:
                        part = conn.recv(4 - len(head))
                        if not part:
                            break
                        head += part
                    if len(head) < 4:
                        break
                    (size,) = struct.unpack("!L", head)
                    if size == 0:
                        self.scanned.append(body)
                        reply = (
                            b"stream: Eicar-Test-Signature FOUND\0"
                            if EICAR in body
                            else b"stream: OK\0"
                        )
                        conn.sendall(reply)
                        break
                    chunk = b""
                    while len(chunk) < size:
                        chunk += conn.recv(size - len(chunk))
                    body += chunk

    def close(self):
        self.server.close()


@pytest.fixture
def clamd(settings, tmp_path):
    settings.SECURITY_ALERTS = True
    settings.SECURITY_ALERT_EMAIL = "alarm@example.org"
    fake = FakeClamd(tmp_path / "clamd.ctl")
    settings.CLAMD_SOCKET = fake.path
    yield fake
    fake.close()


def _upload(api, board_fed, setup, file):
    c = api(board_fed)
    b = base(setup["federation"])
    f = folder(c, b)
    return c.post(f"{b}folders/{f['id']}/documents/", {"title": "Protokoll", "file": file})


def test_sauber_geht_durch(clamd, api, board_fed, setup):
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 201, resp.json()
    assert clamd.scanned == [b"%PDF-1.4 erfundenes Protokoll"]


def test_fund_wird_abgelehnt_und_gemeldet(clamd, api, board_fed, setup):
    from documents.models import Document

    mail.outbox.clear()
    resp = _upload(api, board_fed, setup, SimpleUploadedFile("rechnung.pdf", b"%PDF-1.4 " + EICAR))
    assert resp.status_code == 422
    assert "Schadsoftware" in resp.json()["detail"]
    assert not Document.objects.exists()
    assert any("Schadsoftware" in m.subject for m in mail.outbox)


def _version_url(resp) -> str:
    return resp.json()["current"]["url"]


def test_clamd_aus_quarantaene(settings, tmp_path, api, board_fed, setup):
    """Gesamtaudit 10.11., Fachfrage 2: Scanner aus → Datei angenommen, aber gesperrt,
    bis die Nachprüfung sie sauber findet."""
    from core.models import QuarantinedFile

    settings.CLAMD_SOCKET = str(tmp_path / "fehlt.ctl")
    mail.outbox.clear()
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 201, resp.json()
    assert resp.json()["current"]["scan"] == "pending"
    held = QuarantinedFile.objects.get()
    assert held.status == "pending"
    c = api(board_fed)
    assert c.get(_version_url(resp)).status_code == 423
    # Scanner weiter aus: bleibt gesperrt
    assert virenscan.recheck_quarantine()["waiting"] == 1
    fake = FakeClamd(tmp_path / "wieder.ctl")
    try:
        settings.CLAMD_SOCKET = fake.path
        assert virenscan.recheck_quarantine()["released"] == 1
    finally:
        fake.close()
    assert fake.scanned == [b"%PDF-1.4 erfundenes Protokoll"]
    assert not QuarantinedFile.objects.exists()
    assert c.get(_version_url(resp)).status_code == 200


def test_fund_in_quarantaene_bleibt_gesperrt(settings, tmp_path, api, board_fed, setup):
    from core.models import QuarantinedFile

    settings.SECURITY_ALERTS = True
    settings.SECURITY_ALERT_EMAIL = "alarm@example.org"
    settings.CLAMD_SOCKET = str(tmp_path / "fehlt.ctl")
    resp = _upload(api, board_fed, setup, SimpleUploadedFile("r.pdf", b"%PDF-1.4 " + EICAR))
    assert resp.status_code == 201, resp.json()
    fake = FakeClamd(tmp_path / "wieder.ctl")
    mail.outbox.clear()
    try:
        settings.CLAMD_SOCKET = fake.path
        assert virenscan.recheck_quarantine()["infected"] == 1
    finally:
        fake.close()
    held = QuarantinedFile.objects.get()
    assert held.status == "infected" and "Eicar" in held.signature
    assert any("Quarantäne" in m.subject for m in mail.outbox)
    response = api(board_fed).get(_version_url(resp))
    assert response.status_code == 423
    assert "Schadsoftware" in response.json()["detail"]


def test_pflicht_ohne_scanner_haelt_zurueck(settings, api, board_fed, setup):
    from core.models import QuarantinedFile

    settings.CLAMD_SOCKET = ""
    settings.VIRUS_SCAN_REQUIRED = True
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 201, resp.json()
    assert QuarantinedFile.objects.count() == 1
    assert api(board_fed).get(_version_url(resp)).status_code == 423


def test_zu_gross_mit_pflicht_abgelehnt(clamd, settings, api, board_fed, setup):
    settings.CLAMD_MAX_BYTES = 10
    settings.VIRUS_SCAN_REQUIRED = True
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 422
    assert "zu groß" in resp.json()["detail"]


def test_quarantaene_nur_wo_erlaubt():
    """Andere Uploads (Importe, Bilder) lehnen bei ausgefallenem Scanner weiter ab."""
    from types import SimpleNamespace

    from documents.views import _FolderDocuments

    class Ohne:
        pass

    def request(cls):
        func = SimpleNamespace(cls=cls)
        return SimpleNamespace(resolver_match=SimpleNamespace(func=func))

    assert virenscan.quarantine_allowed(request(_FolderDocuments))
    assert not virenscan.quarantine_allowed(request(Ohne))
    assert not virenscan.quarantine_allowed(SimpleNamespace())


def test_weitergabe_hebt_quarantaene_nach_pruefung_auf(clamd, settings):
    from django.core.cache import cache
    from django.core.files.base import ContentFile

    from core.models import QuarantinedFile

    cache.clear()
    QuarantinedFile.objects.create(name="x/a.pdf")
    file = ContentFile(b"harmlos", name="x/a.pdf")
    settings.CLAMD_SOCKET = ""
    with pytest.raises(virenscan.Quarantined):
        virenscan.release_ok(file, "a.pdf", "Test", key="q:1")
    settings.CLAMD_SOCKET = clamd.path
    virenscan.release_ok(file, "a.pdf", "Test", key="q:1")
    assert not QuarantinedFile.objects.exists()


def test_zu_gross_bleibt_ungeprueft(clamd, settings, api, board_fed, setup):
    settings.CLAMD_MAX_BYTES = 10
    settings.VIRUS_SCAN_REQUIRED = False
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 201, resp.json()
    assert clamd.scanned == []


def test_ohne_socket_keine_pruefung(settings, api, board_fed, setup):
    settings.CLAMD_SOCKET = ""
    resp = _upload(api, board_fed, setup, SimpleUploadedFile("x.pdf", b"%PDF-1.4 " + EICAR))
    assert resp.status_code == 201


def test_scan_bytes(clamd):
    virenscan.scan_bytes(b"harmlos", "a.txt")
    with pytest.raises(virenscan.VirusFound):
        virenscan.scan_bytes(EICAR, "b.txt")


def test_inbound_ok_mail_anhang(clamd):
    """GA-I01: Anhänge aus Mails werden geprüft, ein Fund wird übersprungen."""
    from email.message import EmailMessage

    from circulars.inbound import extract

    assert virenscan.inbound_ok(b"harmlos", "a.pdf", "Test")
    assert not virenscan.inbound_ok(EICAR, "b.pdf", "Test")

    msg = EmailMessage()
    msg["Subject"] = "Rundschreiben"
    msg["From"] = "vorstand@example.org"
    msg.set_content("Hallo zusammen")
    msg.add_attachment(b"%PDF-1.4 sauber", maintype="application", subtype="pdf", filename="a.pdf")
    msg.add_attachment(
        b"%PDF-1.4 " + EICAR, maintype="application", subtype="pdf", filename="b.pdf"
    )
    result = extract(msg)
    assert [name for name, _ in result.pdfs] == ["a.pdf"]
    assert any("b.pdf" in s and "Schadsoftware" in s for s in result.skipped)


def test_mail_bleibt_bei_scanner_ausfall_liegen(settings, tmp_path):
    """Fachfrage 2 (10.11.): Anhänge nicht prüfbar → Mail bleibt ungelesen im Postfach."""
    from email.message import EmailMessage
    from unittest import mock

    from circulars import inbound
    from circulars.models import InboundMail

    settings.CLAMD_SOCKET = str(tmp_path / "fehlt.ctl")
    msg = EmailMessage()
    msg["Subject"] = "Rundschreiben"
    msg["From"] = "vorstand@example.org"
    msg.set_content("Hallo zusammen")
    msg.add_attachment(b"%PDF-1.4 sauber", maintype="application", subtype="pdf", filename="a.pdf")
    with pytest.raises(virenscan.ScanUnavailable):
        inbound.extract(msg)

    settings.INBOUND_IMAP_HOST = "imap.example.org"
    imap = mock.MagicMock()
    imap.__enter__.return_value = imap
    imap.uid.side_effect = lambda cmd, *args: {
        "search": ("OK", [b"7 8"]),
        "fetch": ("OK", [(b"7 (BODY[] {1}", msg.as_bytes()), b")"]),
        "store": ("OK", [b""]),
    }[cmd]
    with (
        mock.patch("circulars.inbound.imaplib.IMAP4_SSL", return_value=imap),
        mock.patch("circulars.inbound._process", side_effect=virenscan.ScanUnavailable()),
    ):
        assert inbound.fetch_inbound() == 0
    stores = [c for c in imap.uid.call_args_list if c.args[0] == "store"]
    # Nur Inhaltsabrufe zählen; vorher fragt der Abruf die Größe ab (Gesamtaudit 10.11. S03)
    fetches = [c for c in imap.uid.call_args_list if c.args[0] == "fetch" and "BODY" in c.args[-1]]
    assert stores == [] and [c.args[1] for c in fetches] == [b"7"]
    assert not InboundMail.objects.exists()


# --- Fachfrage FQ16: vor der Weitergabe noch einmal prüfen ---


class TestVorDerWeitergabe:
    @pytest.fixture(autouse=True)
    def _leer(self):
        from django.core.cache import cache

        cache.clear()

    def test_sauber_wird_gemerkt(self, clamd):
        from django.core.files.base import ContentFile

        virenscan.release_ok(ContentFile(b"harmlos"), "a.pdf", "Test", key="t:1")
        virenscan.release_ok(ContentFile(b"harmlos"), "a.pdf", "Test", key="t:1")
        assert clamd.scanned == [b"harmlos"]

    def test_fund_wird_nicht_weitergegeben(self, clamd):
        from django.core.files.base import ContentFile

        with pytest.raises(virenscan.VirusFound):
            virenscan.release_ok(ContentFile(EICAR), "b.pdf", "Test", key="t:2")

    def test_ohne_scanner(self, settings):
        from django.core.files.base import ContentFile

        settings.CLAMD_SOCKET = ""
        settings.VIRUS_SCAN_REQUIRED = False
        virenscan.release_ok(ContentFile(EICAR), "c.pdf", "Test", key="t:3")
        settings.VIRUS_SCAN_REQUIRED = True
        with pytest.raises(virenscan.NotScanned):
            virenscan.release_ok(ContentFile(b"x"), "c.pdf", "Test", key="t:3")

    def test_zu_gross_nur_ohne_pflicht(self, clamd, settings):
        from django.core.files.base import ContentFile

        settings.CLAMD_MAX_BYTES = 4
        virenscan.release_ok(ContentFile(b"0123456789"), "d.pdf", "Test", key="t:4")
        settings.VIRUS_SCAN_REQUIRED = True
        with pytest.raises(virenscan.NotScanned):
            virenscan.release_ok(ContentFile(b"0123456789"), "d.pdf", "Test", key="t:5")

    def test_oeffentliches_dokument(self, settings, tmp_path, api, board_fed, setup):
        """Hochgeladen ohne Scanner, öffentlich abgerufen mit Scanner: abgelehnt."""
        from django.test import Client

        settings.CLAMD_SOCKET = ""
        c = api(board_fed)
        b = base(setup["federation"])
        f = folder(c, b, "Aufnahme", "public")
        c.post(
            f"{b}folders/{f['id']}/documents/",
            {"title": "Antrag", "file": SimpleUploadedFile("a.pdf", b"%PDF-1.4 " + EICAR)},
        )
        folders = c.get(b).json()["folders"]
        url = next(x for x in folders if x["id"] == f["id"])["public_url"]
        anon = Client()
        doc_url = anon.get(url).json()["documents"][0]["url"]
        fake = FakeClamd(tmp_path / "clamd2.ctl")
        try:
            settings.CLAMD_SOCKET = fake.path
            assert anon.get(doc_url).status_code == 422
        finally:
            fake.close()
