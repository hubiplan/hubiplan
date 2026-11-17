"""Rechnungspostfach: Kennungen mit „nw“ am Anfang (Gesamtaudit 15.11., AZ-04).

``rechnung+nw…`` ist auch die Antwortadresse für Beitragsnachweise (feeproofs/mail.py). Ein
Verein, dessen zufällige Kennung mit „nw“ begann, bekam seine E-Rechnungen deshalb nie in den
Rechnungseingang: Die Mails blieben als „unbekannte Nachweis-Adresse“ im Postfach liegen.
"""
# ruff: noqa: F811

import datetime
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from billing import incoming_mail
from billing.incoming_mail import Result
from billing.models import IncomingMail
from core.tenancy import rls_bypass, tenant_context
from feeproofs import mail as proof_mail
from feeproofs import notify
from feeproofs.models import FeeProof, ProofDiscount

from .test_beitragsnachweise import JAHR, anna_portal, bescheinigung, rabatt, stichtag  # noqa: F401
from .test_m9_billing import c, club, setup  # noqa: F401
from .test_rechnungspostfach import (  # noqa: F401
    address,
    checks,
    invoices,
    mail,
    mails,
    postfach,
    xml_part,
)

pytestmark = pytest.mark.django_db

ALTE_KENNUNG = "nwk7m2q9ab"


def nw_kennung(club) -> str:
    """Kennung wie vor der Behebung: zufällig mit „nw“ am Anfang."""
    with tenant_context(club.pk):
        box = incoming_mail.mailbox_of(club)
        box.tag = ALTE_KENNUNG
        box.save(update_fields=["tag"])
    return address(club)


def test_alte_nw_kennung_nimmt_e_rechnung_an(club):
    to = nw_kennung(club)
    assert to == f"rechnung+{ALTE_KENNUNG}@example.org"
    raw = mail(to, [xml_part()])
    msg = EmailMessage()
    msg["To"] = to
    # Kein Nachweis: Der Weg der Beitragsnachweise lässt die Mail durch
    assert proof_mail.process(msg, [to]) is None
    assert incoming_mail.process_message(raw) == Result.MOVE
    [item] = invoices(club)
    assert item.data["payable"] == "119.00"
    [entry] = mails(club)
    assert entry.status == IncomingMail.Status.IMPORTED


def test_alte_nw_kennung_ohne_e_rechnung_wird_hinweis(club):
    raw = mail(nw_kennung(club))
    assert incoming_mail.process_message(raw) == Result.KEEP
    [entry] = mails(club)
    assert entry.status == IncomingMail.Status.NO_INVOICE


def test_nachweis_antwort_bleibt_beim_nachweis(club, rabatt, anna_portal):
    nw_kennung(club)  # auch neben einem Verein mit „nw“-Kennung
    anna = anna_portal["anna"]
    with tenant_context(club.pk):
        discount = ProofDiscount.objects.get(pk=rabatt["id"])
        link, _ = notify.new_link(anna, discount, JAHR, datetime.date(2099, 1, 1))
    reply = notify.reply_address(link.mail_key)
    assert reply.startswith("rechnung+nw")
    msg = EmailMessage()
    msg["From"] = "anna@example.org"
    msg["To"] = reply
    msg["Subject"] = "Re: Nachweis"
    msg["Message-ID"] = "<nw1@example.org>"
    msg.set_content("Anbei")
    msg.add_attachment(bescheinigung(), maintype="application", subtype="pdf", filename="b.pdf")
    assert incoming_mail.process_message(msg.as_bytes()) == Result.MOVE
    with rls_bypass():
        assert FeeProof.objects.filter(membership=anna, channel="mail").count() == 1
    assert mails(club) == []  # nicht im Rechnungseingang
    # Unbekannte Nachweis-Adresse ohne Verein: bleibt wie bisher liegen
    msg.replace_header("To", "rechnung+nwunbekannt99@example.org")
    assert incoming_mail.process_message(msg.as_bytes()) == Result.KEEP
    assert mails(club) == []


def test_neue_kennung_beginnt_nie_mit_nw(monkeypatch):
    zeichen = iter("nw" + "a" * 8 + "bcdefghjkm")
    monkeypatch.setattr(
        incoming_mail, "secrets", SimpleNamespace(choice=lambda alphabet: next(zeichen))
    )
    assert incoming_mail._new_tag() == "bcdefghjkm"


def test_kennungen_im_alphabet_ohne_nw():
    for _ in range(200):
        tag = incoming_mail._new_tag()
        assert len(tag) == incoming_mail.TAG_LENGTH and not tag.startswith("nw")
