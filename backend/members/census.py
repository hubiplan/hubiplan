"""Stichtagsstatistik: Mitglieder an einem Tag nach Alter, Geschlecht, Wohnort und Gruppe.

Für Meldungen an Stadt- und Kreissportbund, Verband und für Zuschussanträge. Gezählt wird der
Bestand nach den Austritten des Stichtags, wie in der Mitgliederentwicklung (``statistics``):
Wer am Stichtag austritt, zählt nicht mehr mit.

- Alter: am Stichtag vollendete Jahre oder nach Jahrgang (Jahr des Stichtags minus
  Geburtsjahr, wie viele Sportbünde zählen)
- Geschlecht: männlich, weiblich, divers, ohne Angabe
- Wohnort: Ort aus der Anschrift, wie der Verein sie sieht (``services.contact_for``)
- Gruppen: Abteilungen (Verein) bzw. Vereine (Dachverband); wer in zwei Abteilungen ist,
  zählt in beiden
- Organisationen als Mitglied haben weder Alter noch Geschlecht und werden getrennt gezählt
"""

from __future__ import annotations

import csv
import datetime
import io
from collections import defaultdict
from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop as N_
from rest_framework import serializers

from .models import ContactDetails, Gender, Membership, PersonKind
from .services import shared_contacts
from .statistics import _age, _Source

# (von, bis, Beschriftung); bis 999 = offen
SCHEMES: dict[str, list[tuple[int, int, str]]] = {
    # Altersgruppen der Bestandserhebung der Landessportbünde
    "sport": [
        (0, 6, N_("bis 6")),
        (7, 14, N_("7 bis 14")),
        (15, 18, N_("15 bis 18")),
        (19, 26, N_("19 bis 26")),
        (27, 40, N_("27 bis 40")),
        (41, 60, N_("41 bis 60")),
        (61, 999, N_("über 60")),
    ],
    # Jugendförderung: Kinder, Jugendliche, junge Erwachsene bis 26
    "jugend": [
        (0, 5, N_("unter 6")),
        (6, 13, N_("6 bis 13")),
        (14, 17, N_("14 bis 17")),
        (18, 26, N_("18 bis 26")),
        (27, 999, N_("27 und älter")),
    ],
    "zehn": [
        (0, 17, N_("unter 18")),
        (18, 29, N_("18 bis 29")),
        (30, 39, N_("30 bis 39")),
        (40, 49, N_("40 bis 49")),
        (50, 59, N_("50 bis 59")),
        (60, 69, N_("60 bis 69")),
        (70, 79, N_("70 bis 79")),
        (80, 999, N_("80 und älter")),
    ],
}
SCHEME_LABELS = {
    "sport": N_("Sportbund (bis 6, 7–14, 15–18, 19–26, 27–40, 41–60, über 60)"),
    "jugend": N_("Jugendförderung (unter 6, 6–13, 14–17, 18–26, ab 27)"),
    "zehn": N_("Zehnjahresgruppen (unter 18, 18–29 … 80 und älter)"),
}
COUNTINGS = ("stichtag", "jahrgang")
GENDERS = [Gender.MALE.value, Gender.FEMALE.value, Gender.DIVERSE.value, ""]


def gender_labels() -> list[str]:
    return [_("männlich"), _("weiblich"), _("divers"), _("ohne Angabe")]


def _parse_day(value: str | None) -> datetime.date:
    today = timezone.localdate()
    if not value:
        return today
    try:
        day = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise serializers.ValidationError(
            {"stichtag": _("Bitte ein Datum im Format JJJJ-MM-TT angeben.")}
        ) from exc
    if day.year < 1900 or day > today.replace(year=today.year + 1):
        raise serializers.ValidationError(
            {"stichtag": _("Der Stichtag liegt außerhalb des möglichen Zeitraums.")}
        )
    return day


def _ids(value: str | None) -> set[int] | None:
    if not value:
        return None
    try:
        return {int(v) for v in value.split(",") if v.strip()}
    except ValueError as exc:
        raise serializers.ValidationError({"arten": _("Ungültige Auswahl.")}) from exc


def _current(pieces, day: datetime.date) -> set[int]:
    """Mitgliedschaften, die am Stichtag nach dessen Austritten dabei sind."""
    return {mid for mid, start, end in pieces if start <= day and (end is None or end > day)}


