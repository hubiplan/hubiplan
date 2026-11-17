"""Auskunft (Art. 15) unter dem Zeilenschutz: Kontodaten des Mitglieds sind vollständig.

Gesamtaudit 15.11., AZ-04: Die Anfrage läuft im Betrieb unter der Rolle der Anwendung mit dem
Konto des Vorstands. Tabellen, die je Konto geschützt sind (Unterschrift, Aufgaben, Nextcloud,
KI-Assistenten, Briefbogen, Erinnerungen) und Qualifikationen aus Untereinheiten fehlten daher in
der Auskunft. Geprüft wird auch, dass nichts einer anderen Person und nichts aus einem fremden
Verein hineinkommt. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
import io
import json
import zipfile

import pytest
from django.utils import timezone

from accounts.models import StoredSignature
from core.tenancy import rls_bypass
from letterhead.models import LetterheadChoice
from mcpserver.models import McpClient, McpGrant
from members.models import Membership
from music.models import MusicReminderPreference
from oidc.models import Account, Client
from portal.models import PortalAccess
from qualifications.models import Qualification, QualificationType
from todos.models import (
    Todo,
    TodoNotice,
    TodoPreference,
    TodoReminder,
    TodoReminderConfig,
    TodoShare,
)

from .factories import make_member, make_org, make_user
from .test_m3_workflows import member, types, url  # noqa: F401

# Anfragen wie im Betrieb unter dem Zeilenschutz (Gesamtaudit 15.11., AZ-04)
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anfragen_unter_app_rolle")]

ERIKA_UNTERSCHRIFT = datetime.datetime(2025, 2, 3, 10, 0, tzinfo=datetime.UTC)
MAX_UNTERSCHRIFT = datetime.datetime(2001, 1, 1, 8, 0, tzinfo=datetime.UTC)


def _grant(user, org, client, mark: str) -> McpGrant:
    now = timezone.now()
    return McpGrant.objects.create(
        user=user,
        organization=org,
        client=client,
        scopes=["webseite.lesen"],
        access_hash=mark * 64,
        access_expires_at=now + datetime.timedelta(hours=1),
        refresh_hash=mark.upper() * 64,
        expires_at=now + datetime.timedelta(days=30),
    )


def _cloud(org, name: str) -> Client:
    return Client.objects.create(
        organization=org,
        name=name,
        base_url="https://cloud.example.org",
        secret_hash="f" * 64,
    )


def _erinnerungen(org, todo, user, days: list[int]) -> None:
    """Erinnerungseinstellung, geplante Erinnerung und Hinweis für eine Aufgabe."""
    TodoReminderConfig.objects.create(organization=org, todo=todo, user=user, days=days)
    TodoReminder.objects.create(
        organization=org,
        todo=todo,
        user=user,
        due_revision=1,
        config_revision=1,
        rule="1d",
        channel="mail",
        scheduled_at=timezone.now() + datetime.timedelta(days=1),
    )
    TodoNotice.objects.create(organization=org, todo=todo, user=user, revision=1)


def _qualifikation(org, person, name: str) -> None:
    kind = QualificationType.objects.create(organization=org, name=name)
    Qualification.objects.create(
        organization=org, person=person, kind=kind, acquired_on=datetime.date(2023, 5, 1)
    )


@pytest.fixture
def bestand(orgs, member):
    """Erika (Verein A) mit je einer Zeile in jedem geschützten Teil; dazu Max Beispiel
    (ebenfalls Verein A, eigenes Konto) und Zeilen von Erikas Konto in Verein B."""
    club, fremd = orgs["a"], orgs["b"]
    unit = make_org("Jugendabteilung Auskunft", "unit", parent=club)
    erika = make_user("erika.rls@example.org", first_name="Erika", last_name="Muster")
    teiler = make_user("hans.teiler@example.org", first_name="Hans", last_name="Teiler")
    maxi = make_user("max.beispiel@example.org", first_name="Max", last_name="Beispiel")
    with rls_bypass():
        m = Membership.objects.get(pk=member["id"])
    m_max = make_member(club, "Max", "Beispiel", email="max.beispiel@example.org")

    with rls_bypass():
        PortalAccess.objects.create(organization=club, membership=m, user=erika)
        PortalAccess.objects.create(organization=club, membership=m_max, user=maxi)

        # --- Erika, Verein A (und Untereinheit) ---
        StoredSignature.objects.create(user=erika, strokes=[[[0, 0], [1, 1]]])
        eigene = Todo.objects.create(
            organization=club, title="Erikas Vereinsaufgabe", owner=erika, shared=True
        )
        geteilt = Todo.objects.create(
            organization=club, title="Geteilt an Erika", owner=teiler, shared=True
        )
        TodoShare.objects.create(organization=club, todo=geteilt, user=erika, target_org=club)
        Account.objects.create(
            organization=club,
            client=_cloud(club, "Vereinswolke A"),
            user=erika,
            nc_user="erika.muster",
            last_login_at=timezone.now(),
        )
        _grant(erika, club, McpClient.objects.create(name="Assistent Erika A"), "a")
        LetterheadChoice.objects.create(
            user=erika, unit=club, context=f"org:{club.pk}", function_text="Schriftführerin A"
        )
        TodoPreference.objects.create(user=erika, push_title=False)
        _erinnerungen(club, eigene, erika, [3])
        MusicReminderPreference.objects.create(
            organization=club, user=erika, enabled=True, days_ahead=5
        )
        _qualifikation(unit, m.person, "Jugendleiterin Erika")

        # --- Max Beispiel, ebenfalls Verein A ---
        StoredSignature.objects.create(user=maxi, strokes=[[[7, 7], [8, 8]]])
        max_todo = Todo.objects.create(
            organization=club, title="Aufgabe von Max", owner=maxi, shared=True
        )
        TodoShare.objects.create(organization=club, todo=geteilt, user=maxi, target_org=club)
        Account.objects.create(
            organization=club,
            client=Client.objects.get(organization=club),
            user=maxi,
            nc_user="max.beispiel",
            last_login_at=timezone.now(),
        )
        _grant(maxi, club, McpClient.objects.create(name="Assistent von Max"), "m")
        LetterheadChoice.objects.create(
            user=maxi, unit=club, context=f"org:{club.pk}", function_text="Kassierer Max"
        )
        TodoPreference.objects.create(user=maxi, push_title=True)
        _erinnerungen(club, max_todo, maxi, [8])
        MusicReminderPreference.objects.create(
            organization=club, user=maxi, enabled=True, days_ahead=13
        )
        _qualifikation(club, m_max.person, "Sanitäter Max")

        # --- Erikas Konto in Verein B (fremder Verein) ---
        fremde = Todo.objects.create(
            organization=fremd, title="Erikas Aufgabe in B", owner=erika, shared=True
        )
        fremd_geteilt = Todo.objects.create(
            organization=fremd, title="Geteilt in Verein B", owner=teiler, shared=True
        )
        TodoShare.objects.create(
            organization=fremd, todo=fremd_geteilt, user=erika, target_org=fremd
        )
        Account.objects.create(
            organization=fremd,
            client=_cloud(fremd, "Wolke Verein B"),
            user=erika,
            nc_user="erika.verein-b",
            last_login_at=timezone.now(),
        )
        _grant(erika, fremd, McpClient.objects.create(name="Fremder Assistent B"), "b")
        LetterheadChoice.objects.create(
            user=erika, unit=fremd, context=f"org:{fremd.pk}", function_text="Fremde Funktion B"
        )
        _erinnerungen(fremd, fremde, erika, [9])
        MusicReminderPreference.objects.create(
            organization=fremd, user=erika, enabled=True, days_ahead=11
        )
        _qualifikation(fremd, m.person, "Übungsleiter Verein B")

    StoredSignature.objects.filter(user=erika).update(updated_at=ERIKA_UNTERSCHRIFT)
    StoredSignature.objects.filter(user=maxi).update(updated_at=MAX_UNTERSCHRIFT)
    return {"erika": erika, "max": maxi, "fremd": fremd}


def _auskunft(c, orgs, member) -> tuple[dict, list, bytes]:
    resp = c.get(url(orgs, member, "auskunft/"))
    assert resp.status_code == 200, resp.content[:300]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    everything = b"".join(zf.read(n) for n in zf.namelist())
    [konto] = json.loads(zf.read("konto.json"))
    return konto, json.loads(zf.read("qualifikationen.json")), everything


TEILE = [
    ("unterschrift", lambda k, q: k["gespeicherte_unterschrift"]["vorhanden"], True),
    (
        "eigene_aufgaben",
        lambda k, q: [t["titel"] for t in k["aufgaben"]["eigene"]],
        ["Erikas Vereinsaufgabe"],
    ),
    (
        "mit_dir_geteilt",
        lambda k, q: [t["titel"] for t in k["aufgaben"]["mit_dir_geteilt"]],
        ["Geteilt an Erika"],
    ),
    ("freigaben", lambda k, q: k["aufgaben"]["freigaben"], 1),
    (
        "nextcloud",
        lambda k, q: [(a["dienst"], a["benutzername"]) for a in k["nextcloud"]],
        [("Vereinswolke A", "erika.muster")],
    ),
    (
        "ki_assistenten",
        lambda k, q: [g["assistent"] for g in k["ki_assistenten"]],
        ["Assistent Erika A"],
    ),
    (
        "briefbogen",
        lambda k, q: [b["function_text"] for b in k["briefbogen"]],
        ["Schriftführerin A"],
    ),
    (
        "aufgaben_einstellungen",
        lambda k, q: [p["push_title"] for p in k["aufgaben"]["einstellungen"]],
        [False],
    ),
    (
        "erinnerungen",
        lambda k, q: [r["days"] for r in k["aufgaben"]["erinnerungen"]],
        [[3]],
    ),
    ("geplante_erinnerungen", lambda k, q: k["aufgaben"]["geplante_erinnerungen"], 1),
    ("hinweise", lambda k, q: k["aufgaben"]["hinweise"], 1),
    (
        "musik_erinnerungen",
        lambda k, q: [(r["enabled"], r["days_ahead"]) for r in k["musik_erinnerungen"]],
        [(True, 5)],
    ),
    (
        "qualifikationen",
        lambda k, q: [x["qualifikation"] for x in q],
        ["Jugendleiterin Erika"],
    ),
]


@pytest.mark.parametrize(
    ("auslesen", "erwartet"), [t[1:] for t in TEILE], ids=[t[0] for t in TEILE]
)
def test_vorstand_sieht_geschuetzten_teil_in_der_auskunft(
    api, orgs, member, board_a, bestand, auslesen, erwartet
):
    konto, quals, _ = _auskunft(api(board_a), orgs, member)
    assert auslesen(konto, quals) == erwartet


def test_auskunft_ohne_daten_anderer_personen_und_fremder_vereine(
    api, orgs, member, board_a, bestand
):
    konto, quals, everything = _auskunft(api(board_a), orgs, member)
    fremd = bestand["fremd"]

    # Unterschrift ist Erikas, nicht die von Max
    assert konto["gespeicherte_unterschrift"]["geändert"].startswith("2025-02-03T10:00:00")
    assert konto["anmelde_email"] == "erika.rls@example.org"

    # Nichts von Max Beispiel
    for marker in (
        "max.beispiel@example.org",
        "Aufgabe von Max",
        "Assistent von Max",
        "Kassierer Max",
        "Sanitäter Max",
        "2001-01-01T08:00",
        '"days_ahead": 13',
    ):
        assert marker.encode() not in everything, marker

    # Nichts aus Verein B
    for marker in (
        "Erikas Aufgabe in B",
        "Geteilt in Verein B",
        "Wolke Verein B",
        "erika.verein-b",
        "Fremder Assistent B",
        "Fremde Funktion B",
        f"org:{fremd.pk}",
        "Übungsleiter Verein B",
        '"days_ahead": 11',
    ):
        assert marker.encode() not in everything, marker

    # Zählungen nur aus Verein A und nur für Erika
    aufgaben = konto["aufgaben"]
    assert aufgaben["freigaben"] == 1
    assert aufgaben["geplante_erinnerungen"] == 1
    assert aufgaben["hinweise"] == 1
    assert [r["days"] for r in aufgaben["erinnerungen"]] == [[3]]
    assert len(aufgaben["einstellungen"]) == 1
    assert [b["context"] for b in konto["briefbogen"]] == [f"org:{orgs['a'].pk}"]
    assert [x["qualifikation"] for x in quals] == ["Jugendleiterin Erika"]
