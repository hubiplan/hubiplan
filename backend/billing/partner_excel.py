"""Excel-Export und -Import der Geschäftspartner mit allen Feldern und Ansprechpartnern.

Blatt 1 enthält die Partner, Blatt 2 („Ansprechpartner“) ihre Ansprechpartner. Der Import
liest dieselbe Datei wieder ein: Eine bekannte Nummer aktualisiert den Partner (nur gefüllte
Zellen überschreiben), eine Zeile ohne Nummer mit schon bekanntem Namen wird übersprungen,
alles andere wird neu angelegt. Ansprechpartner werden über Partnernummer, Name und Vorname
zugeordnet. Bankangaben, Zahlungsziel, Standardkategorie und Künstlerkennzeichen gehen nur
mit Kassen- oder Beitragsrechten hinaus und herein (GP-3).
"""

from __future__ import annotations

import datetime as dt
import io

from django.db import transaction
from django.utils.translation import gettext
from rest_framework import serializers

from audit.log import diff, record, snapshot

from .models import BusinessPartner, PartnerContact

MAX_ROWS = 2000

# Schlüssel, deutsche Spaltenüberschrift (msgid), englische Überschrift. Die englische
# Überschrift steht hier noch einmal, damit eine Datei unabhängig von der Sprache passt.
PARTNER_COLUMNS = [
    ("number", "Nummer", "Number"),
    ("name", "Name", "Name"),
    ("kind", "Art", "Type"),
    ("roles", "Rollen", "Roles"),
    ("street", "Straße", "Street"),
    ("postcode", "PLZ", "Postcode"),
    ("city", "Ort", "City"),
    ("country", "Land", "Country"),
    ("email", "E-Mail", "Email"),
    ("phone", "Telefon", "Phone"),
    ("website", "Webseite", "Website"),
    ("vat_id", "USt-IdNr.", "VAT ID"),
    ("tax_number", "Steuernummer", "Tax number"),
    ("leitweg_id", "Leitweg-ID", "Leitweg ID"),
    ("our_customer_number", "Unsere Kundennummer", "Our customer number"),
    ("contact", "Ansprechpartner", "Contact person"),
    ("first_contact_on", "Erstkontakt am", "First contact on"),
    ("first_contact_note", "Erstkontakt", "First contact"),
    ("liaison", "Betreut von", "Looked after by"),
    ("liaison_number", "Betreut von (Mitgliedsnummer)", "Looked after by (member number)"),
    ("membership", "Mitglied", "Member"),
    ("membership_number", "Mitglied (Mitgliedsnummer)", "Member (member number)"),
    ("notes", "Notizen", "Notes"),
    ("website_consent", "Auf der Webseite nennen", "Show on website"),
    ("website_url", "Link für die Webseite", "Link for the website"),
    ("is_active", "Aktiv", "Active"),
]
MONEY_COLUMNS = [
    ("iban", "IBAN", "IBAN"),
    ("bic", "BIC", "BIC"),
    ("holder", "Kontoinhaber", "Account holder"),
    ("payment_terms_days", "Zahlungsziel (Tage)", "Payment terms (days)"),
    ("default_category", "Standardkategorie", "Default category"),
    ("artist", "Künstlersozialabgabe", "Artists' social security levy"),
]
CONTACT_COLUMNS = [
    ("partner_number", "Partnernummer", "Partner number"),
    ("partner", "Geschäftspartner", "Business partner"),
    ("last_name", "Name", "Name"),
    ("first_name", "Vorname", "First name"),
    ("function", "Funktion", "Function"),
    ("email", "E-Mail", "Email"),
    ("phone", "Telefon", "Phone"),
    ("is_primary", "Hauptansprechpartner", "Main contact"),
    ("receives_invoices", "erhält Rechnungen", "receives invoices"),
    ("receives_mail", "erhält Post", "receives mail"),
    ("notes", "Notiz", "Note"),
]
DATE_COLUMN = [k for k, _, _ in PARTNER_COLUMNS].index("first_contact_on") + 1
DETAIL_KEYS = (
    "name",
    "street",
    "postcode",
    "city",
    "country",
    "email",
    "phone",
    "website",
    "vat_id",
    "tax_number",
    "leitweg_id",
    "contact",
)
YES = {"ja", "yes", "x", "1", "true", "wahr"}
NO = {"nein", "no", "0", "false", "falsch", "-"}


