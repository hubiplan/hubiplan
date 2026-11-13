"""Import von Altdaten (Excel/CSV) in Schritten.

1. Datei hochladen: Kopfzeile und Beispielzeilen lesen, Zuordnung vorschlagen.
2. Spalten zuordnen (Spalte -> Feld), als Vorlage speicherbar.
3. Werte zuordnen (z. B. „Akt.“ -> Mitgliedsart „aktiv“).
4. Prüfen: Fehler und mögliche Dubletten im Dachverband – noch nichts gespeichert.
5. Importieren: nur fehlerfreie Personen; die übrigen als Fehlerliste.
6. Rückgängig: als Ganzes, solange nichts weiter bearbeitet wurde.

Historie aus derselben Datei: zusätzliche Spalten (Eintritt 2, Austritt 2, Art 2 …)
oder weitere Zeilen derselben Person (gleicher Name, Vorname, Geburtsdatum).
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from openpyxl import Workbook

from access.models import Role, RoleAssignment
from audit.models import AuditEntry
from core.i18n import date_text
from customfields.models import FieldDefinition, FieldValue, clean_scalar
from customfields.views import definitions_for
from members import services
from members.gender import parse_gender
from members.models import (
    BillingAddress,
    ContactDetails,
    ContactPerson,
    DepartmentMembership,
    ExitReason,
    FederationMember,
    Household,
    HouseholdMember,
    LegalForm,
    Membership,
    MembershipPeriod,
    MemberType,
    MemberTypeAssignment,
    Person,
    PersonKind,
    overlaps,
)
from members.title import parse_title
from organizations.models import Department, Organization
from organizations.terms import fill

HISTORY = range(2, 6)  # Eintritt 2 … Eintritt 5

BASE_TARGETS = {
    "kind": "Typ (Person/Organisation)",
    "last_name": "Name",
    "first_name": "Vorname",
    "birth_date": "Geburtsdatum",
    "gender": "Geschlecht",
    "title": "Titel",
    "email": "E-Mail",
    "phone": "Telefon",
    "street": "Straße und Hausnummer",
    "postal_code": "PLZ",
    "city": "Ort",
    "country": "Land",
    "club_number": "Mitgliedsnummer im Verein",
    "member_type": "Mitgliedsart",
    "entry_date": "Eintritt",
    "exit_date": "Austritt",
    "exit_reason": "Austrittsgrund",
    "departments": "Abteilung(en)",
    "federation_entry_date": "Eintritt Dachverband (manuell)",
    "board_role": "Vorstandsrolle",
    "board_role_from": "Vorstandsrolle von",
    "board_role_until": "Vorstandsrolle bis",
    # Organisationsmitglieder (J6): ein Ansprechpartner je Zeile
    "name_suffix": "Namenszusatz",
    "legal_form": "Rechtsform",
    "contact_last_name": "Ansprechpartner Name",
    "contact_first_name": "Ansprechpartner Vorname",
    "contact_function": "Ansprechpartner Funktion",
    "contact_email": "Ansprechpartner E-Mail",
    "contact_phone": "Ansprechpartner Telefon",
    # Abweichende Rechnungsanschrift (J3), für Personen und Organisationen
    "billing_name": "Rechnungsempfänger",
    "billing_attention": "Rechnung z. Hd.",
    "billing_street": "Rechnung Straße oder Postfach",
    "billing_postal_code": "Rechnung PLZ",
    "billing_city": "Rechnung Ort",
    "billing_country": "Rechnung Land",
    "billing_email": "Rechnungs-E-Mail",
    "billing_order_reference": "Bestellnummer",
    "billing_leitweg_id": "Leitweg-ID",
    # Haushalte und Firmen (H6): gleicher Name = derselbe Haushalt bzw. dieselbe Firma
    "household": "Haushalt",
    "household_role": "Rolle im Haushalt",
    "company": "Firma",
    "fee_via": "Beitrag über",
}
HOUSEHOLD_TARGETS = ("household", "household_role", "company", "fee_via")
# Ziel -> (Feld der Rechnungsanschrift, Höchstlänge)
BILLING_TARGETS = {
    "billing_name": ("name", 200),
    "billing_attention": ("attention", 200),
    "billing_street": ("street", 200),
    "billing_postal_code": ("postal_code", 20),
    "billing_city": ("city", 100),
    "billing_country": ("country", 100),
    "billing_email": ("email", 254),
    "billing_order_reference": ("order_reference", 100),
    "billing_leitweg_id": ("leitweg_id", 50),
}
CONTACT_TARGETS = {
    "contact_last_name": "last_name",
    "contact_first_name": "first_name",
    "contact_function": "function",
    "contact_email": "email",
    "contact_phone": "phone",
}
for n in HISTORY:
    BASE_TARGETS[f"entry_date_{n}"] = f"Eintritt {n}"
    BASE_TARGETS[f"exit_date_{n}"] = f"Austritt {n}"
    BASE_TARGETS[f"member_type_{n}"] = f"Mitgliedsart {n}"
    BASE_TARGETS[f"exit_reason_{n}"] = f"Austrittsgrund {n}"

# Welche Ziele brauchen eine Wertzuordnung (Dateiwert -> Wert in hubiplan)?
VALUE_MAPPED = {"member_type", "exit_reason", "departments", "board_role"}

SYNONYMS = {
    "kind": ["typ", "mitgliedstyp", "art des mitglieds"],
    "name_suffix": ["zusatz", "namenszusatz", "niederlassung"],
    "legal_form": ["rechtsform"],
    "contact_last_name": ["ansprechpartner", "ansprechpartner nachname", "kontaktperson"],
    "contact_first_name": ["ansprechpartner vorname"],
    "contact_function": ["ansprechpartner funktion"],
    "contact_email": ["ansprechpartner email", "ansprechpartner mail"],
    "contact_phone": ["ansprechpartner telefon", "ansprechpartner tel"],
    "billing_name": ["rechnung name", "rechnung empfänger", "rechnungsanschrift name"],
    "billing_attention": ["rechnung zhd", "rechnung abteilung", "rechnungsanschrift zhd"],
    "billing_street": ["rechnung straße", "rechnung strasse", "rechnungsanschrift straße"],
    "billing_postal_code": ["rechnung postleitzahl", "rechnungsanschrift plz"],
    "billing_city": ["rechnungsanschrift ort"],
    "billing_country": ["rechnungsanschrift land"],
    "billing_email": ["rechnung email", "rechnung mail", "rechnungsmail", "rechnungsemail"],
    "billing_order_reference": ["bestellnr", "bestellnummer", "käuferreferenz"],
    "billing_leitweg_id": ["leitweg id", "leitwegid"],
    "household": ["familie", "haushalt name", "familienname haushalt"],
    "household_role": ["rolle haushalt", "haushaltsrolle", "rolle in der familie"],
    "company": ["arbeitgeber", "firma name"],
    "fee_via": ["beitrag ueber", "beitrag über haushalt", "zahlt über"],
    "last_name": ["name", "nachname", "familienname"],
    "first_name": ["vorname"],
    "birth_date": ["geburtsdatum", "geboren", "geb", "gebdatum", "geburtstag"],
    "gender": ["geschlecht", "anrede", "m/w", "mw", "sex"],
    "title": ["titel", "akademischer titel", "akad titel", "akademischer grad", "grad"],
    "email": ["email", "e-mail", "mail"],
    "phone": ["telefon", "tel", "handy", "mobil"],
    "street": ["strasse", "straße", "adresse", "anschrift", "strasse und hausnummer"],
    "postal_code": ["plz", "postleitzahl"],
    "city": ["ort", "wohnort", "stadt"],
    "country": ["land"],
    "club_number": ["mitgliedsnummer", "mitgliedsnr", "nr", "mitglieds-nr"],
    "member_type": ["mitgliedsart", "art", "status", "beitragsart"],
    "entry_date": ["eintritt", "eintrittsdatum", "beitritt", "mitglied seit"],
    "exit_date": ["austritt", "austrittsdatum"],
    "exit_reason": ["austrittsgrund", "grund"],
    "departments": ["abteilung", "abteilungen", "sparte", "kompanie", "gruppe"],
    "federation_entry_date": ["eintritt dachverband", "verbandseintritt"],
    "board_role": ["vorstandsrolle", "funktion", "amt"],
}


def targets_for(org: Organization) -> dict[str, str]:
    targets = dict(BASE_TARGETS)
    targets["departments"] = f"{org.department_label_plural}"
    targets["federation_entry_date"] = fill("Eintritt {dv_sg} (manuell)", org)
    targets["club_number"] = fill("Mitgliedsnummer {e_im}", org)
    for d in definitions_for(org):
        if d.is_archived:
            continue
        if d.repeatable:
            for sub in d.subfields:
                targets[f"field:{d.pk}:{sub['key']}"] = f"{d.label}: {sub['label']}"
        else:
            targets[f"field:{d.pk}"] = d.label
    return targets


def normalize(text: str) -> str:
    return re.sub(
        r"[^a-z0-9äöüß ]", "", str(text).lower().replace("_", " ").replace(".", "")
    ).strip()


def suggest_mapping(headers: list[str], org: Organization) -> dict[str, str]:
    targets = targets_for(org)
    by_label = {normalize(label): key for key, label in targets.items()}
    # Das feste Feld geht einem gleichnamigen Zusatzfeld vor
    by_label[normalize(BASE_TARGETS["gender"])] = "gender"
    by_label[normalize(BASE_TARGETS["title"])] = "title"
    for key, words in SYNONYMS.items():
        for w in words:
            by_label.setdefault(normalize(w), key)
    mapping, used = {}, set()
    for i, header in enumerate(headers):
        key = by_label.get(normalize(header))
        if key is None:
            m = re.match(
                r"(eintritt|austritt|art|mitgliedsart|grund|austrittsgrund) ?(\d)$",
                normalize(header),
            )
            if m and int(m.group(2)) in HISTORY:
                base = {
                    "eintritt": "entry_date",
                    "austritt": "exit_date",
                    "art": "member_type",
                    "mitgliedsart": "member_type",
                    "grund": "exit_reason",
                    "austrittsgrund": "exit_reason",
                }[m.group(1)]
                key = f"{base}_{m.group(2)}"
        if key and key not in used:
            mapping[str(i)] = key
            used.add(key)
    return mapping


# --- Werte lesen ---


DATE_PATTERNS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y")


def parse_date(value) -> datetime.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if re.fullmatch(r"\d{4}", text):  # nur Jahr: 1. Januar
        return datetime.date(int(text), 1, 1)
    for pattern in DATE_PATTERNS:
        try:
            parsed = datetime.datetime.strptime(text, pattern).date()
        except ValueError:
            continue
        if pattern == "%d.%m.%y":
            raise ValueError(
                gettext("Zweistellige Jahreszahl ist mehrdeutig: {text}").format(text=text)
            )
        return parsed
    raise ValueError(gettext("Kein gültiges Datum: {text}").format(text=text))


def distinct_values(job, target: str) -> list[str]:
    """Verschiedene Dateiwerte einer zugeordneten Spalte (für die Wertzuordnung)."""
    from .reading import read_stored_table

    columns = [
        int(c)
        for c, t in job.mapping.items()
        if t == target or (target in VALUE_MAPPED and t.startswith(f"{target}_"))
    ]
    if not columns:
        return []
    _, rows = read_stored_table(job.file, job.file_name)
    values = set()
    for row in rows:
        for c in columns:
            raw = row[c]
            if raw in (None, ""):
                continue
            parts = str(raw).split(",") if target == "departments" else [str(raw)]
            values.update(p.strip() for p in parts if p.strip())
    return sorted(values)


ORGANIZATION_WORDS = {
    "organisation",
    "organization",
    "org",
    "firma",
    "unternehmen",
    "juristische person",
    "o",
}
PERSON_WORDS = {"person", "natürliche person", "mensch", "p", ""}
# Typische Endungen von Organisationsnamen: nur Hinweis, nie stilles Raten (J6)
ORGANIZATION_ENDINGS = re.compile(
    r"\b(gmbh|ug|ag|e\. ?v\.?|ev|eg|e\. ?g\.|kg|ohg|gbr|stiftung|mbh)$",
    re.IGNORECASE,
)


def parse_kind(raw) -> str:
    text = str(raw or "").strip().lower()
    if text in ORGANIZATION_WORDS:
        return PersonKind.ORGANIZATION
    if text in PERSON_WORDS:
        return PersonKind.PERSON
    raise ValueError(
        gettext("Typ „{raw}“ ist unbekannt (erlaubt: Person oder Organisation).").format(raw=raw)
    )


def parse_legal_form(raw) -> tuple[str, str]:
    """(Rechtsform, Freitext) aus einem Dateiwert; Unbekanntes wird „Sonstige“."""
    text = str(raw or "").strip()
    if not text:
        return "", ""
    key = normalize(text)
    for value, label in LegalForm.choices:
        if key in (normalize(value), normalize(label)):
            return value, ""
    short = {
        "ev": LegalForm.EV,
        "eg": LegalForm.EG,
        "ug": LegalForm.UG,
        "gmbhcokg": LegalForm.KG,
    }
    compact = key.replace(" ", "")
    if compact in short:
        return short[compact], ""
    return LegalForm.OTHER, text[:100]


@dataclass
class PeriodData:
    entry: datetime.date
    exit: datetime.date | None
    reason: str
    member_type: MemberType | None


@dataclass
class PersonGroup:
    rows: list[int] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    periods: list[PeriodData] = field(default_factory=list)
    departments: list[Department] = field(default_factory=list)
    board_roles: list[tuple] = field(default_factory=list)
    fields: dict = field(default_factory=dict)  # Definition-ID -> Wert / Liste
    errors: list[str] = field(default_factory=list)
    duplicate: Person | None = None
    duplicate_info: str = ""
    sources: dict = field(default_factory=dict)  # Feld -> Zeile, aus der der Wert stammt
    contacts: list[dict] = field(default_factory=list)  # Ansprechpartner (Organisationen)
    notes: list[str] = field(default_factory=list)  # Hinweise für die Vorschau


class Lookups:
    """Werte der Organisation für die Wertzuordnung."""

    def __init__(self, org: Organization, value_mapping: dict):
        self.org = org
        self.vm = value_mapping
        self.types = {t.pk: t for t in MemberType.objects.filter(organization=org)}
        self.types_by_name = {t.name.lower(): t for t in self.types.values()}
        self.departments = {d.pk: d for d in Department.objects.filter(organization=org)}
        # Abteilungen auch über den Kurznamen erkennen; der volle Name hat Vorrang
        self.departments_by_name = {
            d.short_name.lower(): d for d in self.departments.values() if d.short_name
        }
        self.departments_by_name.update({d.name.lower(): d for d in self.departments.values()})
        self.roles = {r.pk: r for r in Role.objects.filter(organization=org)}
        self.roles_by_name = {r.name.lower(): r for r in self.roles.values()}
        self.definitions = {d.pk: d for d in definitions_for(org)}

    def mapped(self, target: str, raw: str):
        return self.vm.get(target, {}).get(str(raw).strip())

    def member_type(self, raw) -> MemberType | None:
        if raw in (None, ""):
            return None
        mapped = self.mapped("member_type", raw)
        if mapped:
            return self.types.get(int(mapped))
        found = self.types_by_name.get(str(raw).strip().lower())
        if found is None:
            raise ValueError(gettext("Unbekannte Mitgliedsart: {raw}").format(raw=raw))
        return found

    def exit_reason(self, raw) -> str:
        if raw in (None, ""):
            return ExitReason.EXIT
        mapped = self.mapped("exit_reason", raw)
        if mapped:
            return mapped
        for value, label in ExitReason.choices:
            if str(raw).strip().lower() in (value, label.lower()):
                return value
        raise ValueError(gettext("Unbekannter Austrittsgrund: {raw}").format(raw=raw))

    def departments_of(self, raw) -> list[Department]:
        result = []
        for part in str(raw or "").split(","):
            part = part.strip()
            if not part:
                continue
            mapped = self.mapped("departments", part)
            dep = (
                self.departments.get(int(mapped))
                if mapped
                else self.departments_by_name.get(part.lower())
            )
            if dep is None:
                raise ValueError(fill("Unbekannt{adj} {sg}: ", self.org) + part)
            result.append(dep)
        return result

    def role(self, raw) -> Role | None:
        if raw in (None, ""):
            return None
        mapped = self.mapped("board_role", raw)
        role = (
            self.roles.get(int(mapped))
            if mapped
            else self.roles_by_name.get(str(raw).strip().lower())
        )
        if role is None:
            raise ValueError(gettext("Unbekannte Vorstandsrolle: {raw}").format(raw=raw))
        return role


GERMANY = {"", "deutschland", "de", "deu", "germany"}


def _pad_postal_code(g, index) -> None:
    """Als Zahl gespeicherte PLZ verlieren in Excel die führende 0 (Datenaudit 08.11. FD-09).

    Bei Land „Deutschland“ (oder leer) wird eine vierstellige PLZ auf fünf Stellen
    aufgefüllt; die Vorschau zeigt das an."""
    code = g.data.get("postal_code") or ""
    country = (g.data.get("country") or "").strip().lower()
    if len(code) == 4 and code.isdigit() and country in GERMANY:
        g.data["postal_code"] = "0" + code
        g.notes.append(
            gettext("Zeile {index}: PLZ „{old}“ zu „{new}“ ergänzt.").format(
                index=index, old=code, new="0" + code
            )
        )


def _value(row, mapping, target):
    for col, t in mapping.items():
        if t == target:
            v = row[int(col)]
            return v if v not in ("",) else None
    return None


def group_rows(job, rows: list[list], lookups: Lookups) -> list[PersonGroup]:
    mapping = job.mapping
    groups: dict[tuple, PersonGroup] = {}
    aliases: dict[tuple, tuple] = {}  # Name+Geburtstag -> Gruppe mit Mitgliedsnummer
    order: list[tuple] = []
    for index, row in enumerate(rows, start=2):  # Zeile 1 ist die Kopfzeile
        errors = []
        last = str(_value(row, mapping, "last_name") or "").strip()
        first = str(_value(row, mapping, "first_name") or "").strip()
        suffix = str(_value(row, mapping, "name_suffix") or "").strip()
        try:
            kind = parse_kind(_value(row, mapping, "kind"))
        except ValueError as exc:
            kind, errors = PersonKind.PERSON, [str(exc)]
        try:
            birth = parse_date(_value(row, mapping, "birth_date"))
        except ValueError as exc:
            birth = None
            errors.append(gettext("Geburtsdatum: {exc}").format(exc=exc))
        # Fachfrage 11 (Audit 31.10.): eine Mitgliedsnummer ordnet sicherer zu als Name und
        # Geburtstag; ohne sie gelten gleicher Name und Geburtstag als dieselbe Person
        number = str(_value(row, mapping, "club_number") or "").strip()
        if kind == PersonKind.ORGANIZATION:
            # Organisationen: gleicher Name und Zusatz gelten als dieselbe
            name_key = ("org", last.lower(), suffix.lower()) if last else None
        else:
            name_key = (last.lower(), first.lower(), birth) if last and first and birth else None
        if number:
            key = ("nr", number.lower())
            if name_key and name_key in groups and key not in groups:
                # dieselbe Person stand schon ohne Nummer in einer früheren Zeile
                key = name_key
        elif name_key:
            key = aliases.get(name_key, name_key)
        else:
            key = ("zeile", index)
        if number and name_key and name_key not in aliases:
            aliases[name_key] = key
        if key not in groups:
            groups[key] = PersonGroup()
            order.append(key)
        g = groups[key]
        g.rows.append(index)
        g.errors.extend(f"Zeile {index}: {e}" for e in errors)
        if not g.data:
            g.data = {"last_name": last, "first_name": first, "birth_date": birth, "kind": kind}
            if suffix:
                g.data["name_suffix"] = suffix
            raw_form = _value(row, mapping, "legal_form")
            if raw_form not in (None, ""):
                g.data["legal_form"], g.data["legal_form_other"] = parse_legal_form(raw_form)
        else:
            if kind != g.data.get("kind"):
                g.errors.append(
                    gettext("Zeile {index}: Typ widerspricht Zeile {first_row}.").format(
                        index=index, first_row=g.rows[0]
                    )
                )
            base = (("last_name", last), ("first_name", first), ("birth_date", birth))
            for target, value in base:
                _conflict(g, target, value, index)
        for target in ("email", "phone", "street", "postal_code", "city", "country", "club_number"):
            value = _value(row, mapping, target)
            if value in (None, ""):
                continue
            value = str(value).strip()
            if not g.data.get(target):
                g.data[target] = value
                g.sources[target] = index
            else:
                _conflict(g, target, value, index)
        _pad_postal_code(g, index)
        _read_billing(g, row, mapping, index)
        _read_household(g, row, mapping, index)
        raw_gender = _value(row, mapping, "gender")
        if raw_gender not in (None, "") and not g.data.get("gender"):
            gender = parse_gender(raw_gender)
            if gender is None:
                g.errors.append(
                    gettext(
                        "Zeile {index}: Geschlecht: „{raw_gender}“ ist unbekannt (erlaubt: "
                        "männlich, weiblich, divers oder leer)."
                    ).format(index=index, raw_gender=raw_gender)
                )
            elif gender:
                g.data["gender"] = gender
        raw_title = _value(row, mapping, "title")
        if raw_title not in (None, "") and not g.data.get("title"):
            # frei; übliche Schreibweisen vereinheitlicht („dr“ → „Dr.“)
            if title := parse_title(raw_title):
                g.data["title"] = title
        try:
            fed = parse_date(_value(row, mapping, "federation_entry_date"))
            if fed:
                g.data["federation_entry_date"] = fed
        except ValueError as exc:
            g.errors.append(f"Zeile {index}: " + fill("Eintritt {dv_sg}: ", lookups.org) + str(exc))
        _read_periods(g, row, mapping, lookups, index)
        try:
            deps = lookups.departments_of(_value(row, mapping, "departments"))
            g.departments.extend(d for d in deps if d not in g.departments)
        except ValueError as exc:
            g.errors.append(gettext("Zeile {index}: {exc}").format(index=index, exc=exc))
        _read_role(g, row, mapping, lookups, index)
        _read_fields(g, row, mapping, lookups, index)
        _read_contact(g, row, mapping, index)
    return [groups[k] for k in order]


def _read_billing(g, row, mapping, index) -> None:
    """Rechnungsanschrift: erster Wert gilt, ein anderer in einer weiteren Zeile ist ein
    Widerspruch (wie bei der Anschrift)."""
    for target in BILLING_TARGETS:
        value = _value(row, mapping, target)
        if value in (None, ""):
            continue
        value = str(value).strip()
        if not value:
            continue
        if not g.data.get(target):
            g.data[target] = value
            g.sources[target] = index
        else:
            _conflict(g, target, value, index)
    code = g.data.get("billing_postal_code") or ""
    country = (g.data.get("billing_country") or "").strip().lower()
    if g.sources.get("billing_postal_code") == index and (
        len(code) == 4 and code.isdigit() and country in GERMANY
    ):
        g.data["billing_postal_code"] = "0" + code
        g.notes.append(
            gettext("Zeile {index}: PLZ „{old}“ zu „{new}“ ergänzt.").format(
                index=index, old=code, new="0" + code
            )
        )


def _read_household(g, row, mapping, index) -> None:
    """Haushalt, Rolle, Firma und „Beitrag über“: erster Wert gilt, wie bei der Anschrift."""
    for target in HOUSEHOLD_TARGETS:
        value = _value(row, mapping, target)
        value = "" if value is None else str(value).strip()
        if not value:
            continue
        if not g.data.get(target):
            g.data[target] = value
            g.sources[target] = index
        else:
            _conflict(g, target, value, index)


ROLE_WORDS = {
    "erwachsen": HouseholdMember.Role.ADULT,
    "erwachsener": HouseholdMember.Role.ADULT,
    "erwachsene": HouseholdMember.Role.ADULT,
    "adult": HouseholdMember.Role.ADULT,
    "kind": HouseholdMember.Role.CHILD,
    "child": HouseholdMember.Role.CHILD,
}
FEE_VIA_WORDS = {
    "haushalt": Household.Kind.FAMILY,
    "familie": Household.Kind.FAMILY,
    "household": Household.Kind.FAMILY,
    "firma": Household.Kind.COMPANY,
    "company": Household.Kind.COMPANY,
}


def _check_household(g) -> None:
    d = g.data
    for target, limit in (("household", 200), ("company", 200)):
        if len(d.get(target, "")) > limit:
            g.errors.append(
                gettext("{label}: höchstens {limit} Zeichen.").format(
                    label=BASE_TARGETS[target], limit=limit
                )
            )
    role = (d.get("household_role") or "").casefold()
    if role and role not in ROLE_WORDS:
        g.errors.append(
            gettext(
                "Rolle im Haushalt: „{value}“ ist unbekannt (erlaubt: Erwachsener, Kind oder leer)."
            ).format(value=d["household_role"])
        )
    via = (d.get("fee_via") or "").casefold()
    if via and via not in FEE_VIA_WORDS and via not in ("selbst", "einzeln", "-"):
        g.errors.append(
            gettext(
                "Beitrag über: „{value}“ ist unbekannt (erlaubt: Haushalt, Firma oder leer)."
            ).format(value=d["fee_via"])
        )
    elif via in FEE_VIA_WORDS:
        kind = FEE_VIA_WORDS[via]
        needed = "household" if kind == Household.Kind.FAMILY else "company"
        if not d.get(needed):
            g.errors.append(
                gettext("Beitrag über {value}: Spalte „{column}“ ist leer.").format(
                    value=d["fee_via"], column=BASE_TARGETS[needed]
                )
            )


def _join_households(org, d, membership, valid_from, cache, created) -> None:
    """Mitglied den Haushalten aus der Datei zuordnen; gleiche Namen = derselbe Haushalt."""
    from members.households import add_member

    via = FEE_VIA_WORDS.get((d.get("fee_via") or "").casefold())
    for target, kind in (("household", Household.Kind.FAMILY), ("company", Household.Kind.COMPANY)):
        name = (d.get(target) or "").strip()
        if not name:
            continue
        key = (kind, name.casefold())
        if key not in cache:
            for existing in Household.objects.filter(organization=org, kind=kind):
                cache.setdefault((kind, existing.name.strip().casefold()), existing)
        household = cache.get(key)
        if household is None:
            household = Household.objects.create(organization=org, kind=kind, name=name)
            created["households"].append(household.pk)
            cache[key] = household
        role = ROLE_WORDS.get((d.get("household_role") or "").casefold(), "")
        add_member(
            household,
            membership,
            role=role if kind == Household.Kind.FAMILY else "",
            valid_from=valid_from,
            pays_via=via == kind,
        )


def billing_values(d: dict) -> dict:
    """Felder der Rechnungsanschrift aus den gelesenen Daten (leer: keine)."""
    return {key: d[target] for target, (key, _) in BILLING_TARGETS.items() if d.get(target)}


def _check_billing(g) -> None:
    values = billing_values(g.data)
    if not values:
        return
    for target, (key, limit) in BILLING_TARGETS.items():
        if len(values.get(key, "")) > limit:
            g.errors.append(
                gettext("{label}: höchstens {limit} Zeichen.").format(
                    label=BASE_TARGETS[target], limit=limit
                )
            )
    street, city = values.get("street", ""), values.get("city", "")
    if (street or city or values.get("postal_code")) and not (street and city):
        g.errors.append(
            gettext(
                "Für eine eigene Rechnungsanschrift bitte Straße (oder Postfach) und Ort angeben."
            )
        )
    if values.get("email"):
        try:
            validate_email(values["email"])
        except DjangoValidationError:
            g.errors.append(gettext("Die Rechnungs-E-Mail ist ungültig."))


def _read_contact(g, row, mapping, index):
    values = {
        key: str(_value(row, mapping, target) or "").strip()
        for target, key in CONTACT_TARGETS.items()
    }
    if not any(values.values()):
        return
    if not values["last_name"]:
        g.errors.append(
            gettext("Zeile {index}: Name des Ansprechpartners fehlt.").format(index=index)
        )
        return
    if values["email"]:
        try:
            validate_email(values["email"])
        except DjangoValidationError:
            g.errors.append(
                gettext("Zeile {index}: E-Mail des Ansprechpartners ist ungültig.").format(
                    index=index
                )
            )
            return
    same = (values["last_name"].lower(), values["first_name"].lower())
    if any((c["last_name"].lower(), c["first_name"].lower()) == same for c in g.contacts):
        return  # derselbe Ansprechpartner in mehreren Zeilen
    values["row"] = index
    g.contacts.append(values)


CONFLICT_LABELS = {
    "last_name": "Nachname",
    "first_name": "Vorname",
    "birth_date": "Geburtsdatum",
    "email": "E-Mail",
    "phone": "Telefon",
    "street": "Straße",
    "postal_code": "PLZ",
    "city": "Ort",
    "country": "Land",
    "club_number": "Mitgliedsnummer",
    **{target: BASE_TARGETS[target] for target in BILLING_TARGETS},
}


def _conflict(g, target: str, value, index: int) -> None:
    """Widersprüchliche Angaben derselben Person nicht still übergehen (Fachfrage 11)."""
    known = g.data.get(target)
    if value in (None, "") or known in (None, ""):
        return
    same = (
        str(value).strip().casefold() == str(known).strip().casefold()
        if isinstance(value, str)
        else value == known
    )
    if same:
        return
    first_row = getattr(g, "sources", {}).get(target, g.rows[0])
    shown = value.strftime("%d.%m.%Y") if hasattr(value, "strftime") else value
    before = known.strftime("%d.%m.%Y") if hasattr(known, "strftime") else known
    g.errors.append(
        gettext(
            "Zeile {index}: {x1} „{shown}“ widerspricht Zeile {first_row} "
            "(„{before}“). Bitte in der Datei vereinheitlichen."
        ).format(
            index=index, x1=CONFLICT_LABELS[target], shown=shown, first_row=first_row, before=before
        )
    )


def _read_periods(g, row, mapping, lookups, index):
    for suffix in ["", *[f"_{n}" for n in HISTORY]]:
        try:
            entry = parse_date(_value(row, mapping, f"entry_date{suffix}"))
            exit_ = parse_date(_value(row, mapping, f"exit_date{suffix}"))
            raw_type = _value(row, mapping, f"member_type{suffix}")
            if entry is None:
                if exit_ or raw_type:
                    g.errors.append(
                        gettext("Zeile {index}: Eintritt{x1} fehlt.").format(
                            index=index, x1=suffix.replace("_", " ")
                        )
                    )
                continue
            member_type = lookups.member_type(raw_type) if raw_type else None
            reason = (
                lookups.exit_reason(_value(row, mapping, f"exit_reason{suffix}")) if exit_ else ""
            )
        except ValueError as exc:
            g.errors.append(gettext("Zeile {index}: {exc}").format(index=index, exc=exc))
            continue
        same = next((p for p in g.periods if p.entry == entry), None)
        if same is not None:
            # Gleicher Zeitraum in mehreren Zeilen; abweichende Angaben sind ein Widerspruch
            # (Datenaudit 08.11. DR-08)
            pairs = (
                (same.exit, exit_),
                (same.reason, reason),
                (getattr(same.member_type, "pk", None), getattr(member_type, "pk", None)),
            )
            if any(a not in (None, "") and b not in (None, "") and a != b for a, b in pairs):
                g.errors.append(
                    gettext(
                        "Zeile {index}: Zeitraum ab {entry} widerspricht einer früheren Zeile."
                    ).format(index=index, entry=entry.strftime("%d.%m.%Y"))
                )
            continue
        g.periods.append(PeriodData(entry, exit_, reason, member_type))


def _read_role(g, row, mapping, lookups, index):
    try:
        role = lookups.role(_value(row, mapping, "board_role"))
        if role is None:
            return
        start = parse_date(_value(row, mapping, "board_role_from"))
        end = parse_date(_value(row, mapping, "board_role_until"))
    except ValueError as exc:
        g.errors.append(gettext("Zeile {index}: {exc}").format(index=index, exc=exc))
        return
    if start is None:
        g.errors.append(gettext("Zeile {index}: Vorstandsrolle ohne Beginn.").format(index=index))
        return
    g.board_roles.append((role, start, end))


def _read_fields(g, row, mapping, lookups, index):
    repeat_rows: dict[int, dict] = {}
    for col, target in mapping.items():
        if not target.startswith("field:"):
            continue
        raw = row[int(col)]
        if raw in (None, ""):
            continue
        parts = target.split(":")
        definition = lookups.definitions.get(int(parts[1]))
        if definition is None:
            continue
        try:
            if len(parts) == 2:
                value = clean_scalar(
                    definition.field_type,
                    _plain(raw, definition.field_type),
                    definition.choices,
                )
                if definition.pk not in g.fields:
                    g.fields[definition.pk] = value
                elif g.fields[definition.pk] != value:
                    # Widersprüchliche Werte nicht still übergehen (Datenaudit 08.11. DR-08)
                    g.errors.append(
                        gettext(
                            "Zeile {index}: {x1}: „{value}“ widerspricht „{known}“ aus einer "
                            "früheren Zeile."
                        ).format(
                            index=index,
                            x1=definition.label,
                            value=value,
                            known=g.fields[definition.pk],
                        )
                    )
            else:
                sub = next(s for s in definition.subfields if s["key"] == parts[2])
                repeat_rows.setdefault(definition.pk, {})[sub["key"]] = clean_scalar(
                    sub["type"], _plain(raw, sub["type"]), sub.get("choices")
                )
        except (DjangoValidationError, StopIteration, ValueError) as exc:
            # Ungültiges Datum (ValueError) als Zeilenfehler, nicht als Abbruch der ganzen
            # Prüfung (Datenaudit 08.11. DA-04)
            if isinstance(exc, DjangoValidationError):
                message = " ".join(exc.messages)
            elif isinstance(exc, ValueError):
                message = str(exc)
            else:
                message = "Unbekanntes Feld"
            g.errors.append(
                gettext("Zeile {index}: {x1}: {message}").format(
                    index=index, x1=definition.label, message=message
                )
            )
    for def_id, entry in repeat_rows.items():
        g.fields.setdefault(def_id, [])
        if entry not in g.fields[def_id]:
            g.fields[def_id].append(entry)


def _plain(raw, field_type):
    if field_type == "date":
        return parse_date(raw).isoformat()
    return raw


# --- Prüfen ---


def check_group(
    g: PersonGroup, org: Organization, link_duplicates: bool, names: dict | None = None
) -> None:
    """``names``: vorab gelesener Namensindex des Vereins (services.club_name_index)."""
    d = g.data
    organization = d.get("kind") == PersonKind.ORGANIZATION
    required = ("last_name",) if organization else ("last_name", "first_name")
    for target in required:
        if not d.get(target):
            g.errors.append(gettext("{x0} fehlt.").format(x0=BASE_TARGETS[target]))
    if organization:
        if d.get("first_name") or d.get("birth_date"):
            g.errors.append(gettext("Eine Organisation hat keinen Vornamen und kein Geburtsdatum."))
    else:
        if g.contacts:
            g.errors.append(gettext("Ansprechpartner gibt es nur bei Organisationen."))
        if d.get("name_suffix") or d.get("legal_form"):
            g.errors.append(gettext("Namenszusatz und Rechtsform gibt es nur bei Organisationen."))
        if (
            not d.get("first_name")
            and not d.get("birth_date")
            and ORGANIZATION_ENDINGS.search(d.get("last_name", "").strip())
        ):
            # Kein Raten: der Vorstand ergänzt die Spalte „Typ“ (J6)
            g.errors.append(
                gettext(
                    "„{name}“ sieht nach einer Organisation aus. Bitte in der Spalte „Typ“ "
                    "„Organisation“ eintragen."
                ).format(name=d.get("last_name"))
            )
    _check_billing(g)
    _check_household(g)
    if not g.periods:
        g.errors.append(gettext("Kein Eintrittsdatum."))
    periods = sorted(g.periods, key=lambda p: p.entry)
    for i, p in enumerate(periods):
        if p.member_type is None:
            g.errors.append(
                gettext("Zeitraum ab {x0}: Mitgliedsart fehlt.").format(x0=date_text(p.entry))
            )
        if p.exit and p.exit < p.entry:
            g.errors.append(
                gettext("Zeitraum ab {x0}: Austritt vor Eintritt.").format(x0=date_text(p.entry))
            )
        if d.get("birth_date") and p.entry < d["birth_date"]:
            g.errors.append(
                gettext("Zeitraum ab {x0}: Eintritt vor der Geburt.").format(x0=date_text(p.entry))
            )
        for q in periods[i + 1 :]:
            if overlaps(p.entry, p.exit, q.entry, q.exit):
                g.errors.append(gettext("Zeiträume überschneiden sich."))
    current = [p for p in periods if p.exit is None]
    if len(current) > 1:
        g.errors.append(gettext("Mehr als ein offener Zeitraum."))
    if current and not all(d.get(k) for k in ("street", "postal_code", "city")):
        g.errors.append(gettext("Für aktuelle Mitglieder ist die Anschrift Pflicht."))
    if organization and not g.errors:
        name = d["last_name"].lower()
        suffix = d.get("name_suffix", "").lower()
        for m in Membership.objects.filter(
            organization=org, person__kind=PersonKind.ORGANIZATION
        ).select_related("person"):
            if m.person.last_name.lower() == name and m.person.name_suffix.lower() == suffix:
                g.errors.append(fill("Die Organisation ist bereits Mitglied {e_dieses}.", org))
                break
        return
    if g.errors:
        return
    if not d.get("birth_date"):
        # Ohne Geburtsdatum keine Dublettensuche; eigene Mitglieder gleichen Namens melden
        if services.club_namesakes(org, d["last_name"], d["first_name"], index=names):
            g.errors.append(
                gettext(
                    "Eine Person mit diesem Namen ist hier bereits Mitglied. "
                    "Bitte das Geburtsdatum angeben."
                )
            )
        return
    found = services.find_duplicates(org, d["last_name"], d["first_name"], d["birth_date"])
    exact = [
        p
        for p in found
        if p.last_name.lower() == d["last_name"].lower()
        and p.first_name.lower() == d["first_name"].lower()
    ]
    if len(exact) > 1:
        g.errors.append(fill("Mehrere passende Personen {dv_im}; bitte von Hand zuordnen.", org))
        return
    if exact:
        person = exact[0]
        if Membership.objects.filter(organization=org, person=person).exists():
            g.errors.append(fill("Die Person ist bereits Mitglied {e_dieses}.", org))
            return
        g.duplicate = person
        fm = getattr(person, "federation", None)
        g.duplicate_info = fill("Vorhandene Person {dv_im}", org) + (
            f" (Verbandsnr. {fm.member_number})" if fm else ""
        )
        if not link_duplicates:
            g.errors.append(fill("Mögliche Dublette {dv_im} (Verknüpfen ist ausgeschaltet).", org))
            return
        today = timezone.localdate()
        for p in current:
            if (
                p.member_type
                and p.member_type.active
                and services.active_elsewhere(person, org, today)
            ):
                g.errors.append(fill("Die Person ist bereits in {e_einem_anderen} aktiv.", org))


def validate(job) -> list[PersonGroup]:
    from .reading import read_stored_table

    _, rows = read_stored_table(job.file, job.file_name)
    lookups = Lookups(job.organization, job.value_mapping)
    groups = group_rows(job, rows, lookups)
    link = job.options.get("link_duplicates", True)
    names = None
    if any(not g.data.get("birth_date") for g in groups):
        names = services.club_name_index(job.organization)
    for g in groups:
        check_group(g, job.organization, link, names)
    return groups


def preview_of(groups: list[PersonGroup]) -> tuple[list[dict], dict]:
    preview = []
    counts = {"persons": len(groups), "ok": 0, "errors": 0, "duplicates": 0, "rows": 0}
    for g in groups:
        counts["rows"] += len(g.rows)
        status = "error" if g.errors else ("duplicate" if g.duplicate else "ok")
        counts["errors" if g.errors else "ok"] += 1
        counts["duplicates"] += int(bool(g.duplicate and not g.errors))
        preview.append(
            {
                "rows": g.rows,
                "name": (
                    " – ".join(p for p in (g.data.get("last_name"), g.data.get("name_suffix")) if p)
                    if g.data.get("kind") == PersonKind.ORGANIZATION
                    else f"{g.data.get('last_name', '')}, {g.data.get('first_name', '')}".strip(
                        ", "
                    )
                ),
                "kind": g.data.get("kind", PersonKind.PERSON),
                "birth_date": g.data["birth_date"].isoformat()
                if g.data.get("birth_date")
                else None,
                "periods": len(g.periods),
                "status": status,
                "messages": g.errors or ([g.duplicate_info] if g.duplicate else []) + g.notes,
            }
        )
    return preview, counts


# --- Importieren ---


@transaction.atomic
def run(job, user) -> dict:
    groups = validate(job)
    org = job.organization
    scope = services.scope_for(org)
    created = {
        k: []
        for k in (
            "persons",
            "memberships",
            "contacts",
            "field_values",
            "role_assignments",
            "federation_members",
            "households",
        )
    }
    households: dict = {}
    errors = []
    audit = []
    # Zeilen ohne Mitgliedsnummer bekommen die nächste freie, auch über die Nummern der Datei
    in_file = [g.data.get("club_number", "") for g in groups if not g.errors]
    next_number = None
    for g in groups:
        if g.errors:
            errors.append(g)
            continue
        d = g.data
        person = g.duplicate
        if person is None:
            organization = d.get("kind") == PersonKind.ORGANIZATION
            person = Person.objects.create(
                scope=scope,
                kind=d.get("kind", PersonKind.PERSON),
                last_name=d["last_name"],
                first_name="" if organization else d["first_name"],
                birth_date=None if organization else d["birth_date"],
                gender=d.get("gender", ""),
                title="" if organization else d.get("title", ""),
                name_suffix=d.get("name_suffix", "") if organization else "",
                legal_form=d.get("legal_form", "") if organization else "",
                legal_form_other=d.get("legal_form_other", "") if organization else "",
            )
            created["persons"].append(person.pk)
        club_number = (d.get("club_number") or "").strip()
        if not club_number:
            if next_number is None:
                next_number = services.next_club_number(org, in_file)
            club_number = next_number
            next_number = str(int(next_number) + 1).zfill(len(next_number))
        membership = Membership.objects.create(
            organization=org, scope=scope, person=person, club_number=club_number
        )
        created["memberships"].append(membership.pk)
        for i, c in enumerate(g.contacts):
            ContactPerson.objects.create(
                organization=org,
                membership=membership,
                last_name=c["last_name"],
                first_name=c["first_name"],
                function=c["function"][:100],
                email=c["email"],
                phone=c["phone"][:50],
                is_primary=i == 0,
            )
        billing = billing_values(d)
        if billing:
            # verschwindet beim Rückgängigmachen mit der Mitgliedschaft
            BillingAddress.objects.create(organization=org, membership=membership, **billing)
        reported = False
        for p in sorted(g.periods, key=lambda x: x.entry):
            MembershipPeriod.objects.create(
                organization=org,
                membership=membership,
                entry_date=p.entry,
                exit_date=p.exit,
                exit_reason=p.reason if p.exit else "",
            )
            MemberTypeAssignment.objects.create(
                organization=org,
                membership=membership,
                member_type=p.member_type,
                valid_from=p.entry,
                valid_until=p.exit,
            )
            reported = reported or p.member_type.reported
        latest = max(g.periods, key=lambda x: x.entry)
        if not latest.exit:
            _join_households(org, d, membership, latest.entry, households, created)
        for dep in g.departments:
            DepartmentMembership.objects.create(
                organization=org,
                membership=membership,
                department=dep,
                valid_from=latest.entry,
                valid_until=latest.exit,
            )
        # Aktuelle Mitglieder haben laut Prüfung vollständige Kontaktdaten; bei früheren
        # Mitgliedern gilt auch ein Teil (z. B. nur Telefon) und darf nicht wegfallen.
        if any(d.get(k) for k in services.CONTACT_FIELDS if k != "country"):
            existing = services.contact_for(person, org)
            if existing is None:
                contact = services.save_contact(
                    person, org, {k: d[k] for k in services.CONTACT_FIELDS if d.get(k)}
                )
                created["contacts"].append(contact.pk)
        if reported and org.federation:
            had = FederationMember.objects.filter(person=person).exists()
            fm = services.ensure_federation_member(person, org)
            if not had:
                created["federation_members"].append(fm.pk)
            if d.get("federation_entry_date") and not fm.manual_entry_date:
                fm.manual_entry_date = d["federation_entry_date"]
                fm.save()
        for role, start, end in g.board_roles:
            ra = RoleAssignment.objects.create(
                organization=org,
                role=role,
                user=None,
                person=person,
                valid_from=start,
                valid_until=end,
            )
            created["role_assignments"].append(ra.pk)
        for def_id, value in g.fields.items():
            definition = FieldDefinition.objects.get(pk=def_id)
            if FieldValue.objects.filter(definition=definition, person=person).exists():
                continue
            fv = FieldValue.objects.create(
                organization=definition.organization,
                definition=definition,
                person=person,
                value=value,
            )
            created["field_values"].append(fv.pk)
        audit.append(
            AuditEntry(
                organization=org,
                user=user,
                user_email=getattr(user, "email", ""),
                action="create",
                object_type="Mitgliedschaft",
                object_id=str(membership.pk),
                object_repr=str(person)[:200],
                changes={"Import": [None, job.file_name]},
                person_id=person.pk,
            )
        )
    AuditEntry.objects.bulk_create(audit)
    from audit.chain import seal_later

    seal_later(org.pk)
    job.created = created
    job.imported_at = timezone.now()
    job.status = job.Status.IMPORTED
    job.counts = {**job.counts, "imported": len(created["memberships"]), "failed": len(errors)}
    if errors:
        job.error_file.save(f"fehler-{job.pk}.xlsx", _error_file(job, errors), save=False)
    job.save()
    from audit.log import record

    record(
        org,
        user,
        "create",
        job,
        {
            "Datei": [None, job.file_name],
            "importiert": [None, job.counts["imported"]],
            "fehlerhaft": [None, job.counts["failed"]],
        },
    )
    return job.counts


def _error_file(job, groups: list[PersonGroup]):
    from django.core.files.base import ContentFile

    from .reading import read_stored_table

    headers, rows = read_stored_table(job.file, job.file_name)
    wb = Workbook()
    ws = wb.active
    ws.title = "Fehler"
    from .export import safe_cell

    ws.append(["Fehler", *[safe_cell(h) for h in headers]])
    for g in groups:
        for index in g.rows:
            ws.append(["; ".join(g.errors), *[safe_cell(v) for v in rows[index - 2]]])
    buf = __import__("io").BytesIO()
    wb.save(buf)
    return ContentFile(buf.getvalue())


# --- Rückgängig ---


def undo_blockers(job) -> list[str]:
    """Gründe, warum ein Import nicht mehr rückgängig gemacht werden kann."""
    if job.status != job.Status.IMPORTED:
        return ["Nur ein abgeschlossener Import lässt sich rückgängig machen."]
    created = job.created
    memberships = Membership.objects.filter(pk__in=created.get("memberships", []))
    since = job.imported_at
    blockers = []
    if memberships.filter(updated_at__gt=since).exists():
        blockers.append("Mitgliedschaften wurden seit dem Import geändert.")
    later = AuditEntry.objects.filter(
        organization=job.organization,
        person_id__in=memberships.values("person_id"),
        timestamp__gt=since,
    ).only("pk", "changes")
    # Inhalt verschlüsselt: Einträge des Imports selbst hier aussortieren
    if any(not _from_import(entry) for entry in later.iterator()):
        blockers.append("Importierte Mitglieder wurden seither bearbeitet.")
    return blockers


def _from_import(entry) -> bool:
    return isinstance(entry.changes, dict) and "Import" in entry.changes


@transaction.atomic
def undo(job, user) -> None:
    blockers = undo_blockers(job)
    if blockers:
        raise DjangoValidationError(blockers)
    c = job.created
    FieldValue.objects.filter(pk__in=c.get("field_values", [])).delete()
    RoleAssignment.objects.filter(pk__in=c.get("role_assignments", [])).delete()
    ContactDetails.objects.filter(pk__in=c.get("contacts", [])).delete()
    memberships = Membership.objects.filter(pk__in=c.get("memberships", []))
    person_ids = list(memberships.values_list("person_id", flat=True))
    # Protokolleinträge bleiben (verkettet), nur ohne Inhalt
    entries = AuditEntry.objects.filter(
        organization=job.organization, person_id__in=person_ids
    ).only("pk", "changes")
    AuditEntry.objects.filter(
        pk__in=[entry.pk for entry in entries.iterator() if _from_import(entry)]
    ).update(changes={}, cleared=True)
    memberships.delete()
    FederationMember.objects.filter(pk__in=c.get("federation_members", [])).delete()
    Person.objects.filter(pk__in=c.get("persons", [])).filter(memberships__isnull=True).delete()
    # Haushalte des Imports, die jetzt leer sind
    Household.objects.filter(pk__in=c.get("households", []), members__isnull=True).delete()
    job.status = job.Status.UNDONE
    job.undone_at = timezone.now()
    job.save()
