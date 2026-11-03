"""Versionierte, bereichsgebundene Suchmarken für Namen zusammen mit Datum/Jahr.

Version 1 erhält bewusst PostgreSQLs bisherige iexact-Normalisierung (UPPER,
Datenbank-Locale), statt Unicode-casefold als neue Zuordnungsregel einzuführen.
Die Normalisierung persistiert keine Namen; auch entschlüsselte Kandidaten werden
damit abschließend geprüft. SQL-Parameter können wie bisher Namen enthalten.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.db import connections
from django.db.models import Q

from core import crypto

VERSION = 1
MARK_FIELDS = ("last_birth_mark", "first_birth_mark", "last_year_mark", "first_year_mark")
DERIVED_FIELDS = (*MARK_FIELDS, "marks_version", "marks_key_id")
IDENTITY_FIELDS = {"scope", "scope_id", "last_name", "first_name", "birth_date", "birth_year_only"}


def names(last_name, first_name, *, using="default"):
    """Dieselbe Großschreibung wie bisherige iexact-Abfragen; gespeicherte Namen
    NICHT trimmen. Nur die Suchangaben werden von den Aufrufern getrimmt."""
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT UPPER(%s::text), UPPER(%s::text)", [last_name, first_name])
        return cursor.fetchone()


def _mark(raw_key, scope_id, purpose, name, date):
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"hubiplan/personmarks/{VERSION}/{scope_id}/{purpose}".encode("ascii"),
    ).derive(raw_key)
    payload = json.dumps([name, date], ensure_ascii=False, separators=(",", ":")).encode()
    digest = hmac.digest(key, payload, hashlib.sha256)[:16]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def values(person, *, using="default"):
    birth = person._meta.get_field("birth_date").to_python(person.birth_date)
    if birth is None:
        raise ValueError("Geburtsdatum nicht lesbar; Suchmarken nicht berechnet.")
    key_id, raw_key = crypto.key_for_org(person.scope_id)
    last, first = names(person.last_name, person.first_name, using=using)
    day = birth.isoformat()
    year = str(birth.year)
    result = {"marks_version": VERSION, "marks_key_id": key_id}
    for field, name, date in (
        ("last_birth_mark", last, day),
        ("first_birth_mark", first, day),
        ("last_year_mark", last, year),
        ("first_year_mark", first, year),
    ):
        result[field] = (
            _mark(raw_key, person.scope_id, field, name, date)
            if "year" not in field or person.birth_year_only
            else ""
        )
    return result


def write(person, *, using="default"):
    """Nur unter derselben Zeilensperre/Transaktion wie die Identitätsänderung.
    Abgeleitete Werte gehören nicht in Änderungsprotokoll oder Rückgängig-Pakete."""
    result = values(person, using=using)
    columns = ", ".join(f'"{field}" = %s' for field in result)
    with connections[using].cursor() as cursor:
        cursor.execute(
            f"UPDATE members_person SET {columns} WHERE id = %s",  # noqa: S608
            [*result.values(), person.pk],
        )
    for field, value in result.items():
        setattr(person, field, value)


def candidates(scope_id, last_name, first_name, birth_date, *, strict):
    from .models import Person

    if birth_date is None:
        return Person.objects.none()
    key_id, raw_key = crypto.key_for_org(scope_id)
    last, first = names(last_name, first_name)
    day, year = birth_date.isoformat(), str(birth_date.year)
    last_day = Q(last_birth_mark=_mark(raw_key, scope_id, "last_birth_mark", last, day))
    first_day = Q(first_birth_mark=_mark(raw_key, scope_id, "first_birth_mark", first, day))
    match = last_day & first_day if strict else last_day | first_day
    if not strict:
        match |= Q(birth_year_only=True) & (
            Q(last_year_mark=_mark(raw_key, scope_id, "last_year_mark", last, year))
            | Q(first_year_mark=_mark(raw_key, scope_id, "first_year_mark", first, year))
        )
    # Fehlender Bestand, ältere Writer und Schlüssel-/Formatwechsel: niemals
    # Personen verlieren. Der geprüfte Bestandslauf beseitigt diesen Übergang.
    pending = (
        ~Q(marks_version=VERSION)
        | Q(marks_key_id__isnull=True)
        | ~Q(marks_key_id=key_id)
        | Q(last_birth_mark="")
        | Q(first_birth_mark="")
        | (Q(birth_year_only=True) & (Q(last_year_mark="") | Q(first_year_mark="")))
    )
    return Person.objects.filter(scope_id=scope_id).filter(match | pending)


def verified(person, last_name, first_name, birth_date, *, strict):
    from .services import same_birth

    wanted = names(last_name, first_name)
    actual = names(person.last_name, person.first_name)
    equal = (actual[0] == wanted[0], actual[1] == wanted[1])
    return (all(equal) if strict else any(equal)) and same_birth(
        person,
        birth_date,
        year_only=not strict,
    )