def _yes_no(value: bool) -> str:
    return gettext("Ja") if value else gettext("Nein")


def _member_label(membership) -> str:
    if not membership:
        return ""
    person = membership.person
    return " ".join(p for p in (person.first_name, person.last_name) if p)


def _primary(partner):
    contacts = list(partner.contacts.all())
    return next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)


def contact_label(contact) -> str:
    if not contact:
        return ""
    return " ".join(p for p in (contact.first_name, contact.last_name) if p)


def scalar_fields(org) -> list:
    """Zusatzfelder, die in eine Excel-Spalte passen (ohne wiederholbare)."""
    from .models import PartnerField

    return list(PartnerField.objects.filter(organization=org, is_archived=False, repeatable=False))


class _RowError(Exception):
    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


def export_workbook(org, partners, money: bool) -> bytes:
    from openpyxl import Workbook

    roles = dict(BusinessPartner.Role.choices)
    kinds = dict(BusinessPartner.Kind.choices)
    columns = PARTNER_COLUMNS + (MONEY_COLUMNS if money else [])
    fields = scalar_fields(org)
    book = Workbook()
    sheet = book.active
    sheet.title = gettext("Geschäftspartner")
    sheet.append([gettext(de) for _, de, _ in columns] + [f.label for f in fields])
    contacts = book.create_sheet(gettext("Ansprechpartner"))
    contacts.append([gettext(de) for _, de, _ in CONTACT_COLUMNS])
    for p in partners:
        d = p.details or {}
        b = p.bank or {}
        values = {
            **{k: d.get(k, "") for k in DETAIL_KEYS},
            "number": p.number,
            "name": p.name,
            "kind": str(kinds.get(p.kind, p.kind)),
            "roles": ", ".join(str(roles.get(r, r)) for r in p.roles or []),
            "our_customer_number": p.our_customer_number,
            "contact": contact_label(_primary(p)) or d.get("contact", ""),
            "first_contact_on": p.first_contact_on,
            "first_contact_note": p.first_contact_note,
            "liaison": _member_label(p.liaison),
            "liaison_number": p.liaison.club_number if p.liaison_id else "",
            "membership": _member_label(p.membership),
            "membership_number": p.membership.club_number if p.membership_id else "",
            "notes": p.notes,
            "website_consent": _yes_no(p.website_consent),
            "website_url": p.website_url,
            "is_active": _yes_no(p.is_active),
            "iban": b.get("iban", ""),
            "bic": b.get("bic", ""),
            "holder": b.get("holder", ""),
            "payment_terms_days": p.payment_terms_days,
            "default_category": p.default_category.name if p.default_category_id else "",
            "artist": _yes_no(p.artist),
        }
        row = [values[key] for key, _, _ in columns]
        extra = {v.definition_id: v.value for v in p.field_values.all()}
        for field in fields:
            value = extra.get(field.pk)
            if field.field_type == "bool" and value is not None:
                value = _yes_no(value)
            row.append(value)
        sheet.append(row)
        if values["first_contact_on"]:
            sheet.cell(sheet.max_row, DATE_COLUMN).number_format = "DD.MM.YYYY"
        for c in p.contacts.all():
            contacts.append(
                [
                    p.number,
                    p.name,
                    c.last_name,
                    c.first_name,
                    c.function,
                    c.email,
                    c.phone,
                    _yes_no(c.is_primary),
                    _yes_no(c.receives_invoices),
                    _yes_no(c.receives_mail),
                    c.notes,
                ]
            )
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _header(row, columns) -> list[str]:
    names = {}
    for key, de, en in columns:
        for label in (de, en, gettext(de)):
            names.setdefault(label.casefold(), key)
    # ältere Exporte und Kurzformen
    names.setdefault("number", "number")
    names.setdefault("vat id", "vat_id")
    names.setdefault("contact", "contact")
    names.setdefault("type", "kind")
    return [names.get(str(h or "").strip().casefold(), "") for h in row]


