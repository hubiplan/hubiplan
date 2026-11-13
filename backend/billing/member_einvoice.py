"""Beitragsrechnungen als E-Rechnung (XRechnung) an Mitglieder mit Leitweg-ID (Konzept J8a).

Behörden und andere öffentliche Auftraggeber, die Mitglied sind, nehmen Rechnungen oft nur
als XRechnung an. Ist das in den Beitragseinstellungen eingeschaltet, bekommt jede
Rechnung an ein Mitglied mit Leitweg-ID beim Festschreiben die fachlichen Daten der
E-Rechnung. Den Rest erledigt der vorhandene Weg der Leistungsrechnungen: XML erzeugen,
mit dem KoSIT-Prüfwerkzeug prüfen, Original ablegen, XML an die Rechnungsmail hängen.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

CENT = Decimal("0.01")
# Echte Mitgliedsbeiträge sind kein Entgelt für eine Leistung und damit nicht steuerbar
NOT_TAXABLE = "Echter Mitgliedsbeitrag, nicht steuerbar"
COUNTRIES = {
    "": "DE",
    "deutschland": "DE",
    "germany": "DE",
    "österreich": "AT",
    "austria": "AT",
    "schweiz": "CH",
    "switzerland": "CH",
    "niederlande": "NL",
    "netherlands": "NL",
    "belgien": "BE",
    "belgium": "BE",
    "luxemburg": "LU",
    "luxembourg": "LU",
    "frankreich": "FR",
    "france": "FR",
    "dänemark": "DK",
    "denmark": "DK",
    "polen": "PL",
    "poland": "PL",
}
VAT_ID = re.compile(r"^[A-Z]{2}[0-9A-Z+*.]{2,13}$")


def country_code(value: str) -> str:
    """Land als ISO-Code (DE, AT …); unbekannte Namen bleiben Deutschland."""
    text = (value or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", text):
        return text.upper()
    return COUNTRIES.get(text.lower(), "DE")


def applies(invoice, cfg) -> bool:
    """E-Rechnung für diese Rechnung? Nur Rechnungen an Mitglieder bzw. Haushalte und Firmen
    (H5) mit Leitweg-ID."""
    from .models import Invoice

    return (
        bool(cfg.einvoice_members)
        and invoice.organization.type != "unit"
        and invoice.recipient_kind in (Invoice.Recipient.MEMBER, Invoice.Recipient.HOUSEHOLD)
        and bool(invoice.leitweg_id.strip())
        and invoice.document_kind == "invoice"
        and not invoice.electronic_data
    )


def _seller(org, cfg, taxable: bool) -> dict:
    from organizations.models import Imprint
    from organizations.serializers import effective_contact

    imprint = Imprint.objects.filter(organization=org).first()
    contact = effective_contact(org)
    street = (imprint.street if imprint and imprint.street else org.street).strip()
    # Wie im Impressum: mit eigener Straße gilt auch dessen Zusatz
    own = imprint and (imprint.street or imprint.address_extra)
    address_extra = (imprint.address_extra if own else org.address_extra).strip()
    postcode = (imprint.postal_code if imprint and imprint.postal_code else org.postal_code).strip()
    city = (imprint.city if imprint and imprint.city else org.city).strip()
    email = cfg.einvoice_email or contact.get("email") or (imprint.email if imprint else "")
    phone = cfg.einvoice_phone or contact.get("phone") or (imprint.phone if imprint else "")
    name = cfg.einvoice_contact or contact.get("holder") or ""
    tax = cfg.tax_number.strip()
    vat_id = tax.replace(" ", "").upper() if VAT_ID.match(tax.replace(" ", "").upper()) else ""
    tax_number = "" if vat_id else tax
    identifier = cfg.einvoice_identifier.strip()
    if not identifier and imprint and imprint.register_number:
        identifier = " ".join(
            part for part in (imprint.register_court, imprint.register_number) if part
        )
    if not identifier:
        identifier = tax_number or cfg.creditor_id
    if not taxable:
        # Ohne steuerbare Posten (Kategorie O) verbietet EN 16931 die USt-IdNr. (BR-O-02)
        vat_id = ""
    missing = [
        label
        for label, value in (
            (gettext("Anschrift des Vereins"), street and postcode and city),
            (gettext("E-Mail für Rechnungsfragen"), email),
            (gettext("Ansprechpartner für Rechnungsfragen"), name),
            (gettext("Telefon für Rechnungsfragen"), phone),
            (gettext("Kennung des Rechnungsstellers"), vat_id or identifier),
        )
        if not value
    ]
    if missing:
        raise ValidationError(
            gettext("Für die E-Rechnung fehlen in den Beitragseinstellungen: {fields}.").format(
                fields=", ".join(missing)
            )
        )
    return {
        "name": (imprint.name if imprint and imprint.name else org.name)[:200],
        "street": street,
        "address_extra": address_extra[:200],
        "postcode": postcode,
        "city": city,
        "country": "DE",
        "email": email,
        "vat_id": vat_id,
        "tax_number": tax_number,
        "contact": name[:100],
        "phone": phone,
        "identifier": identifier[:100],
        "endpoint_id": "",
        "endpoint_scheme": "EM",
    }


def _payer_source(org, invoice):
    """Anschrift des Zahlers einer Haushalts- bzw. Firmenrechnung (H5): Mitgliedschaft oder
    eigene Angaben (Person ohne Mitgliedschaft, Geschäftspartner)."""
    from types import SimpleNamespace

    from .models import HouseholdPayer

    payer = HouseholdPayer.objects.filter(household_id=invoice.household_id).first()
    if payer is None:
        raise ValidationError(gettext("Der Haushalt hat keinen Zahler mehr."))
    if payer.membership_id is not None:
        return payer.membership, None
    if payer.partner_id is not None:
        d = payer.partner.details or {}
        return None, SimpleNamespace(
            name=payer.partner.name,
            street=d.get("street", ""),
            postal_code=d.get("postcode", ""),
            city=d.get("city", ""),
            country=d.get("country", ""),
        )
    return None, payer


def _buyer(org, invoice) -> dict:
    from members.models import BillingAddress
    from members.services import contact_for

    from .models import Invoice

    membership, own = invoice.membership, None
    if invoice.recipient_kind == Invoice.Recipient.HOUSEHOLD:
        membership, own = _payer_source(org, invoice)
    if own is not None:
        source = own
        name = own.name.strip()
    else:
        person = membership.person
        billing = BillingAddress.objects.filter(membership=membership).first()
        source = (
            billing if billing is not None and billing.has_address else contact_for(person, org)
        )
        name = (
            billing.name.strip() if billing is not None and billing.has_address else ""
        ) or person.address_name
    street = (getattr(source, "street", "") or "").strip()
    postcode = (getattr(source, "postal_code", "") or "").strip()
    city = (getattr(source, "city", "") or "").strip()
    if not (street and postcode and city):
        raise ValidationError(
            gettext("Für die E-Rechnung an {name} fehlt die vollständige Anschrift.").format(
                name=name
            )
        )
    return {
        "name": name[:200],
        "street": street,
        "postcode": postcode,
        "city": city,
        "country": country_code(getattr(source, "country", "")),
        "email": invoice.recipient_email,
        "vat_id": "",
        "tax_number": "",
        "contact": "",
        "phone": "",
        "identifier": "",
        # Öffentliche Auftraggeber erreicht man über die Leitweg-ID (Schema 0204)
        "endpoint_id": invoice.leitweg_id.strip(),
        "endpoint_scheme": "0204",
    }


def _line(line) -> dict:
    gross = Decimal(line.amount)
    rate = Decimal(line.vat_rate or 0)
    if rate:
        net = gross - (gross * rate / (Decimal(100) + rate)).quantize(CENT, ROUND_HALF_UP)
        category, reason = "S", ""
    else:
        net, category, reason = gross, "O", NOT_TAXABLE
    return {
        "text": " – ".join(part for part in (line.text, line.detail) if part)[:200]
        or gettext("Mitgliedsbeitrag"),
        # Gutschriften als negative Menge; Preise bleiben positiv (EN 16931 BR-27)
        "quantity": Decimal(-1 if net < 0 else 1),
        "unit": "C62",
        "unit_price": abs(net),
        "allowance": Decimal(0),
        "charge": Decimal(0),
        "adjustment_reason": "",
        "tax_category": category,
        "tax_rate": rate,
        "tax_reason": reason,
    }


def prepare(invoice, cfg) -> None:
    """Fachliche Daten der E-Rechnung an die Rechnung und ihre Posten schreiben."""
    from .einvoice_services import json_data
    from .einvoice_xml import calculate
    from .sepa import iban_valid

    org = invoice.organization
    lines = list(invoice.lines.all().order_by("position", "pk"))
    data = [_line(line) for line in lines]
    taxable = any(row["tax_category"] == "S" for row in data)
    if taxable:
        # Nicht steuerbare Posten neben steuerpflichtigen: steuerfrei mit Grund (BR-O-11)
        for row in data:
            if row["tax_category"] == "O":
                row["tax_category"], row["tax_reason"] = "E", NOT_TAXABLE
    iban = (cfg.account.iban if cfg.account_id else "").replace(" ", "").upper()
    if not iban or not iban_valid(iban):
        raise ValidationError(
            gettext("Für die E-Rechnung fehlt ein Konto mit IBAN in den Beitragseinstellungen.")
        )
    seller = _seller(org, cfg, taxable)
    if taxable and not (seller["vat_id"] or seller["tax_number"]):
        raise ValidationError(
            gettext(
                "Für steuerpflichtige Posten braucht die E-Rechnung Steuernummer oder USt-IdNr."
            )
        )
    totals = calculate(data)
    start, end = (
        (invoice.run.start_date, invoice.run.end_date)
        if invoice.run_id
        else (invoice.date, invoice.date)
    )
    invoice.electronic_data = json_data(
        {
            "seller": seller,
            "buyer": _buyer(org, invoice),
            "buyer_reference": invoice.leitweg_id.strip(),
            "order_reference": invoice.order_reference.strip(),
            "service_start": start,
            "service_end": end,
            "iban": iban,
            "currency": "EUR",
            "source": "membership",
        }
    )
    for line, row in zip(lines, totals["lines"], strict=True):
        line.electronic_data = json_data(row)
        line.amount = row["gross"]
        line.save(update_fields=["electronic_data", "amount"])
    # Steuer je Satz gerundet: der Betrag der E-Rechnung gilt (selten ein Cent Unterschied)
    invoice.total = totals["gross"]
    invoice.save(update_fields=["electronic_data", "total", "updated_at"])