class _Table:
    """Zählung Altersgruppe × Geschlecht; Zeile ``None`` = ohne Geburtsdatum."""

    def __init__(self, groups: int):
        self.rows = [[0] * len(GENDERS) for _i in range(groups + 1)]

    def add(self, group: int | None, gender: str):
        row = self.rows[-1 if group is None else group]
        row[GENDERS.index(gender if gender in GENDERS else "")] += 1

    @property
    def total(self) -> int:
        return sum(sum(r) for r in self.rows)

    def by_gender(self) -> list[int]:
        return [sum(r[i] for r in self.rows) for i in range(len(GENDERS))]

    def by_age(self) -> list[int]:
        return [sum(r) for r in self.rows]

    def as_dict(self, labels: list[str]) -> dict:
        rows = [
            {"label": label, "counts": counts, "total": sum(counts)}
            for label, counts in zip([*labels, _("ohne Geburtsdatum")], self.rows, strict=True)
        ]
        return {"rows": rows, "genders": self.by_gender(), "total": self.total}


def _group_of(age: int, scheme: list[tuple[int, int, str]]) -> int | None:
    for i, (low, high, _label) in enumerate(scheme):
        if low <= age <= high:
            return i
    return None


def _addresses(mids: set[int]) -> dict[int, tuple[str, str]]:
    """(PLZ, Ort) je Mitgliedschaft, wie ``services.contact_for`` die Anschrift wählt."""
    club_of: dict[int, tuple[int, int]] = {
        mid: (person, org)
        for mid, person, org in Membership.objects.filter(pk__in=mids).values_list(
            "pk", "person_id", "organization_id"
        )
    }
    persons = {p for p, _o in club_of.values()}
    contacts: dict[int, dict[int | None, tuple[str, str, str]]] = defaultdict(dict)
    for person, org, plz, city, country in ContactDetails.objects.filter(
        person_id__in=persons
    ).values_list("person_id", "organization_id", "postal_code", "city", "country"):
        contacts[person][org] = (plz or "", city or "", country or "")
    shared = shared_contacts()
    out: dict[int, tuple[str, str]] = {}
    for mid, (person, org) in club_of.items():
        own = contacts[person].get(org)
        common = contacts[person].get(None)
        found = (common or own) if shared else (own or common)
        if not found:
            out[mid] = ("", "")
            continue
        plz, city, country = (v.strip() for v in found)
        if country and country.lower() not in ("deutschland", "germany", "de"):
            city = f"{city} ({country})" if city else country
        out[mid] = (plz, city)
    return out


def census(src: _Source, params, *, membership_ids=None) -> dict:
    """Stichtagsstatistik einer Sicht (``statistics.club_source`` usw.)."""
    day = _parse_day(params.get("stichtag"))
    scheme_key = params.get("alter") or "sport"
    if scheme_key not in SCHEMES:
        raise serializers.ValidationError({"alter": _("Unbekannte Altersgruppen.")})
    counting = params.get("zaehlung") or "stichtag"
    if counting not in COUNTINGS:
        raise serializers.ValidationError({"zaehlung": _("Unbekannte Zählweise.")})
    scheme = SCHEMES[scheme_key]
    labels = [_(label) for _l, _h, label in scheme]

    current = _current(src.base, day)
    type_options = []
    chosen = _ids(params.get("arten"))
    in_types: set[int] = set()
    for key, name, pieces in src.types:
        members = _current(pieces, day)
        type_options.append({"id": key, "name": name, "count": len(members)})
        if chosen is None or key in chosen:
            in_types |= members
    if chosen is not None:
        current &= in_types

    persons = dict(Membership.objects.filter(pk__in=current).values_list("pk", "person__kind"))
    genders = dict(Membership.objects.filter(pk__in=current).values_list("pk", "person__gender"))
    organizations = {mid for mid in current if persons.get(mid) == PersonKind.ORGANIZATION}
    people = current - organizations

    def age_group(mid: int) -> int | None:
        birth = src.birth.get(mid)
        if birth is None or birth > day:
            return None
        age = day.year - birth.year if counting == "jahrgang" else _age(birth, day)
        return _group_of(age, scheme)

    groups_of = {mid: age_group(mid) for mid in people}
    total = _Table(len(scheme))
    for mid in people:
        total.add(groups_of[mid], genders.get(mid) or "")

    # Wohnorte: Ort, darunter die vorkommenden Postleitzahlen
    addresses = _addresses(people)
    places: dict[str, _Table] = {}
    codes: dict[str, set[str]] = defaultdict(set)
    spellings: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for mid in people:
        plz, city = addresses.get(mid, ("", ""))
        key = city.casefold()
        spellings[key][city] += 1
        if plz:
            codes[key].add(plz)
        places.setdefault(key, _Table(len(scheme))).add(groups_of[mid], genders.get(mid) or "")
    # Schreibweise eines Orts: die häufigste, bei Gleichstand die mit Großbuchstaben vorn
    names = {
        key: max(found, key=lambda c: (found[c], c[:1].isupper(), c))
        for key, found in spellings.items()
    }
    place_rows = []
    for key, table in places.items():
        place_rows.append(
            {
                "city": names[key] or _("ohne Anschrift"),
                "postal_codes": sorted(codes[key]),
                "genders": table.by_gender(),
                "ages": table.by_age(),
                "total": table.total,
                "missing": not names[key],
            }
        )
    place_rows.sort(key=lambda r: (r["missing"], -r["total"], r["city"].casefold()))

    group_rows = []
    for key, name, pieces in src.groups:
        members = _current(pieces, day) & people
        if not members:
            continue
        table = _Table(len(scheme))
        for mid in members:
            table.add(groups_of[mid], genders.get(mid) or "")
        orgs = len(_current(pieces, day) & organizations)
        group_rows.append({"id": key, "name": name, "organizations": orgs, **table.as_dict(labels)})

    return {
        "stichtag": day,
        "alter": scheme_key,
        "zaehlung": counting,
        "schemes": [{"key": k, "label": _(v)} for k, v in SCHEME_LABELS.items()],
        "age_groups": labels,
        "gender_labels": gender_labels(),
        "types": type_options,
        "arten": sorted(chosen) if chosen is not None else None,
        "total": len(current),
        "persons": len(people),
        "organizations": len(organizations),
        **total.as_dict(labels),
        "places": place_rows,
        "groups_title": src.groups_title,
        "groups": group_rows,
    }


