"""Feste Instrumentenliste je Einheit: Vorbelegung und Abgleich (konzepte/instrumente.md).

Fähigkeiten, Sollbesetzung, Besetzungsvorlagen, Notenstimmen und Material speichern weiter den
Namen des Instruments. Diese Liste sorgt dafür, dass überall dieselbe Schreibweise steht:
Eingaben werden auf den Listeneintrag gebracht („trompete“ → „Trompete“, „Saxophon“ und
„Saxofon“ gleich), Unbekanntes kommt als neuer Eintrag dazu.
"""

import re
from collections import Counter

from django.db.models import Max
from django.utils.translation import gettext, gettext_noop
from rest_framework import serializers

from core.i18n import language_of_org

from .models import EnsembleTemplatePosition, Equipment, Instrument, Position, ScorePart, Skill

# Umfassende Auswahl für Blaskapellen, Spielleute und Weiteres (Anhang des Konzepts)
DEFAULT_INSTRUMENTS = [
    (
        "wood",
        [
            gettext_noop("Piccoloflöte"),
            gettext_noop("Querflöte"),
            gettext_noop("Altflöte"),
            gettext_noop("Oboe"),
            gettext_noop("Englischhorn"),
            gettext_noop("Fagott"),
            gettext_noop("Es-Klarinette"),
            gettext_noop("Klarinette"),
            gettext_noop("Altklarinette"),
            gettext_noop("Bassklarinette"),
            gettext_noop("Kontrabassklarinette"),
            gettext_noop("Sopransaxofon"),
            gettext_noop("Altsaxofon"),
            gettext_noop("Tenorsaxofon"),
            gettext_noop("Baritonsaxofon"),
            gettext_noop("Basssaxofon"),
        ],
    ),
    (
        "brass",
        [
            gettext_noop("Piccolotrompete"),
            gettext_noop("Trompete"),
            gettext_noop("Kornett"),
            gettext_noop("Flügelhorn"),
            gettext_noop("Horn"),
            gettext_noop("Tenorhorn"),
            gettext_noop("Bariton"),
            gettext_noop("Euphonium"),
            gettext_noop("Posaune"),
            gettext_noop("Bassposaune"),
            gettext_noop("Es-Tuba"),
            gettext_noop("B-Tuba"),
            gettext_noop("Sousafon"),
        ],
    ),
    (
        "percussion",
        [
            gettext_noop("Schlagzeug"),
            gettext_noop("Kleine Trommel"),
            gettext_noop("Große Trommel"),
            gettext_noop("Becken"),
            gettext_noop("Pauken"),
            gettext_noop("Lyra"),
            gettext_noop("Glockenspiel"),
            gettext_noop("Xylofon"),
            gettext_noop("Vibrafon"),
            gettext_noop("Marimbafon"),
            gettext_noop("Röhrenglocken"),
            gettext_noop("Kleinpercussion"),
        ],
    ),
    (
        "corps",
        [
            gettext_noop("Spielmannsflöte (Sopran)"),
            gettext_noop("Spielmannsflöte (Alt)"),
            gettext_noop("Spielmannsflöte (Tenor)"),
            gettext_noop("Marschtrommel"),
            gettext_noop("Landsknechtstrommel"),
            gettext_noop("Fanfare"),
            gettext_noop("Signalhorn"),
            gettext_noop("Schellenbaum"),
        ],
    ),
    (
        "other",
        [
            gettext_noop("Kontrabass"),
            gettext_noop("E-Bass"),
            gettext_noop("Gitarre"),
            gettext_noop("Keyboard"),
            gettext_noop("Klavier"),
            gettext_noop("Harfe"),
            gettext_noop("Gesang"),
        ],
    ),
]

# Häufige andere Namen für Einträge der Vorbelegung (Schlüssel wie key())
ALIASES = {"waldhorn": "horn", "drumset": "schlagzeug"}

USERS = (Skill, Position, EnsembleTemplatePosition, ScorePart, Equipment)


def key(name: str) -> str:
    """Vergleichsschlüssel: Groß-/Kleinschreibung, Umlaute, ph/f, Leer- und Bindestriche egal."""
    text = (name or "").strip().casefold()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("ph", "f")):
        text = text.replace(a, b)
    return re.sub(r"[^0-9a-z()]+", "", text)


def ensure_defaults(org, model=Instrument):
    """Legt die Vorbelegung einmal an, solange die Einheit noch gar keine Instrumente hat."""
    if model.objects.filter(organization=org).exists():
        return
    position = 0
    with language_of_org(org):
        for group, names in DEFAULT_INSTRUMENTS:
            for name in names:
                position += 1
                model.objects.get_or_create(
                    organization=org,
                    name=gettext(name),
                    defaults={"group": group, "position": position},
                )


def lookup(org, model=Instrument) -> dict:
    """Schlüssel → Listeneintrag der Einheit, samt Aliassen auf die Vorbelegung."""
    rows = {key(i.name): i for i in model.objects.filter(organization=org)}
    for alias, target in ALIASES.items():
        if alias not in rows and target in rows:
            rows[alias] = rows[target]
    return rows


def canonical(org, name: str, model=Instrument, create=True) -> str:
    """Name aus der Liste der Einheit; Unbekanntes wird (mit create) als neuer Eintrag angelegt."""
    name = (name or "").strip()
    if not name or org is None:
        return name
    if create:
        ensure_defaults(org, model)
    found = lookup(org, model).get(key(name))
    if found:
        return found.name
    if not create:
        return name
    if name == name.lower():
        name = name[:1].upper() + name[1:]
    last = model.objects.filter(organization=org).aggregate(m=Max("position"))["m"] or 0
    created, _ = model.objects.get_or_create(
        organization=org,
        name=name,
        defaults={"group": "other", "position": min(last + 1, 32767)},
    )
    return created.name


def usage(org) -> Counter:
    """Wie oft jeder Name verwendet wird (nach Schlüssel)."""
    counts = Counter()
    for model in USERS:
        for name in model.objects.filter(organization=org).values_list("instrument", flat=True):
            if name:
                counts[key(name)] += 1
    return counts


class InstrumentField(serializers.CharField):
    """Eingabefeld „Instrument“: bringt die Eingabe gleich auf den Listeneintrag.

    Neue Einträge legt erst das Speichern an (Signal in models.py), damit eine abgelehnte
    Eingabe keine Spuren in der Liste hinterlässt.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 100)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        org = getattr(self.context.get("view"), "org", None) if self.context else None
        if not value or org is None:
            return value
        return canonical(org, value, create=False)
