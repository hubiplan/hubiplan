"""Zugriffslog ohne Geheimnisse im Pfad (Gesamtaudit 19.11., S-15)."""

import datetime
import importlib.util
from pathlib import Path

import pytest

from core.accesslog import HIDDEN, AccessLogger, log_path

GEHEIM = "Zx3kQ9vTt7Lm2PpR8sWbYc4d"


@pytest.mark.parametrize(
    ("pfad", "erwartet"),
    [
        (f"/api/public/scan/{GEHEIM}/", f"/api/public/scan/{HIDDEN}/"),
        (f"/api/public/scan/{GEHEIM}/cash/", f"/api/public/scan/{HIDDEN}/cash/"),
        (f"/api/public/rsvp/{GEHEIM}/attachments/7/", f"/api/public/rsvp/{HIDDEN}/attachments/7/"),
        (f"/api/public/registration/mine/{GEHEIM}/", f"/api/public/registration/mine/{HIDDEN}/"),
        (f"/api/public/registration/{GEHEIM}/", f"/api/public/registration/{HIDDEN}/"),
        (f"/api/public/feed/{GEHEIM}/termine.ics", f"/api/public/feed/{HIDDEN}/termine.ics"),
    ],
)
def test_geheimnisse_im_pfad_fehlen_im_log(pfad, erwartet):
    assert log_path(pfad) == erwartet
    assert GEHEIM not in log_path(pfad)


def test_gewoehnliche_pfade_bleiben_lesbar():
    assert log_path("/api/health/") == "/api/health/"
    assert log_path("/api/orgs/12/members/") == "/api/orgs/12/members/"
    assert log_path("") == ""
    assert log_path(None) is None


def test_unbekannte_oeffentliche_adresse_wird_gekuerzt():
    # Vertippter oder veralteter Link: keine Route, das Geheimnis steht trotzdem im Pfad
    pfad = f"/api/public/gibt-es-nicht/{GEHEIM}/weiter/"
    assert log_path(pfad) == f"/api/public/gibt-es-nicht/{HIDDEN}/weiter/"
    assert log_path("/api/gibt-es-nicht/") == "/api/gibt-es-nicht/"


def test_fehler_beim_aufloesen_stoert_das_log_nicht(monkeypatch):
    def kaputt(path):
        raise RuntimeError("erfundener Fehler")

    monkeypatch.setattr("core.accesslog._log_path", kaputt)
    assert log_path(f"/api/public/scan/{GEHEIM}/cash/") == f"/api/public/scan/{HIDDEN}/{HIDDEN}/"
    assert log_path("/api/orgs/12/members/") == "/api/orgs/12/members/"


def test_gunicorn_nutzt_den_logger():
    spec = importlib.util.spec_from_file_location(
        "test_gunicorn_zugriffslog", Path(__file__).parents[1] / "gunicorn.conf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.logger_class == "core.accesslog.AccessLogger"


def test_logger_ersetzt_pfad_und_rohzeile():
    class Antwort:
        status = "200 OK"
        sent = 12
        headers = ()

    class Anfrage:
        headers = ()

    environ = {
        "REQUEST_METHOD": "GET",
        "RAW_URI": f"/api/public/scan/{GEHEIM}/?x=1",
        "PATH_INFO": f"/api/public/scan/{GEHEIM}/",
        "QUERY_STRING": "x=1",
        "SERVER_PROTOCOL": "HTTP/1.1",
    }
    logger = AccessLogger.__new__(AccessLogger)
    atoms = AccessLogger.atoms(logger, Antwort(), Anfrage(), environ, datetime.timedelta(0))
    assert atoms["U"] == f"/api/public/scan/{HIDDEN}/"
    assert GEHEIM not in atoms["r"]