# --- Dateien ---


def _title(data: dict) -> str:
    return _("Mitglieder am {date}").format(date=f"{data['stichtag']:%d.%m.%Y}")


def _basis(data: dict) -> str:
    parts = [_("Alter nach Jahrgang") if data["zaehlung"] == "jahrgang" else _("Alter am Stichtag")]
    if data["arten"] is not None:
        names = [t["name"] for t in data["types"] if t["id"] in data["arten"]]
        parts.append(_("Mitgliedsarten: {names}").format(names=", ".join(names)))
    return " · ".join(parts)


def _age_table(data: dict, block: dict) -> list[list]:
    head = [_("Altersgruppe"), *data["gender_labels"], _("gesamt")]
    rows = [head]
    for r in block["rows"]:
        if r["label"] == _("ohne Geburtsdatum") and not r["total"]:
            continue
        rows.append([r["label"], *r["counts"], r["total"]])
    rows.append([_("Summe"), *block["genders"], block["total"]])
    return rows


def _place_table(data: dict) -> list[list]:
    ages = list(data["age_groups"])
    with_missing = any(p["ages"][-1] for p in data["places"])
    if with_missing:
        ages.append(_("ohne Geburtsdatum"))
    head = [_("Ort"), _("PLZ"), *data["gender_labels"], *ages, _("gesamt")]
    rows = [head]
    for p in data["places"]:
        age_counts = p["ages"] if with_missing else p["ages"][:-1]
        rows.append(
            [p["city"], ", ".join(p["postal_codes"]), *p["genders"], *age_counts, p["total"]]
        )
    return rows


def _group_table(data: dict) -> list[list]:
    head = [data["groups_title"] or _("Gruppe"), _("Altersgruppe"), *data["gender_labels"]]
    rows = [[*head, _("gesamt")]]
    for g in data["groups"]:
        for r in g["rows"]:
            if r["total"]:
                rows.append([g["name"], r["label"], *r["counts"], r["total"]])
        rows.append([g["name"], _("Summe"), *g["genders"], g["total"]])
    return rows


def _summary_rows(org, data: dict) -> list[list]:
    rows = [
        [_("Einheit"), org.name],
        [_("Stichtag"), data["stichtag"]],
        [_("Grundlage"), _basis(data)],
        [_("Mitglieder gesamt"), data["total"]],
        [_("davon Personen"), data["persons"]],
        [_("davon Organisationen"), data["organizations"]],
        [_("Stand"), timezone.localdate()],
    ]
    return rows


