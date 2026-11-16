# ruff: noqa: F811  (Fixtures aus test_mitgliedsantrag als Parameter)
"""Auskunft nach Art. 15 DSGVO: kein Bestand mit Bezug zur Person fehlt (Gesamtaudit 13.11. K-02).

Jedes Modell mit Verweis auf Person oder Mitgliedschaft steht in ``members/auskunft.py``, kommt
über die Akte hinein oder steht hier mit Begründung. Ein neues Modul fällt damit auf.
"""

import inspect
import io
import json
import zipfile

import pytest
from django.apps import apps
from django.db import models

from members import auskunft
from members.models import Membership, Person

from .test_gesamtaudit_1311 import _angenommen
from .test_mitgliedsantrag import club, leichte_aufgabe  # noqa: F401  (Fixtures)

# Über die Akte (members.serializers.member_detail) in akte.json
IN_DER_AKTE = {
    "members.MembershipPeriod": "Mitgliedschaftszeiten",
    "members.MemberTypeAssignment": "Mitgliedsarten",
    "members.DepartmentMembership": "Untereinheiten",
    "members.DepartmentRoleHolder": "Ämter in Untereinheiten",
    "members.ContactPerson": "Ansprechpartner",
    "members.BillingAddress": "Rechnungsanschrift",
    "members.HouseholdMember": "Haushalte und Firmen",
    "members.HonoraryTitleAward": "Ehrentitel",
    "members.FederationMember": "Verbandsmeldung",
    "members.MemberPhoto": "Foto (foto.*)",
    "access.RoleAssignment": "Ämter",
}

AUSNAHMEN = {
    "billing.InvoiceLine": "steht als Posten bei den Rechnungen (rechnungen.json)",
    "finance.BankLine": "nur Zuordnungsvorschlag einer Bankzeile; die Zahlung steht bei den "
    "Rechnungen, die Zeile kann Angaben anderer enthalten",
}


def _modelle():
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if isinstance(field, models.ForeignKey) and field.related_model in (Membership, Person):
                yield model._meta.label, model.__name__
                break


def test_jeder_bestand_zur_person_ist_in_der_auskunft():
    source = inspect.getsource(auskunft)
    fehlend = [
        label
        for label, name in _modelle()
        if name not in source and label not in IN_DER_AKTE and label not in AUSNAHMEN
    ]
    assert fehlend == []


def test_ausnahmelisten_sind_aktuell():
    labels = {label for label, _ in _modelle()}
    assert set(IN_DER_AKTE) | set(AUSNAHMEN) <= labels


# Gesamtaudit 15.11., PF-02/PF-20/PF-23: Auch was am Anmeldekonto hängt, gehört in die
# Auskunft (konto.json). Erfasst sind Modelle, die mit dem Konto gelöscht werden (CASCADE,
# auch aus allauth). Verweise mit SET_NULL nennen nur, wer etwas angelegt oder bearbeitet
# hat; sie sind Angaben zu einem Vorgang des Vereins, nicht Daten des Kontos.
KONTO_AUSNAHMEN = {
    "access.RoleAssignment": "Ämter, in der Akte",
    "members.DepartmentRoleHolder": "Ämter in Untereinheiten, in der Akte",
    "changes.RequestKey": "Schlüssel gegen doppelte Absendung, technische Kennung ohne Inhalt",
    "devices.PairingCode": "Kopplungscode der App, nur wenige Minuten gültig, nur Prüfsumme",
    "peering.LoginLink": "Anmeldelink über eine andere Instanz, kurzlebig, nur Prüfsumme",
    "portal.LoginLink": "Anmeldelink, nur Prüfsumme; nach 30 Tagen gelöscht",
    "todos.TodoShare": "Freigaben einer Aufgabe; in konto.json als „mit dir geteilt“",
    "website.ImageUploadLink": "Hochladelink für Bilder der Webseite, kurzlebig, ohne Inhalt",
    "admin.LogEntry": "Protokoll des Django-Admins (standardmäßig aus) über Plattformverwalter",
}


def _konto_modelle():
    from django.contrib.auth import get_user_model

    user = get_user_model()
    for model in apps.get_models():
        if model is user:
            continue
        for field in model._meta.concrete_fields:
            if (
                isinstance(field, models.ForeignKey)
                and field.related_model is user
                and field.remote_field.on_delete is models.CASCADE
            ):
                yield model._meta.label, model.__name__
                break


def test_jeder_bestand_zum_konto_ist_in_der_auskunft():
    source = inspect.getsource(auskunft)
    fehlend = [
        label
        for label, name in _konto_modelle()
        if name not in source and label not in KONTO_AUSNAHMEN
    ]
    assert fehlend == []


def test_konto_ausnahmen_sind_aktuell():
    labels = {label for label, _ in _konto_modelle()}
    assert set(KONTO_AUSNAHMEN) <= labels


def _zip(content: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


NEU = (
    "antrag.json",
    "aenderungswuensche.json",
    "kuendigungen.json",
    "einwilligungen.json",
    "ausweise.json",
    "fotolinks.json",
    "kasse.json",
    "zahler.json",
    "geschaeftspartner.json",
    "rundschreiben.json",
    "wettbewerbe.json",
    "meldungen.json",
    "wuerden.json",
    "musik.json",
    "material.json",
    "wechsel.json",
)


@pytest.mark.django_db(transaction=True)
def test_auskunft_enthaelt_online_antrag(club):
    app, _, _ = _angenommen(club)
    res = club["client"].get(f"/api/orgs/{club['org'].pk}/members/{app.membership_id}/auskunft/")
    assert res.status_code == 200, res.content
    files = _zip(b"".join(res.streaming_content) if res.streaming else res.content)
    for name in NEU:
        json.loads(files[name])
    [antrag] = json.loads(files["antrag.json"])
    assert antrag["nummer"] == app.number
    assert antrag["angaben"]["last_name"] == "Muster"
    assert antrag["einwilligungen"]
    assert files[f"antrag-{app.number}.pdf"].startswith(b"%PDF")
    # keine Namen der Entscheidenden
    assert "user_name" not in files["antrag.json"].decode()
