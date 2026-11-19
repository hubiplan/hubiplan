# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Infoschreiben an Angemeldete (konzepte/veranstaltungen-anmeldung-gebuehr.md, Stufe A5):
Rundschreiben zum Termin an die Anmeldungen, auch an Gäste ohne Mitgliedschaft, mit Ablauf,
Platzhaltern je Anmeldung und Nachzüglern. Alle Daten erfunden."""

import pytest
from django.core import mail

from circulars.models import Circular, CircularRecipient
from core.tenancy import tenant_context

from .test_anmeldungen import JSON, einrichten, fest, ok  # noqa: F401
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db


def test_infoschreiben_an_angemeldete_und_nachzuegler(
    c, fest, club, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    ok(
        c.patch(
            f"{fest['org']}/events/{fest['event']['id']}/",
            {"programme": "10:00 Treffen am Bahnhof\n12:00 Mittagessen"},
            content_type=JSON,
        )
    )
    einrichten(c, fest)
    client, url = fest["portals"]["Bernd"]
    adult, _kids, guests = (
        p["id"] for p in ok(client.get(f"{url}registration/"))["offer"]["prices"]
    )
    ok(
        client.post(
            f"{url}registration/",
            {"persons": [{"membership_id": fest["bernd"].pk, "price_id": adult}]},
            content_type=JSON,
        )
    )
    ok(
        c.post(
            f"{fest['url']}list/",
            {
                "name": "Greta Gast",
                "email": "greta@example.org",
                "persons": [{"name": "Greta Gast", "price_id": guests}],
            },
            content_type=JSON,
        )
    )
    circulars = f"{fest['org']}/circulars/"
    draft = ok(c.post(f"{circulars}from-event/{fest['event']['id']}/", content_type=JSON))
    assert draft["audience"] == "registered"
    assert "10:00 Treffen am Bahnhof" in draft["body"]
    body = draft["body"] + "\n\nAngemeldet: {Personen}, offen: {Offener Betrag} ({Anmeldenummer})"
    ok(c.patch(f"{circulars}{draft['id']}/", {"body": body}, content_type=JSON))
    preview = ok(c.get(f"{circulars}{draft['id']}/recipients/"))
    names = sorted(f"{r['first_name']} {r['last_name']}".strip() for r in preview["items"])
    assert names == ["Bernd Beispiel", "Greta Gast"]
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        ok(c.post(f"{circulars}{draft['id']}/send/", content_type=JSON))
    to = sorted(m.to[0] for m in mail.outbox if m.subject.startswith("Informationen:"))
    assert to == ["bernd@example.org", "greta@example.org"]
    greta = next(m for m in mail.outbox if m.to == ["greta@example.org"])
    assert "Greta Gast (Gäste)" in greta.body and "40,00" in greta.body
    with tenant_context(club.pk):
        assert CircularRecipient.objects.filter(registration__isnull=False).count() == 2
    # Spätere Anmeldung bekommt das Infoschreiben mit
    client, url = fest["portals"]["Anna"]
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        ok(
            client.post(
                f"{url}registration/",
                {"persons": [{"membership_id": fest["anna"].pk, "price_id": adult}]},
                content_type=JSON,
            )
        )
    subjects = [m.subject for m in mail.outbox if m.to == ["anna@example.org"]]
    assert any(s.startswith("Anmeldebestätigung") for s in subjects)
    assert any(s.startswith("Informationen:") for s in subjects)
    with tenant_context(club.pk):
        assert CircularRecipient.objects.filter(registration__isnull=False).count() == 3
        assert Circular.objects.get(pk=draft["id"]).status == "sent"


def test_infoschreiben_nur_warteliste_und_ohne_nachzuegler(
    c, fest, club, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    einrichten(c, fest, capacity=1, waitlist=True)
    client, url = fest["portals"]["Bernd"]
    adult = ok(client.get(f"{url}registration/"))["offer"]["prices"][0]["id"]
    for who in ("Bernd", "Anna"):
        client, url = fest["portals"][who]
        ok(
            client.post(
                f"{url}registration/",
                {"persons": [{"membership_id": fest[who.lower()].pk, "price_id": adult}]},
                content_type=JSON,
            )
        )
    circulars = f"{fest['org']}/circulars/"
    draft = ok(c.post(f"{circulars}from-event/{fest['event']['id']}/", content_type=JSON))
    ok(
        c.patch(
            f"{circulars}{draft['id']}/",
            {"filters": {"registration_states": ["waiting"], "latecomers": False}},
            content_type=JSON,
        )
    )
    preview = ok(c.get(f"{circulars}{draft['id']}/recipients/"))
    assert [r["first_name"] for r in preview["items"]] == ["Anna"]
    # Ein normales Rundschreiben kann nicht auf „Angemeldete“ umgestellt werden
    other = ok(c.post(circulars, {"subject": "Hallo", "audience": "registered"}, content_type=JSON))
    assert other["audience"] == "members"