def render_xlsx(org, data: dict) -> bytes:
    from finance.project_report import _xlsx

    sheets = [
        (_("Übersicht"), [[_("Angabe"), _("Wert")], *_summary_rows(org, data)]),
        (_("Alter und Geschlecht"), _age_table(data, data)),
        (_("Wohnorte"), _place_table(data)),
    ]
    if data["groups"]:
        sheets.append((data["groups_title"] or _("Gruppen"), _group_table(data)))
    return _xlsx(org, sheets)


def _csv_cell(value):
    if isinstance(value, datetime.date):
        return f"{value:%d.%m.%Y}"
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def render_csv(org, data: dict) -> bytes:
    """Eine Tabelle zum Einlesen: Bereich, Gruppe, Altersgruppe, Geschlechter, gesamt."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [_("Stichtag"), _("Bereich"), _("Gruppe"), _("Altersgruppe"), *data["gender_labels"]]
        + [_("gesamt")]
    )
    day = data["stichtag"]
    for r in data["rows"]:
        writer.writerow(
            [_csv_cell(v) for v in (day, _("Alter und Geschlecht"), "", r["label"], *r["counts"])]
            + [r["total"]]
        )
    for p in data["places"]:
        place = p["city"] + (f" ({', '.join(p['postal_codes'])})" if p["postal_codes"] else "")
        writer.writerow(
            [_csv_cell(v) for v in (day, _("Wohnort"), place, "", *p["genders"])] + [p["total"]]
        )
    for g in data["groups"]:
        for r in g["rows"]:
            if r["total"]:
                writer.writerow(
                    [_csv_cell(v) for v in (day, data["groups_title"], g["name"], r["label"])]
                    + r["counts"]
                    + [r["total"]]
                )
    return ("﻿" + buf.getvalue()).encode("utf-8")


def render_pdf(org, data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    from finance.project_report import _build
    from finance.report import _styles, _table
    from organizations.theme import effective_theme

    st = _styles()
    n, r, rb = st["normal"], st["right"], st["right_bold"]
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    title = _title(data)
    story: list = [
        Paragraph(f"<b>{escape(title)}</b>", st["title"]),
        Paragraph(f"{escape(org.name)} · {escape(_basis(data))}", n),
        Paragraph(
            escape(
                _("{total} Mitglieder, davon {persons} Personen und {orgs} Organisationen").format(
                    total=data["total"], persons=data["persons"], orgs=data["organizations"]
                )
            )
            + " · "
            + escape(_("Stand {date}").format(date=f"{timezone.localdate():%d.%m.%Y}")),
            st["small"],
        ),
        Spacer(1, 4 * mm),
    ]

    def cells(table: list[list], first: int = 1) -> list[list]:
        out = []
        for i, row in enumerate(table):
            bold = i == 0 or (row and row[min(first, len(row)) - 1] == _("Summe"))
            line = []
            for j, v in enumerate(row):
                text = escape(str(v))
                if bold:
                    text = f"<b>{text}</b>"
                line.append(Paragraph(text, n if j < first else (rb if bold else r)))
            out.append(line)
        return out

    def widths(cols: int, first: list[int], total: int = 170) -> list:
        rest = (total - sum(first)) / max(cols - len(first), 1)
        return [w * mm for w in first] + [rest * mm] * (cols - len(first))

    story.append(Paragraph(f"<b>{escape(_('Alter und Geschlecht'))}</b>", st["h2"]))
    table = _age_table(data, data)
    story.append(_table(cells(table), widths(len(table[0]), [45]), primary))

    if data["places"]:
        story.append(Paragraph(f"<b>{escape(_('Wohnorte'))}</b>", st["h2"]))
        places = [row[:2] + row[2:6] + row[-1:] for row in _place_table(data)]
        story.append(
            _table(cells(places, 2), widths(len(places[0]), [55, 35]), primary, total_row=False)
        )
        story.append(
            Paragraph(escape(_("Die Altersgruppen je Ort stehen in der Excel-Datei.")), st["small"])
        )

    for g in data["groups"]:
        story.append(Paragraph(f"<b>{escape(g['name'])}</b>", st["h2"]))
        table = _age_table(data, g)
        story.append(_table(cells(table), widths(len(table[0]), [45]), primary))
    if data["groups"] and data["groups_title"]:
        story.append(
            Paragraph(
                escape(
                    _("Wer mehreren Gruppen ({title}) angehört, zählt in jeder.").format(
                        title=data["groups_title"]
                    )
                ),
                st["small"],
            )
        )
    return _build(org, title, story)
