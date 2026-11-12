"""Titel (Dr., Prof. …): Eingaben erkennen und Werte aus einem Zusatzfeld „Titel“ übernehmen."""

from __future__ import annotations

import re
from collections import defaultdict

from .models import TITLE_MAX_LENGTH, Title

# Verglichen wird klein, ohne Punkte und Leerzeichen („Prof. Dr.“, „prof.dr“, „ProfDr“).
# Genauere Angaben wie „Dr. med.“ bleiben, wie sie eingegeben wurden.
ALIASES = {
    Title.DR: {"dr", "doktor"},
    Title.DR_DR: {"drdr", "doktordoktor"},
    Title.PROF: {"prof", "professor", "professorin"},
    Title.PROF_DR: {"profdr", "professordoktor"},
}
EMPTY = {"", "-", "–", "ka", "keineangabe", "kein", "keiner", "ohne"}


def parse_title(value) -> str:
    """Titel in der üblichen Schreibweise („dr“ → „Dr.“, „Professor“ → „Prof.“).

    Unbekannte Titel bleiben, wie sie eingegeben wurden (das Feld ist frei, die
    Auswahlliste schlägt nur vor); leer = kein Titel."""
    raw = " ".join(str(value or "").split())
    text = re.sub(r"[\s.\-]", "", raw.lower())
    if text in EMPTY:
        return ""
    for title, names in ALIASES.items():
        if text in names:
            return str(title)
    return raw[:TITLE_MAX_LENGTH]


def take_over_field(person_model, definition_model, value_model) -> int:
    """Übernimmt Werte aus Zusatzfeldern mit der Bezeichnung „Titel“.

    Wie beim Geschlecht (members.gender): nur Personen ohne eigenen Titel, das
    Zusatzfeld bleibt, widersprüchliche Werte derselben Person bleiben leer.
    Gibt die Zahl der gesetzten Personen zurück."""
    definitions = definition_model.objects.filter(
        label__iexact="Titel", repeatable=False
    ).values_list("pk", flat=True)
    found: dict[int, set[str]] = defaultdict(set)
    for person_id, value in value_model.objects.filter(
        definition_id__in=list(definitions), person__title="", person__kind="person"
    ).values_list("person_id", "value"):
        if title := parse_title(value):
            found[person_id].add(title)
    changed = 0
    for person_id, titles in found.items():
        if len(titles) == 1:
            changed += person_model.objects.filter(pk=person_id, title="").update(
                title=titles.pop()
            )
    return changed
