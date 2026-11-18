"""Zeilenschutzregeln rechnen mit dem Datum der Anwendung (Europe/Berlin), nicht in UTC.

Die DB-Sitzung läuft in UTC; ``CURRENT_DATE`` lag zwischen Mitternacht und 1 Uhr
(Sommerzeit 2 Uhr) einen Tag hinter ``timezone.localdate()``. Im Merge-Zug um 0:10 Uhr sah
deshalb ein Rolleninhaber eine geteilte Aufgabe nicht. Regeln nutzen jetzt ``hubiplan_heute()``
(core 0042, todos 0018, finance 0038).
"""

import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone

from access.models import RoleAssignment
from core.tenancy import rls_bypass

from .factories import give_role, make_user
from .test_todos import create, url
from .test_todos import patch as change

pytestmark = pytest.mark.django_db

UTC = datetime.UTC


@pytest.fixture(autouse=True)
def nur_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Zeilenschutz gibt es nur unter PostgreSQL")


def _wert(sql, params=()):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


@pytest.mark.parametrize(
    ("zeitpunkt", "datum"),
    [
        # Winterzeit: 23:30 UTC ist 0:30 Uhr am Folgetag
        (datetime.datetime(2026, 11, 17, 23, 30, tzinfo=UTC), datetime.date(2026, 11, 18)),
        (datetime.datetime(2026, 11, 17, 22, 59, tzinfo=UTC), datetime.date(2026, 11, 17)),
        # Sommerzeit: 22:30 UTC ist 0:30 Uhr am Folgetag, 21:30 UTC noch 23:30 Uhr
        (datetime.datetime(2026, 7, 1, 22, 30, tzinfo=UTC), datetime.date(2026, 7, 2)),
        (datetime.datetime(2026, 7, 1, 21, 30, tzinfo=UTC), datetime.date(2026, 7, 1)),
    ],
)
def test_datum_in_zeitzone_der_anwendung(zeitpunkt, datum):
    assert _wert("SELECT hubiplan_datum(%s)", [zeitpunkt]) == datum
    assert timezone.localdate(zeitpunkt) == datum


def test_heute_wie_die_anwendung():
    with connection.cursor() as cur:
        cur.execute("SELECT hubiplan_heute(), now()")
        heute, jetzt = cur.fetchone()
    assert heute == timezone.localdate(jetzt)


def test_keine_regel_und_keine_funktion_mit_current_date():
    """Wächter: CURRENT_DATE rechnet in der Zeitzone der Sitzung (UTC)."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT tablename || '.' || policyname FROM pg_policies "
            "WHERE schemaname = 'public' "
            "AND (qual ~* '\\mcurrent_date\\M' OR with_check ~* '\\mcurrent_date\\M')"
        )
        regeln = [zeile[0] for zeile in cur.fetchall()]
        cur.execute(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.prosrc ~* '\\mcurrent_date\\M' "
            "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid "
            "AND d.deptype = 'e')"
        )
        funktionen = [zeile[0] for zeile in cur.fetchall()]
    assert regeln == [], f"Regeln mit CURRENT_DATE statt hubiplan_heute(): {regeln}"
    assert funktionen == [], f"Funktionen mit CURRENT_DATE statt hubiplan_heute(): {funktionen}"


def test_rollenwechsel_kurz_nach_mitternacht(api, board_a, orgs):
    """0:30 Uhr: heute beginnende Rolle sieht die Aufgabe, gestern beendete nicht mehr."""
    org = orgs["a"]
    berlin = ZoneInfo(settings.TIME_ZONE)
    tag = timezone.localdate()
    zeitpunkt = datetime.datetime.combine(tag, datetime.time(0, 30), berlin)
    # In UTC ist es noch der Vortag: Mit CURRENT_DATE wäre die neue Rolle unsichtbar.
    assert zeitpunkt.astimezone(UTC).date() == tag - datetime.timedelta(days=1)

    reader = make_user("aufgaben-lesen@example.org")
    successor = make_user("nachfolge@example.org")
    alt = give_role(reader, org, permissions=["todos.view"], name="Aufgaben lesen")
    with rls_bypass():
        RoleAssignment.objects.create(
            organization=org, role=alt.role, user=successor, valid_from=tag
        )
        alt.valid_until = tag - datetime.timedelta(days=1)
        alt.save()

    # Uhr der Datenbank (nur in dieser Testtransaktion) und der Anwendung auf 0:30 Uhr
    with connection.cursor() as cur:
        cur.execute(
            "CREATE OR REPLACE FUNCTION public.hubiplan_heute() RETURNS date "
            "LANGUAGE sql STABLE AS $$ SELECT public.hubiplan_datum("
            f"'{zeitpunkt.isoformat()}'::timestamptz) $$"
        )
    with patch("django.utils.timezone.now", return_value=zeitpunkt):
        todo = create(api, board_a, org)
        response = change(api, board_a, org, todo, shares=[{"role": alt.role_id, "level": "edit"}])
        assert response.status_code == 200, response.content
        assert api(successor).get(url(org, todo["id"])).status_code == 200
        assert api(reader).get(url(org, todo["id"])).status_code == 403