def _cells(header, raw) -> dict:
    values = {}
    for key, value in zip(header, raw, strict=False):
        if not key or value is None:
            continue
        if isinstance(value, dt.datetime):
            value = value.date()
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, dt.date):
            value = str(value).strip()
            if not value:
                continue
        values[key] = value
    return values


def _flag(value, label: str):
    text = str(value).strip().casefold()
    if text in YES:
        return True
    if text in NO:
        return False
    raise serializers.ValidationError({label: gettext("Bitte „Ja“ oder „Nein“.")})


def _date(value, label: str):
    if isinstance(value, dt.date):
        return value.isoformat()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return dt.datetime.strptime(str(value), fmt).date().isoformat()
        except ValueError:
            continue
    raise serializers.ValidationError({label: gettext("Bitte ein Datum wie 31.12.2026.")})


def _messages(detail) -> str:
    if isinstance(detail, dict):
        parts = []
        for key, value in detail.items():
            text = _messages(value)
            parts.append(text if key in ("non_field_errors", "details") else f"{key}: {text}")
        return "; ".join(parts)
    if isinstance(detail, list):
        return " ".join(_messages(v) for v in detail)
    return str(detail)


class _Members:
    """Mitgliedschaften des Vereins nach Mitgliedsnummer und Namen (einmal je Import)."""

    def __init__(self, org):
        from members.models import Membership

        self.by_number: dict[str, int] = {}
        self.by_name: dict[str, list[int]] = {}
        for m in Membership.objects.filter(organization=org).select_related("person"):
            if m.club_number:
                self.by_number.setdefault(m.club_number.strip().casefold(), m.pk)
            self.by_name.setdefault(_member_label(m).casefold(), []).append(m.pk)

    def find(self, number, name, label: str) -> int:
        if number:
            if (found := self.by_number.get(str(number).strip().casefold())) is None:
                raise serializers.ValidationError(
                    {label: gettext("Mitgliedsnummer {number} unbekannt.").format(number=number)}
                )
            return found
        matches = self.by_name.get(str(name).strip().casefold(), [])
        if len(matches) != 1:
            raise serializers.ValidationError(
                {
                    label: gettext(
                        "„{name}“ ist kein eindeutiges Mitglied; bitte die Mitgliedsnummer angeben."
                    ).format(name=name)
                }
            )
        return matches[0]


