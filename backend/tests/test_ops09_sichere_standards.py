"""Sichere Standards ohne Proxy-Liste (Gesamtaudit 15.11., OPS-09). Erfundene Adressen."""

import pytest
from django.core.checks import run_checks
from django.test import RequestFactory

from core.ratelimit import client_ip, from_proxy


@pytest.fixture
def ohne_liste(settings):
    settings.TRUSTED_PROXY_HOSTS = []
    settings.WEBSITE_HOSTS = []
    settings.DEBUG = False
    settings.PROXY_TRUST_ALL = False


def _anfrage():
    return RequestFactory().get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_FORWARDED_FOR="198.51.100.7")


def test_ohne_liste_zaehlt_die_verbindung(ohne_liste):
    request = _anfrage()
    assert not from_proxy(request)
    assert client_ip(request) == "192.0.2.10"


def test_altes_verhalten_nur_ausdruecklich(ohne_liste, settings):
    settings.PROXY_TRUST_ALL = True
    assert client_ip(_anfrage()) == "198.51.100.7"


def test_systemcheck_warnt(ohne_liste):
    ids = {m.id for m in run_checks(include_deployment_checks=True)}
    assert "hubiplan.W001" in ids


def test_systemcheck_still_mit_liste(ohne_liste, settings):
    settings.TRUSTED_PROXY_HOSTS = ["web"]
    ids = {m.id for m in run_checks(include_deployment_checks=True)}
    assert "hubiplan.W001" not in ids
