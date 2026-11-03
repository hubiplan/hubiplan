"""Entschlüsselte Namenssuche und stabile Reihenfolgen auf bereits erlaubten Zeilen.

Es werden nur die Such-/Sortierspalten geladen. Das zurückgegebene QuerySet behält
Annotationen, Fachfilter und Beziehungen; seine Reihenfolge enthält nur Zeilen-IDs.
Kein Cache und keine zusätzliche Freigabe von Personen außerhalb der Kandidaten.
"""

from __future__ import annotations

import unicodedata

from django.contrib.postgres.fields import ArrayField
from django.db.models import BigIntegerField, F, Func, IntegerField, Value


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def text_key(value: str) -> tuple[str, str, str]:
    """Grundbuchstaben zuerst, dann Akzente und Schreibweise als feste Tie-Breaks."""
    folded = normalize(value)
    base = "".join(
        char for char in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(char)
    )
    return base, folded, unicodedata.normalize("NFC", value)


def name_ids(qs, word: str, *, fields=("person__last_name", "person__first_name")):
    """Zeilen-IDs, bei denen eines der angegebenen Namensfelder das Wort enthält."""
    needle = normalize(word)
    return {
        row[0]
        for row in qs.order_by().values_list("pk", *fields)
        if any(needle in normalize(value) for value in row[1:] if value is not None)
    }


def filter_names(qs, search: str, *, variants=None, max_words=3):
    """UND zwischen Wörtern, ODER zwischen Namen und optionalen Umlautvarianten."""
    words = search.split()[:max_words]
    if not words:
        return qs
    needles = [
        {normalize(v) for v in variants(word)} if variants else {normalize(word)} for word in words
    ]
    ids = [
        pk
        for pk, last, first in qs.order_by().values_list(
            "pk", "person__last_name", "person__first_name"
        )
        if all(
            any(needle in normalize(value) for needle in group for value in (last, first))
            for group in needles
        )
    ]
    return qs.filter(pk__in=ids)


def ordered(qs, *ordering, limit=None):
    """In Python sortieren; nur die resultierende ID-Reihenfolge geht an Postgres.

    Unterstützt Feldpfade und F(...).asc/desc(nulls_last/first=True). Ohne explizite
    NULL-Regel gilt wie in Postgres ASC NULLS LAST / DESC NULLS FIRST. Die Zeilen-ID
    bleibt letzter aufsteigender Tie-Break, auch bei absteigenden Fachspalten.
    """
    if qs.query.is_sliced:
        raise ValueError("Personensortierung muss vor dem Seitenschnitt erfolgen.")
    if not ordering:
        ordering = ("person__last_name", "person__first_name")
    terms = []
    for term in ordering:
        if isinstance(term, str):
            desc = term.startswith("-")
            field = term.removeprefix("-")
            nulls_first = desc
        else:
            field = term.expression.name
            desc = term.descending
            nulls_first = bool(term.nulls_first or (desc and not term.nulls_last))
        terms.append((field, desc, nulls_first))
    rows = list(qs.order_by().values_list("pk", *(field for field, _, _ in terms)))
    # DISTINCT mit Beziehungen darf dieselbe Eingangszeile nicht vervielfachen.
    rows = list({row[0]: row for row in rows}.values())
    rows.sort(key=lambda row: row[0])
    for index in reversed(range(len(terms))):
        _, desc, nulls_first = terms[index]
        known = [row for row in rows if row[index + 1] is not None]
        missing = [row for row in rows if row[index + 1] is None]
        known.sort(
            key=lambda row, i=index: (
                text_key(row[i + 1]) if isinstance(row[i + 1], str) else row[i + 1]
            ),
            reverse=desc,
        )
        rows = missing + known if nulls_first else known + missing
    ids = [row[0] for row in rows]
    if limit is not None:
        ids = ids[:limit]
    position = Func(
        Value(ids, output_field=ArrayField(BigIntegerField())),
        F("pk"),
        function="array_position",
        output_field=IntegerField(),
    )
    return qs.filter(pk__in=ids).alias(_person_position=position).order_by("_person_position")
