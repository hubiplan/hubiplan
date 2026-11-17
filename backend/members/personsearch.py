"""Entschlüsselte Namenssuche und stabile Reihenfolgen auf bereits erlaubten Zeilen.

Es werden nur die Such-/Sortierspalten geladen. Das zurückgegebene QuerySet behält
Annotationen, Fachfilter und Beziehungen; seine Reihenfolge enthält nur Zeilen-IDs.
Keine zusätzliche Freigabe von Personen außerhalb der Kandidaten.

Entschlüsselte Namen (Gesamtaudit 15.11., PF-24): Jede Suche entschlüsselte alle Namen der
Einheit neu. Ein kleiner Zwischenspeicher je Prozess hält entschlüsselte Werte für die Suche
(die Sortierung bleibt beim direkten Abruf, dort war er nach Messung nicht schneller),
Schlüssel ist das Chiffrat selbst (mit Feld): Ändert sich ein Name, ändert sich das Chiffrat,
und der alte Eintrag wird nie wieder getroffen. Nur im Arbeitsspeicher, nie in Redis, Logs oder
Fehlermeldungen; feste Obergrenze und Ablaufzeit, damit gelöschte oder anonymisierte Namen nicht
beliebig lange im Prozess liegen (Fachfrage F1 zu Block 6: Namen bleiben verschlüsselt).
"""

from __future__ import annotations

import threading
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Sequence

from django.contrib.postgres.fields import ArrayField
from django.db.models import BigIntegerField, F, Func, IntegerField, TextField, Value
from django.db.models.functions import Cast

from core.encfields import EncryptedMixin

PLAIN_MAX = 50_000
PLAIN_TTL = 10 * 60


class _PlainCache:
    """LRU mit gleitender Ablaufzeit: (Feld, Chiffrat) -> Klartext. Nur im Arbeitsspeicher."""

    def __init__(self, size: int, ttl: float):
        self.size, self.ttl = size, ttl
        self.items: OrderedDict = OrderedDict()
        self.lock = threading.Lock()

    def _prune(self, now: float) -> None:
        """Abgelaufene Einträge vorn entfernen. Die Reihenfolge entspricht der letzten Nutzung,
        die Ablaufzeiten steigen also von vorn nach hinten: Nie mehr getroffene Namen
        (gelöscht, anonymisiert) verlassen den Speicher spätestens beim nächsten Zugriff nach
        ihrem Ablauf, nicht erst, wenn die Obergrenze sie verdrängt."""
        while self.items:
            first = next(iter(self.items.values()))
            if first[0] >= now:
                break
            self.items.popitem(last=False)

    def get(self, key):
        now = time.monotonic()
        with self.lock:
            self._prune(now)
            hit = self.items.get(key)
            if hit is None:
                return None
            if hit[0] < now:
                del self.items[key]
                return None
            # Gleitende Ablaufzeit: benutzte Namen bleiben, nie mehr getroffene (geändert,
            # gelöscht, anonymisiert) fallen nach PLAIN_TTL heraus
            self.items[key] = (now + self.ttl, hit[1])
            self.items.move_to_end(key)
            return hit[1]

    def put(self, key, value) -> None:
        now = time.monotonic()
        with self.lock:
            self._prune(now)
            self.items[key] = (now + self.ttl, value)
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)

    def clear(self) -> None:
        with self.lock:
            self.items.clear()


PLAIN = _PlainCache(PLAIN_MAX, PLAIN_TTL)


def _field(model, path: str):
    """Modellfeld am Ende eines Pfads wie ``person__last_name``; None bei Annotationen."""
    from django.core.exceptions import FieldDoesNotExist

    field = None
    for part in path.split("__"):
        try:
            field = model._meta.get_field(part)
        except FieldDoesNotExist:
            return None
        if field.is_relation:
            model = field.related_model
    return field


