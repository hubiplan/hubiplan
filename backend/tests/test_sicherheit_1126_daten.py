"""Sicherheitsprüfung 26.11.2026, Paket 3: Verschlüsselung, Postausgang, Protokoll (erfunden)."""

from __future__ import annotations

import datetime

import pytest
from django.db import IntegrityError, connection, transaction

from audit.chain import seal
from audit.log import record
from audit.models import AuditEntry
from billing.models import DebitRun
from core.encfields import EncryptedTextField
from core.tenancy import rls_bypass, tenant_context
from members.models import MemberType, TransferRequest
from outbox import mail
from outbox.backend import redact, redact_reply_to
from outbox.models import OutgoingMail
from portal.models import ChangeRequest

from .factories import make_member

pytestmark = pytest.mark.django_db


def _raw(table: str, column: str, pk: int) -> str:
    with rls_bypass(), connection.cursor() as cur:
        cur.execute(f'SELECT "{column}"::text FROM "{table}" WHERE id = %s', [pk])  # noqa: S608
        return cur.fetchone()[0]


# --- B-M01: Änderungsmeldungen und Wechselanfragen liegen verschlüsselt in der Datenbank ---


def test_aenderungsmeldung_verschluesselt_gespeichert(orgs):
    club = orgs["a"]
    membership = make_member(club, "Greta", "Beispiel")
    with tenant_context(club.pk):
        cr = ChangeRequest.objects.create(
            organization=club,
            membership=membership,
            data={"street": "Neue Gasse 7"},
            previous={"street": "Lindenweg 4"},
        )
    for column in ("data", "previous"):
        stored = _raw("portal_changerequest", column, cr.pk)
        assert "enc1" in stored and "Gasse" not in stored and "Lindenweg" not in stored
    with tenant_context(club.pk):
        again = ChangeRequest.objects.get(pk=cr.pk)
        assert again.data == {"street": "Neue Gasse 7"}
        assert again.previous == {"street": "Lindenweg 4"}
        # Löschfristen leeren weiter ohne Umweg
        ChangeRequest.objects.filter(pk=cr.pk).update(data={}, previous={})
        assert ChangeRequest.objects.get(pk=cr.pk).data == {}


def test_wechselanfrage_verschluesselt_und_fuer_beide_vereine_lesbar(orgs):
    alt, neu = orgs["a"], orgs["b"]
    membership = make_member(alt, "Jonas", "Muster")
    with rls_bypass():
        art, _ = MemberType.objects.get_or_create(
            organization=neu, name="aktiv", defaults={"active": True}
        )
        tr = TransferRequest.objects.create(
            scope=neu.federation or neu,
            person=membership.person,
            from_org=alt,
            to_org=neu,
            member_type=art,
            member_type_name=art.name,
            entry_date=datetime.date(2026, 12, 1),
            admission={"email": "jonas@example.org", "club_number": "4711"},
        )
    stored = _raw("members_transferrequest", "admission", tr.pk)
    assert "enc1" in stored and "jonas@example.org" not in stored
    for org in (alt, neu):
        with tenant_context(org.pk):
            assert TransferRequest.objects.get(pk=tr.pk).admission["club_number"] == "4711"


# --- B-H03: die SEPA-Datei eines Lastschriftlaufs liegt nicht im Klartext ---


def test_sepa_datei_des_laufs_ist_verschluesseltes_feld():
    assert isinstance(DebitRun._meta.get_field("xml"), EncryptedTextField)


# --- B-H06: Postausgang speichert keine persönlichen Links und Antwortkennungen ---


@pytest.mark.parametrize(
    "pfad",
    [
        "umfrage",
        "rueckmeldung",
        "anmeldung/bestaetigen",
        "meine-anmeldung",
        "antrag",
        "nachweis",
        "auslage",
        "bilder-hochladen",
        "kartenscan",
        "mitglied-werden/stand",
    ],
)
def test_persoenliche_links_stehen_nicht_im_postausgang(pfad):
    text = redact(f"Hallo,\nhier entlang: https://verein.example.org/{pfad}/GEHEIM123 \nGruß")
    assert "GEHEIM123" not in text
    assert f"https://verein.example.org/{pfad}/" in text and "Gruß" in text


def test_oeffentliche_links_bleiben_im_postausgang():
    text = "Anmeldung: https://verein.example.org/anmeldung/sommerfest und /termine/12"
    assert redact(text) == text


def test_antwortkennung_wird_nicht_gespeichert():
    assert (
        redact_reply_to(["termin+12-34-abcdef@verein.example.org"], "termin")
        == "termin@verein.example.org"
    )
    # Kontaktformular: die Adresse der Absenderin bleibt, wie sie ist
    assert (
        redact_reply_to(["erika+verein@example.org"], "website-contact")
        == "erika+verein@example.org"
    )


def test_erinnerung_anonyme_umfrage_ohne_empfaenger_im_postausgang(orgs, settings):
    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"
    club = orgs["a"]
    mail.send(
        "saeumig@example.org",
        "Erinnerung: Umfrage Sommerfest",
        "Hallo Karla, bitte noch abstimmen.",
        organization=club,
        kind="umfrage_anonym",
    )
    with rls_bypass():
        row = OutgoingMail.objects.get(subject="Erinnerung: Umfrage Sommerfest")
    assert "saeumig" not in row.to and "Karla" not in row.body


# --- Protokoll: alle Felder der Prüfsumme sind in der Datenbank geschützt ---


def _blocked(fn) -> bool:
    try:
        with transaction.atomic():
            fn()
    except IntegrityError:
        return True
    return False


def test_versiegelter_eintrag_schuetzt_person_und_konto(orgs, board_a):
    club = orgs["a"]
    with tenant_context(club.pk):
        record(club, board_a, "update", club, {"Name": ["A", "B"]})
    seal(club.pk)
    with rls_bypass():
        qs = AuditEntry.objects.filter(organization=club).order_by("-pk")[:1]
        qs = AuditEntry.objects.filter(pk=qs.get().pk)
        assert qs.get().hash
        assert _blocked(lambda: qs.update(user_email="andere@example.org"))
        assert _blocked(lambda: qs.update(via="app"))
        assert _blocked(lambda: qs.update(person_id=987654))
        # Löschfristen leeren weiter Inhalt und Bezeichnung
        qs.update(changes={}, object_repr="anonymisiert", cleared=True)
        assert qs.get().cleared
