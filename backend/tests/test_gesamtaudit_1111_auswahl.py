"""Gesamtaudit 11.11.2026, P-04: Auswahllisten laden nicht mehr alle Mitglieder."""
# ruff: noqa: F811

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from .factories import make_member
from .test_music import c, club, music  # noqa: F401

pytestmark = pytest.mark.django_db


def test_musik_auswahl_ohne_mitgliederliste(c, club, music):
    make_member(club, "Anna", "Muster")
    with CaptureQueriesContext(connection) as queries:
        response = c.get(f"{music[0]}/musicians/choices/")
    assert response.status_code == 200, response.content
    assert set(response.json()) == {"events", "partners"}
    assert not any('FROM "members_person"' in q["sql"] for q in queries)