def plain_values(qs, *paths: str):
    """Wie ``values_list("pk", *paths)``, verschlüsselte Felder über den Zwischenspeicher.

    Die Datenbank liefert für verschlüsselte Felder das Chiffrat (Cast nach text, ohne
    Entschlüsseln); entschlüsselt wird nur, was noch nicht im Speicher liegt."""
    fields = [_field(qs.model, path) for path in paths]
    secret = [isinstance(f, EncryptedMixin) for f in fields]
    columns = [
        Cast(F(path), output_field=TextField()) if enc else path
        for path, enc in zip(paths, secret, strict=True)
    ]
    for row in qs.order_by().values_list("pk", *columns):
        out = [row[0]]
        for value, field, enc in zip(row[1:], fields, secret, strict=True):
            if enc and value is not None:
                key = (field.model._meta.label_lower, field.attname, value)
                plain = PLAIN.get(key)
                if plain is None:
                    plain = field.decrypt_db_value(value)
                    PLAIN.put(key, plain)
                value = plain
            out.append(value)
        yield tuple(out)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def text_key(value: str) -> tuple[str, str, str]:
    """Grundbuchstaben zuerst, dann Akzente und Schreibweise als feste Tie-Breaks."""
    folded = normalize(value)
    base = "".join(
        char for char in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(char)
    )
    return base, folded, unicodedata.normalize("NFC", value)


def name_ids(qs, word: str, *, fields=("person__last_name", "person__first_name"), exact=False):
    """Zeilen-IDs, bei denen eines der angegebenen Namensfelder das Wort enthält."""
    return name_ids_many(qs, [word], fields=fields, exact=exact)[word]


def name_ids_many(qs, words, *, fields=("person__last_name", "person__first_name"), exact=False):
    """Alle Wörter aus einem Durchlauf der erlaubten Namensspalten auswerten."""
    needles = {word: normalize(word) for word in dict.fromkeys(words)}
    matches = {word: set() for word in needles}
    if not needles:
        return matches
    for row in plain_values(qs, *fields):
        values = [normalize(value) for value in row[1:] if value is not None]
        for word, needle in needles.items():
            if any(needle == value if exact else needle in value for value in values):
                matches[word].add(row[0])
    return matches


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
        for pk, last, first in plain_values(qs, "person__last_name", "person__first_name")
        if all(
            any(needle in normalize(value) for needle in group for value in (last, first))
            for group in needles
        )
    ]
    return qs.filter(pk__in=ids)


class OrderedRows(Sequence):
    """Sortierte Zeilen, die erst beim Seitenschnitt geladen werden.

    Zählen und Blättern laufen über die fertige ID-Liste; nur die Zeilen der Seite gehen
    mit ihrer Position an Postgres. Mit einer Positionsliste aller Treffer wuchs der
    SQL-Aufwand sonst quadratisch mit der Trefferzahl (Gesamtaudit 10.11. P01)."""

    def __init__(self, qs, ids: list[int]):
        self.qs, self.ids = qs, ids

    def __len__(self) -> int:
        return len(self.ids)

    def count(self) -> int:  # Paginator fragt count() vor len()
        return len(self.ids)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(_by_position(self.qs, self.ids[index]))
        return _by_position(self.qs, [self.ids[index]]).get()


def _by_position(qs, ids: list[int]):
    position = Func(
        Value(ids, output_field=ArrayField(BigIntegerField())),
        F("pk"),
        function="array_position",
        output_field=IntegerField(),
    )
    return qs.filter(pk__in=ids).alias(_person_position=position).order_by("_person_position")


def ordered(qs, *ordering, limit=None, lazy=False):
    """In Python sortieren; nur die resultierende ID-Reihenfolge geht an Postgres.

    Unterstützt Feldpfade und F(...).asc/desc(nulls_last/first=True). Ohne explizite
    NULL-Regel gilt wie in Postgres ASC NULLS LAST / DESC NULLS FIRST. Die Zeilen-ID
    bleibt letzter aufsteigender Tie-Break, auch bei absteigenden Fachspalten.
    ``lazy=True`` liefert ``OrderedRows`` für Listen mit Seitenschnitt.
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
    if lazy:
        return OrderedRows(qs, ids)
    return _by_position(qs, ids)
