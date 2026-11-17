"""Online-Antrag: Grenze je Empfängeradresse, Stand-Modus nur bei aktivem Verein und ohne
freie Angaben in der Mail (Gesamtaudit 15.11., PUB-05, PUB-06). Erfundene Daten."""

import pytest
from django.core import mail
from django.test import Client

from admission.models import KioskLink

from .test_mitgliedsantrag import club, leichte_aufgabe, submit  # noqa: F401

# Wie test_mitgliedsantrag: Antrag und Mails erst nach dem Commit
pytestmark = pytest.mark.django_db(transaction=True)


def test_hoechstens_drei_bestaetigungsmails_je_adresse(club):  # noqa: F811
    mail.outbox.clear()
    # Wie ein Angreifer: je Antrag andere Namen, gleiche Empfängeradresse
    antworten = [
        submit(club["key"], last_name=f"Muster-{n}", first_name=n)
        for n in ("Anna", "Bert", "Clara", "Dieter", "Emil")
    ]
    assert {r.status_code for r in antworten} == {201}, [r.content for r in antworten]
    assert len({frozenset(r.json()) for r in antworten}) == 1  # Antwort immer gleich
    an = [m for m in mail.outbox if "max.muster@example.org" in m.to]
    assert len(an) == 3


def _kiosk(club):  # noqa: F811
    org = club["org"]
    res = club["client"].post(
        f"/api/orgs/{org.pk}/admission/kiosk/", {"label": "Stand", "hours": 8}, "application/json"
    )
    assert res.status_code == 201, res.content
    return res.json()["url"].rsplit("/", 1)[1]


def _stand(token, data, note="Bitte Rückruf unter 0151 000000"):
    return Client().post(
        f"/api/public/join/kiosk/{token}/",
        {
            "member_type": data["types"][0]["id"],
            "last_name": "Stand",
            "first_name": "Sina",
            "email": "sina@example.org",
            "street": "Platz 1",
            "postal_code": "12345",
            "city": "Musterstadt",
            "adult": "yes",
            "note": note,
            "confirmations": ["privacy"],
        },
        "application/json",
    )


def test_stand_mail_ohne_angaben(club):  # noqa: F811
    token = _kiosk(club)
    data = Client().get(f"/api/public/join/kiosk/{token}/").json()
    mail.outbox.clear()
    assert _stand(token, data).status_code == 201
    sent = [m for m in mail.outbox if "sina@example.org" in m.to]
    assert sent and all("Rückruf" not in m.body and "Platz 1" not in m.body for m in sent)


def test_stand_nur_bei_aktivem_verein(club):  # noqa: F811
    token = _kiosk(club)
    org = club["org"]
    org.is_active = False
    org.save()
    assert Client().get(f"/api/public/join/kiosk/{token}/").status_code == 404
    assert KioskLink.objects.filter(organization=org).exists()
