"""Gesamtaudit 11.11.2026, Fachfrage 4: Virenprüfung nur für Eingänge von außen
(``VIRUS_SCAN_SCOPE=extern``)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from core import virenscan

from .test_documents import board_fed, pdf, private_root, setup  # noqa: F401
from .test_virenscan import EICAR, _upload, clamd  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def extern(settings):
    settings.VIRUS_SCAN_SCOPE = "extern"


def _handler(user):
    request = RequestFactory().post("/api/public/upload/")
    request.user = user
    handler = virenscan.ClamavUploadHandler(request)
    handler.new_file("file", "bild.jpg", "image/jpeg", 100, None, {})
    return handler


def test_angemeldet_ohne_pruefung(clamd, extern, api, board_fed, setup):
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 201, resp.json()
    assert clamd.scanned == []


def test_von_aussen_mit_pruefung(clamd, extern):
    handler = _handler(AnonymousUser())
    handler.receive_data_chunk(EICAR, 0)
    with pytest.raises(virenscan.VirusFound):
        handler.file_complete(len(EICAR))
    assert clamd.scanned == [EICAR]


def test_mails_und_verbund_immer(clamd, extern):
    assert not virenscan.inbound_ok(EICAR, "rechnung.pdf", "Mail an das Rechnungspostfach")
    assert virenscan.inbound_ok(b"%PDF-1.4 sauber", "a.pdf", "Mail an das Rechnungspostfach")


def test_standard_prueft_alle(clamd, api, board_fed, setup):
    resp = _upload(api, board_fed, setup, pdf())
    assert resp.status_code == 201, resp.json()
    assert clamd.scanned
