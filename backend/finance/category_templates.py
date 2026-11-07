"""Vorlagen für Kategorien (Konzept vereinskasse-steuern, S8).

Damit ein neuer Verein nicht bei null anfängt: übliche Kategorien eines Schützen-, Sport- oder
Musikvereins mit steuerlichem Bereich, Spenden- und Künstlerhonorar-Kennzeichen. Eine
Vorlage legt nur fehlende Kategorien an und ändert nie bestehende. DATEV-Konten setzt die
Steuerberatung, weil der Kontenrahmen je Kanzlei abweicht.

Sponsoring: Nennt der Verein den Sponsor nur (ohne Hervorhebung oder Werbeleistung), gehören
die Einnahmen zur Vermögensverwaltung; aktive Werbung (Bande, Anzeige, Trikot) ist
wirtschaftlicher Geschäftsbetrieb.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy

from access.modules import module_on

from .models import Category, TaxArea

IN, OUT, BOTH = Category.Kind.INCOME, Category.Kind.EXPENSE, Category.Kind.BOTH
IDEAL, ASSETS, PURPOSE, BUSINESS = (
    TaxArea.IDEAL,
    TaxArea.ASSETS,
    TaxArea.PURPOSE,
    TaxArea.BUSINESS,
)

# (Name, Art, Bereich, Merkmale) – Merkmale: "donations", "artist_fees"
COMMON = [
    (gettext_lazy("Mitgliedsbeiträge"), IN, IDEAL, ()),
    (gettext_lazy("Aufnahmegebühren"), IN, IDEAL, ()),
    (gettext_lazy("Spenden"), IN, IDEAL, ("donations",)),
    (gettext_lazy("Zuschüsse"), IN, IDEAL, ()),
    (gettext_lazy("Zinsen"), IN, ASSETS, ()),
    (gettext_lazy("Sponsoring (nur Nennung)"), IN, ASSETS, ()),
    (gettext_lazy("Werbeeinnahmen (Bande, Anzeigen)"), IN, BUSINESS, ()),
    (gettext_lazy("Vereinsfest Speisen und Getränke"), BOTH, BUSINESS, ()),
    (gettext_lazy("Verbandsbeiträge"), OUT, IDEAL, ()),
    (gettext_lazy("Versicherungen"), OUT, IDEAL, ()),
    (gettext_lazy("Bankgebühren"), OUT, IDEAL, ()),
    (gettext_lazy("Bürobedarf und Porto"), OUT, IDEAL, ()),
    (gettext_lazy("Ehrungen und Geschenke"), OUT, IDEAL, ()),
    (gettext_lazy("Versammlungen"), OUT, IDEAL, ()),
]

TEMPLATES = {
    "schuetzen": (
        gettext_lazy("Schützenverein"),
        [
            (gettext_lazy("Schützenfest Festzelt"), BOTH, BUSINESS, ()),
            (gettext_lazy("Schützenfest Eintritt"), IN, BUSINESS, ()),
            (gettext_lazy("Musik und Spielmannszüge"), OUT, BUSINESS, ("artist_fees",)),
            (gettext_lazy("Schießsport Munition und Scheiben"), OUT, IDEAL, ()),
            (gettext_lazy("Schießstand"), OUT, IDEAL, ()),
            (gettext_lazy("Orden und Königssilber"), OUT, IDEAL, ()),
            (gettext_lazy("Uniformen und Fahnen"), OUT, IDEAL, ()),
        ],
    ),
    "sport": (
        gettext_lazy("Sportverein"),
        [
            (gettext_lazy("Sportveranstaltungen Eintritt"), IN, PURPOSE, ()),
            (gettext_lazy("Übungsleiter"), OUT, IDEAL, ()),
            (gettext_lazy("Startgelder und Meldegebühren"), OUT, IDEAL, ()),
            (gettext_lazy("Sportgeräte und Trikots"), OUT, IDEAL, ()),
            (gettext_lazy("Hallen- und Platzmiete"), OUT, IDEAL, ()),
            (gettext_lazy("Vereinsheim Bewirtung"), BOTH, BUSINESS, ()),
        ],
    ),
    "musik": (
        gettext_lazy("Musikverein"),
        [
            (gettext_lazy("Konzerte Eintritt"), IN, PURPOSE, ()),
            (gettext_lazy("Auftritte gegen Entgelt"), IN, BUSINESS, ()),
            (gettext_lazy("Dirigent und Ausbilder"), OUT, IDEAL, ("artist_fees",)),
            (gettext_lazy("Noten und Instrumente"), OUT, IDEAL, ()),
            (gettext_lazy("Probenraum"), OUT, IDEAL, ()),
            (gettext_lazy("Trachten und Uniformen"), OUT, IDEAL, ()),
        ],
    ),
}


def _rows(key: str):
    return COMMON + TEMPLATES[key][1]


def listing(org) -> list[dict]:
    existing = {
        n.casefold()
        for n in Category.objects.filter(organization=org).values_list("name", flat=True)
    }
    out = []
    for key, (label, _) in TEMPLATES.items():
        cats = []
        for name, kind, area, flags in _rows(key):
            text = str(name)
            cats.append(
                {
                    "name": text,
                    "kind": kind,
                    "kind_label": str(Category.Kind(kind).label),
                    "tax_area": area,
                    "tax_area_label": str(TaxArea(area).label),
                    "donations": "donations" in flags,
                    "artist_fees": "artist_fees" in flags,
                    "exists": text.casefold() in existing,
                }
            )
        out.append({"key": key, "label": str(label), "categories": cats})
    return out


def apply(org, key: str) -> list[Category]:
    """Legt die fehlenden Kategorien der Vorlage an; bestehende bleiben unverändert."""
    if key not in TEMPLATES:
        raise KeyError(key)
    existing = {
        n.casefold()
        for n in Category.objects.filter(organization=org).values_list("name", flat=True)
    }
    artists = module_on(org, "tax")
    created = []
    for name, kind, area, flags in _rows(key):
        text = str(name)
        if text.casefold() in existing:
            continue
        created.append(
            Category.objects.create(
                organization=org,
                name=text,
                kind=kind,
                tax_area=area,
                donations="donations" in flags,
                artist_fees=artists and "artist_fees" in flags,
            )
        )
        existing.add(text.casefold())
    return created
