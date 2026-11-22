"""Meldungen des Browsers über CSP-Verstöße (Härtung B3)."""

from __future__ import annotations

import json

import pytest
from django.core import mail
from django.test import Client

from core.tenancy import rls_bypass
from organizations import csp_reports
from organizations.models import CspReport

from .factories import make_user

URL = "/api/csp-report/"
CSP = "application/csp-report"
REPORTS = "application/reports+json"


def alt(**werte) -> str:
    return json.dumps(
        {
            "csp-report": {
                "document-uri": "https://verein.example/orgs/7/members/123?suche=Musterfrau",
                "violated-directive": "script-src-elem",
                "effective-directive": "script-src-elem",
                "blocked-uri": "https://fremd.example/boese.js?x=1",
                **werte,
            }
        }
    )


def neu(**werte) -> str:
    return json.dumps(
        [
            {
                "type": "csp-violation",
                "url": "https://verein.example/finanzen",
                "body": {
                    "documentURL": "https://verein.example/finanzen",
                    "effectiveDirective": "img-src",
                    "blockedURL": "https://bilder.example/a.png",
                    **werte,
                },
            },
            {"type": "deprecation", "body": {}},
        ]
    )


def alle():
    with rls_bypass():
        return list(CspReport.objects.order_by("id"))


@pytest.fixture
def anon():
    return Client()


def test_bereinigen():
    assert (
        csp_reports.clean_blocked("https://Fremd.example:8443/a/b?c=d") == "https://fremd.example"
    )
    assert csp_reports.clean_blocked("inline") == "inline"
    assert csp_reports.clean_blocked("data:text/javascript,alert(1)") == "data"
    assert csp_reports.clean_blocked("chrome-extension://abcdef/x.js") == ""
    assert csp_reports.clean_blocked("javascript:alert(1)") == ""
    assert csp_reports.clean_blocked("https://<script>") == ""
    assert csp_reports.clean_page("https://v.example/orgs/7/members/123?x=1") == "/orgs/…/members/…"
    assert csp_reports.clean_page("https://v.example/a/Erika Musterfrau/b") == "/a/…/b"
    assert csp_reports.clean_page("") == "/"


def test_meldung_beider_formate_ohne_anmeldung(db, anon):
    assert anon.post(URL, alt(), content_type=CSP).status_code == 204
    assert anon.post(URL, neu(), content_type=REPORTS).status_code == 204
    assert anon.post(URL, alt(), content_type=CSP).status_code == 204
    erste, zweite = alle()
    assert (erste.directive, erste.blocked, erste.page, erste.count) == (
        "script-src-elem",
        "https://fremd.example",
        "/orgs/…/members/…",
        2,
    )
    assert (zweite.directive, zweite.blocked, zweite.page) == (
        "img-src",
        "https://bilder.example",
        "/finanzen",
    )
    # nichts von der Person: kein Suchwort, keine Nummer, kein voller Pfad
    gespeichert = " ".join(f"{r.directive} {r.blocked} {r.page}" for r in alle())
    assert "Musterfrau" not in gespeichert and "123" not in gespeichert


def test_erweiterungen_und_unsinn_werden_verworfen(db, anon):
    for body, art in [
        (alt(**{"blocked-uri": "moz-extension://abc/inhalt.js"}), CSP),
        (alt(**{"source-file": "chrome-extension://abc/x.js"}), CSP),
        (
            alt(**{"effective-directive": "<script>alert(1)</script>", "violated-directive": ""}),
            CSP,
        ),
        (alt(**{"blocked-uri": ""}), CSP),
        ("kein json", CSP),
        ("[" * 5000, CSP),
        ("{}", CSP),
        ("[1, 2, null]", REPORTS),
        (json.dumps({"csp-report": "x"}), CSP),
        (alt(), "text/plain"),
        ("", CSP),
        (alt(**{"blocked-uri": "https://fremd.example/" + "a" * 20000}), CSP),
    ]:
        assert anon.post(URL, body, content_type=art).status_code == 204, body[:40]
    assert alle() == []
    assert anon.get(URL).status_code == 405


def test_begrenzt_je_adresse_und_in_der_summe(db, anon, monkeypatch):
    monkeypatch.setattr(csp_reports, "PER_HOUR", 3)
    for i in range(6):
        anon.post(URL, alt(**{"blocked-uri": f"https://f{i}.example/x"}), content_type=CSP)
    assert len(alle()) == 3

    monkeypatch.setattr(csp_reports, "PER_HOUR", 1000)
    monkeypatch.setattr(csp_reports, "MAX_ROWS", 5)
    for i in range(10, 20):
        anon.post(URL, alt(**{"blocked-uri": f"https://f{i}.example/x"}), content_type=CSP)
    assert len(alle()) == 5
    # Bekannte Einträge zählen weiter, auch wenn die Liste voll ist
    anon.post(URL, alt(**{"blocked-uri": "https://f0.example/x"}), content_type=CSP)
    assert alle()[0].count == 2


def test_alarm_nur_fuer_skripte_und_hoechstens_einer_am_tag(db, anon, settings):
    settings.SECURITY_ALERTS = True
    settings.SECURITY_ALERT_EMAIL = "betrieb@example.org"
    anon.post(URL, neu(), content_type=REPORTS)
    assert mail.outbox == []
    anon.post(URL, alt(), content_type=CSP)
    assert len(mail.outbox) == 1
    text = mail.outbox[0].body
    assert "script-src-elem" in text and "https://fremd.example" in text
    assert "boese.js" not in text
    anon.post(URL, alt(**{"blocked-uri": "https://anders.example/x.js"}), content_type=CSP)
    anon.post(URL, alt(), content_type=CSP)
    assert len(mail.outbox) == 1


def test_plattform_liest_und_loescht(orgs, api, anon):
    anon.post(URL, alt(), content_type=CSP)
    anon.post(URL, neu(), content_type=REPORTS)
    mitglied = make_user("mitglied-csp@example.org")
    betrieb = make_user("betrieb-csp@example.org")
    betrieb.is_superuser = True
    betrieb.save()
    liste = "/api/platform/csp-reports/"
    assert anon.get(liste).status_code in (401, 403)
    assert api(mitglied).get(liste).status_code == 403
    state = api(betrieb).get(liste).json()
    assert state["total"] == 2 and state["limit"] == csp_reports.MAX_ROWS
    skript = next(e for e in state["entries"] if e["directive"] == "script-src-elem")
    assert skript["script"] is True and skript["count"] == 1
    assert api(mitglied).delete(f"{liste}{skript['id']}/").status_code == 403
    danach = api(betrieb).delete(f"{liste}{skript['id']}/").json()
    assert [e["directive"] for e in danach["entries"]] == ["img-src"]
    assert api(mitglied).delete(liste).status_code == 403
    assert api(betrieb).delete(liste).json()["entries"] == []