class PartnerImport:
    def __init__(self, view, money_edit: bool):
        self.view = view
        self.org = view.org
        self.money_edit = money_edit
        self.created = self.updated = self.skipped = 0
        self.contacts_created = self.contacts_updated = 0
        self.errors: list[str] = []
        self._members: _Members | None = None
        self.fields: dict = {}
        self.by_number = {
            p.number.casefold(): p
            for p in BusinessPartner.objects.filter(organization=self.org).exclude(number="")
        }
        self.names = {
            p.name.casefold() for p in BusinessPartner.objects.filter(organization=self.org)
        }

    @property
    def members(self) -> _Members:
        if self._members is None:
            self._members = _Members(self.org)
        return self._members

    def error(self, sheet: str, index: int, detail) -> None:
        self.errors.append(
            gettext("{sheet}, Zeile {index}: {error}").format(
                sheet=sheet, index=index, error=_messages(detail)
            )
        )

    # Partner

    def payload(self, values: dict, partner) -> dict:
        kinds = {str(label).casefold(): v for v, label in BusinessPartner.Kind.choices}
        kinds.update({v: v for v in BusinessPartner.Kind.values})
        roles = {str(label).casefold(): v for v, label in BusinessPartner.Role.choices}
        roles.update({v: v for v in BusinessPartner.Role.values})
        data: dict = {}
        details = {k: str(values[k]) for k in DETAIL_KEYS if k in values}
        if details:
            data["details"] = details
        if "kind" in values:
            kind = kinds.get(str(values["kind"]).casefold())
            if kind is None:
                message = gettext("Unbekannte Art „{value}“.").format(value=values["kind"])
                raise serializers.ValidationError({gettext("Art"): message})
            data["kind"] = kind
        if "roles" in values:
            data["roles"] = sorted(
                {
                    roles[r.strip().casefold()]
                    for r in str(values["roles"]).split(",")
                    if r.strip().casefold() in roles
                }
            )
        for key in ("our_customer_number", "first_contact_note", "notes", "website_url"):
            if key in values:
                data[key] = str(values[key])
        if "first_contact_on" in values:
            data["first_contact_on"] = _date(values["first_contact_on"], gettext("Erstkontakt am"))
        for key, label in (("website_consent", "Auf der Webseite nennen"), ("is_active", "Aktiv")):
            if key in values:
                data[key] = _flag(values[key], gettext(label))
        for key, label in (("liaison", "Betreut von"), ("membership", "Mitglied")):
            number, name = values.get(f"{key}_number"), values.get(key)
            if number or name:
                data[key] = self.members.find(number, name, gettext(label))
        if self.money_edit:
            bank = {k: str(values[k]) for k in ("iban", "bic", "holder") if k in values}
            if bank:
                before = (partner.bank if partner else {}) or {}
                data["bank"] = {
                    "iban": before.get("iban", ""),
                    "bic": before.get("bic", ""),
                    "holder": before.get("holder", ""),
                    **bank,
                }
            if "payment_terms_days" in values:
                data["payment_terms_days"] = values["payment_terms_days"]
            if "artist" in values:
                data["artist"] = _flag(values["artist"], gettext("Künstlersozialabgabe"))
            if "default_category" in values:
                data["default_category"] = self.category(values["default_category"])
        return data

    def category(self, name) -> int:
        from finance.models import Category

        wanted = str(name).strip().casefold()
        for category in Category.objects.filter(organization=self.org):
            if category.name.strip().casefold() == wanted:
                return category.pk
        raise serializers.ValidationError(
            {
                gettext("Standardkategorie"): gettext("Unbekannte Kategorie „{name}“.").format(
                    name=name
                )
            }
        )

    def partner_row(self, index: int, values: dict, next_number) -> None:
        from .partners import PartnerSerializer

        number = str(values.get("number", "")).strip()
        partner = self.by_number.get(number.casefold()) if number else None
        name = str(values.get("name", "")).strip()
        if partner is None and not name:
            if number:
                self.error(
                    gettext("Geschäftspartner"),
                    index,
                    gettext("Nummer {number} unbekannt und kein Name.").format(number=number),
                )
            return
        if partner is None and not number and name.casefold() in self.names:
            self.skipped += 1
            return
        try:
            data = self.payload(values, partner)
        except serializers.ValidationError as exc:
            self.error(gettext("Geschäftspartner"), index, exc.detail)
            return
        serializer = PartnerSerializer(
            partner,
            data=data,
            partial=partner is not None,
            context={"view": self.view, "request": self.view.request},
        )
        if not serializer.is_valid():
            self.error(gettext("Geschäftspartner"), index, serializer.errors)
            return
        user = self.view.request.user
        try:
            with transaction.atomic():
                partner = self._save(serializer, partner, number, values, next_number, user)
        except _RowError as exc:
            self.error(gettext("Geschäftspartner"), index, exc.detail)
            return
        self.by_number[partner.number.casefold()] = partner
        self.names.add(partner.name.casefold())

    def _field_values(self, values: dict) -> tuple[dict, dict]:
        incoming, definitions = {}, {}
        for key, field in self.fields.items():
            if key not in values:
                continue
            raw = values[key]
            if field.field_type == "date":
                try:
                    raw = _date(raw, field.label)
                except serializers.ValidationError:
                    pass  # clean_value meldet den Fehler
            incoming[str(field.pk)] = raw
            definitions[str(field.pk)] = field
        return incoming, definitions

    def _save(self, serializer, partner, number, values, next_number, user):
        from .partner_fields import save_values

        created = partner is None
        if created:
            partner = serializer.save(organization=self.org, number=number or next_number())
            changes = diff({}, snapshot(partner))
        else:
            before = snapshot(partner)
            partner = serializer.save()
            changes = diff(before, snapshot(partner))
        incoming, definitions = self._field_values(values)
        errors, field_changes = save_values(self.org, partner, incoming, definitions)
        if errors:
            labels = {str(f.pk): f.label for f in definitions.values()}
            raise _RowError({labels.get(k, k): v for k, v in errors.items()})
        changes.update(field_changes)
        if created:
            record(self.org, user, "create", partner, changes)
            contact = (partner.details or {}).get("contact", "").strip()
            if contact:
                first, _, last = contact.rpartition(" ")
                PartnerContact.objects.create(
                    organization=self.org,
                    partner=partner,
                    first_name=first,
                    last_name=last or contact,
                    phone=(partner.details or {}).get("phone", ""),
                    is_primary=True,
                    receives_invoices=True,
                )
            self.created += 1
        elif changes:
            record(self.org, user, "update", partner, changes)
            self.updated += 1
        else:
            self.skipped += 1
        return partner

    # Ansprechpartner

    def contact_row(self, index: int, values: dict) -> None:
        from .partners import PartnerContactSerializer

        sheet = gettext("Ansprechpartner")
        number = str(values.get("partner_number", "")).strip()
        partner = self.by_number.get(number.casefold()) if number else None
        if partner is None:
            self.error(
                sheet, index, gettext("Partnernummer „{number}“ unbekannt.").format(number=number)
            )
            return
        last = str(values.get("last_name", "")).strip()
        first = str(values.get("first_name", "")).strip()
        if not last:
            self.error(sheet, index, gettext("Bitte den Namen angeben."))
            return
        data = {}
        try:
            for key in ("last_name", "first_name", "function", "email", "phone", "notes"):
                if key in values:
                    data[key] = str(values[key])
            for key, label in (
                ("is_primary", "Hauptansprechpartner"),
                ("receives_invoices", "erhält Rechnungen"),
                ("receives_mail", "erhält Post"),
            ):
                if key in values:
                    data[key] = _flag(values[key], gettext(label))
        except serializers.ValidationError as exc:
            self.error(sheet, index, exc.detail)
            return
        contact = next(
            (
                c
                for c in PartnerContact.objects.filter(partner=partner)
                if c.last_name.strip().casefold() == last.casefold()
                and c.first_name.strip().casefold() == first.casefold()
            ),
            None,
        )
        serializer = PartnerContactSerializer(contact, data=data, partial=contact is not None)
        if not serializer.is_valid():
            self.error(sheet, index, serializer.errors)
            return
        user = self.view.request.user
        if contact is None:
            contact = serializer.save(organization=self.org, partner=partner)
            record(self.org, user, "create", contact, diff({}, snapshot(contact)))
            self.contacts_created += 1
        else:
            before = snapshot(contact)
            contact = serializer.save()
            changes = diff(before, snapshot(contact))
            if changes:
                record(self.org, user, "update", contact, changes)
                self.contacts_updated += 1
        if contact.is_primary:
            PartnerContact.objects.filter(partner=partner).exclude(pk=contact.pk).update(
                is_primary=False
            )

    def run(self, book, next_number) -> None:
        sheets = book.worksheets
        main = list(sheets[0].iter_rows(values_only=True)) if sheets else []
        if main:
            header = _header(main[0], PARTNER_COLUMNS + MONEY_COLUMNS)
            fields = {f.label.strip().casefold(): f for f in scalar_fields(self.org)}
            for position, title in enumerate(main[0]):
                field = fields.get(str(title or "").strip().casefold())
                if field is not None and position < len(header) and not header[position]:
                    header[position] = f"field:{field.pk}"
                    self.fields[f"field:{field.pk}"] = field
            if "name" not in header and "number" not in header:
                raise serializers.ValidationError(
                    {"file": gettext("Die erste Zeile braucht eine Spalte „Name“.")}
                )
            for index, raw in enumerate(main[1 : MAX_ROWS + 1], start=2):
                values = _cells(header, raw)
                if values:
                    self.partner_row(index, values, next_number)
        for sheet in sheets[1:]:
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            header = _header(rows[0], CONTACT_COLUMNS)
            if "partner_number" not in header:
                continue
            for index, raw in enumerate(rows[1 : MAX_ROWS + 1], start=2):
                values = _cells(header, raw)
                if values:
                    self.contact_row(index, values)

    def result(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "contacts_created": self.contacts_created,
            "contacts_updated": self.contacts_updated,
            "errors": self.errors[:50],
        }
