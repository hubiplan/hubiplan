"""Geschäftspartner im E-Rechnungseingang (Konzept geschaeftspartner.md, P3).

HUBIplan schlägt zu einem Eingang einen Partner vor: über USt-IdNr., IBAN, die
Absenderadresse des Rechnungspostfachs (Adresse, dann Domain) und zuletzt den Namen.
Zugeordnet wird nur von Hand. Weicht die IBAN der Rechnung von der gespeicherten ab,
verlangt die Freigabe eine Bestätigung.

Name, Steuer- und Bankangaben sind verschlüsselt; der Abgleich läuft daher im Speicher.
"""

from __future__ import annotations

import re

from .models import BusinessPartner

# Domains von Mailanbietern sagen nichts über den Absender
FREEMAIL = {
    "aol.com",
    "freenet.de",
    "gmail.com",
    "gmx.de",
    "gmx.net",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "mailbox.org",
    "outlook.com",
    "outlook.de",
    "posteo.de",
    "t-online.de",
    "web.de",
    "yahoo.com",
    "yahoo.de",
}


def norm_iban(value) -> str:
    return re.sub(r"\s", "", str(value or "")).upper()


def norm_vat(value) -> str:
    return re.sub(r"[\s.\-/]", "", str(value or "")).upper()


def norm_mail(value) -> str:
    return str(value or "").strip().lower()


def domain(address: str) -> str:
    _, _, host = norm_mail(address).rpartition("@")
    return host


def partner_iban(partner: BusinessPartner | None) -> str:
    return norm_iban((partner.bank or {}).get("iban")) if partner else ""


class PartnerIndex:
    """Aktive Partner eines Vereins, nach Merkmalen aufgeschlüsselt (einmal je Anfrage)."""

    def __init__(self, org):
        self.by_vat: dict[str, BusinessPartner] = {}
        self.by_iban: dict[str, BusinessPartner] = {}
        self.by_mail: dict[str, BusinessPartner] = {}
        self.by_domain: dict[str, BusinessPartner] = {}
        self.by_name: dict[str, BusinessPartner] = {}
        rows = BusinessPartner.objects.filter(organization=org, is_active=True)
        for partner in sorted(rows.prefetch_related("contacts"), key=lambda p: p.pk):
            details = partner.details or {}
            if vat := norm_vat(details.get("vat_id")):
                self.by_vat.setdefault(vat, partner)
            if iban := partner_iban(partner):
                self.by_iban.setdefault(iban, partner)
            mails = [details.get("email"), *(c.email for c in partner.contacts.all())]
            for mail in filter(None, map(norm_mail, mails)):
                self.by_mail.setdefault(mail, partner)
                if (host := domain(mail)) and host not in FREEMAIL:
                    self.by_domain.setdefault(host, partner)
            if name := (partner.name or "").strip().casefold():
                self.by_name.setdefault(name, partner)

    def known_sender(self, sender: str) -> bool:
        return bool(sender) and norm_mail(sender) in self.by_mail

    def suggest(self, data: dict, sender: str = "") -> tuple[BusinessPartner | None, str]:
        """Vorschlag für einen Eingang und woran er erkannt wurde."""
        data = data or {}
        if (vat := norm_vat(data.get("seller_vat_id"))) and vat in self.by_vat:
            return self.by_vat[vat], "vat_id"
        if (iban := norm_iban(data.get("iban"))) and iban in self.by_iban:
            return self.by_iban[iban], "iban"
        if sender:
            if (mail := norm_mail(sender)) in self.by_mail:
                return self.by_mail[mail], "sender"
            if (host := domain(sender)) and host in self.by_domain:
                return self.by_domain[host], "domain"
        if (name := str(data.get("seller") or "").strip().casefold()) and name in self.by_name:
            return self.by_name[name], "name"
        return None, ""


def known_sender(org, sender: str) -> bool:
    """Absender gehört zu einem aktiven Partner (E-Mail des Partners oder Ansprechpartner)."""
    return bool(sender) and PartnerIndex(org).known_sender(sender)


def iban_changed(partner: BusinessPartner | None, data: dict) -> bool:
    """Die Rechnung nennt eine andere IBAN als beim Partner gespeichert."""
    stored = partner_iban(partner)
    given = norm_iban((data or {}).get("iban"))
    return bool(stored and given and stored != given)
