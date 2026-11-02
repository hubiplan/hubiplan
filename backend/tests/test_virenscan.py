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


def test_clamd_aus_lehnt_ab(settings, tmp_path, api, board_fed, setup):
    settings.CLAMD_SOCKET = str(tmp_path / "fehlt.ctl")
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 503


def test_zu_gross_bleibt_ungeprueft(clamd, settings, api, board_fed, setup):
    settings.CLAMD_MAX_BYTES = 10
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
