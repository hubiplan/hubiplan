"""Arbeitsstunden mit Ersatzbeitrag: Pflichtstunden je Mitgliedsart, Zählung aus erledigten
Helferschichten, fehlende Stunden als Posten im ersten Beitragslauf des Folgejahres."""
# ruff: noqa: F811  (Fixtures aus test_m9_billing als Parameter)

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from billing import services as billing
from billing.models import Invoice, WorkHourRule
from core.tenancy import rls_bypass, tenant_context
from helpers.models import Duty, HelperPlan, Shift, ShiftAssignment
from members.models import MembershipPeriod

from .factories import make_member
from .test_m9_billing import _private, base, c, club, setup, start_run, zug  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def wclub(club, setup):
    club.enabled_modules = [*club.enabled_modules, "events", "helpers"]
    club.save()
    with rls_bypass(), tenant_context(club.pk):
        WorkHourRule.objects.create(
            organization=club, member_type=setup["aktiv"], hours=Decimal("10"), rate=Decimal("15")
        )
    return club


def worked(club, membership, hours, day=datetime.date(2024, 6, 1), done=True):
    """Eine Schicht von ``hours`` Stunden an ``day``, Person eingeteilt und ggf. erledigt."""
    with rls_bypass(), tenant_context(club.pk):
        plan = HelperPlan.objects.create(organization=club, title="Sommerfest", status="published")
        duty = Duty.objects.create(organization=club, plan=plan, name="Theke")
        start = timezone.make_aware(datetime.datetime.combine(day, datetime.time(10)))
        shift = Shift.objects.create(
            organization=club,
            duty=duty,
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=hours),
        )
        ShiftAssignment.objects.create(
            organization=club, shift=shift, membership=membership, name="x", done=done
        )


def plan(club, year=2025, rhythm="yearly", index=1):
    with tenant_context(club.pk):
        return billing.plan_run(club, billing.period(club, year, rhythm, index))


def items(p):
    result = {i.membership.pk: i for i in p.member_items}
    for group in (*p.department_items.values(), *p.household_items.values()):
        result.update({i.membership.pk: i for i in group})
    return result


def test_fehlende_stunden_im_ersten_lauf_des_folgejahres(wclub, setup):
    teil = make_member(wclub, "Erika", "Teil")
    nichts = make_member(wclub, "Max", "Nichts")
    voll = make_member(wclub, "Lena", "Voll")
    neu = make_member(wclub, "Nina", "Neu", entry_date=datetime.date(2024, 7, 1))
    passiv = make_member(wclub, "Paul", "Passiv", member_type=setup["passiv"])
    worked(wclub, teil, 6)
    worked(wclub, voll, 8)
    worked(wclub, voll, 4, day=datetime.date(2024, 9, 1))
    # nicht erledigt, abgesagt oder in einem anderen Jahr zählt nicht
    worked(wclub, nichts, 5, done=None)
    worked(wclub, nichts, 5, day=datetime.date(2025, 3, 1))
    found = items(plan(wclub))
    assert found[teil.pk].work == Decimal("60.00")
    assert found[teil.pk].total == Decimal("120.00")
    assert "Soll 10 Std., geleistet 6 Std.: 4 Std. × 15,00 €" == found[teil.pk].work_detail
    assert found[nichts.pk].work == Decimal("150.00")
    assert found[voll.pk].work == Decimal("0")
    # ein halbes Jahr Mitglied: 5 Pflichtstunden
    assert found[neu.pk].work == Decimal("75.00")
    assert found[passiv.pk].work == Decimal("0")


def test_nur_im_ersten_zeitraum_und_mit_helferdiensten(wclub, club, base, c):
    m = make_member(wclub, "Erika", "Muster")
    resp = c.patch(f"{base}/settings/", {"rhythm": "quarterly"}, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    assert items(plan(wclub, rhythm="quarterly", index=1))[m.pk].work == Decimal("150.00")
    assert items(plan(wclub, rhythm="quarterly", index=2))[m.pk].work == Decimal("0")
    club.enabled_modules = [x for x in club.enabled_modules if x != "helpers"]
    club.save()
    assert items(plan(club, rhythm="quarterly", index=1))[m.pk].work == Decimal("0")


def test_altersgrenzen(wclub, base, c):
    alt = make_member(wclub, "Otto", "Alt", birth_date=datetime.date(1950, 1, 1))
    mittel = make_member(wclub, "Erika", "Mittel")
    resp = c.put(f"{base}/work-hours/", {"min_age": 18, "max_age": 65}, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    found = items(plan(wclub))
    assert found[alt.pk].work == Decimal("0")
    assert found[mittel.pk].work == Decimal("150.00")
    resp = c.put(f"{base}/work-hours/", {"min_age": 70, "max_age": 65}, content_type=JSON)
    assert resp.status_code == 400


def test_rechnung_mit_eigenem_posten_und_ohne_beitrag(wclub, setup, base, c):
    m = make_member(wclub, "Erika", "Muster")
    # beitragsfreie Mitgliedsart mit Pflichtstunden: nur der Ersatzbeitrag
    frei = make_member(wclub, "Emil", "Ehre", member_type=setup["frei"])
    with rls_bypass(), tenant_context(wclub.pk):
        WorkHourRule.objects.create(
            organization=wclub, member_type=setup["frei"], hours=Decimal("2"), rate=Decimal("10")
        )
    worked(wclub, m, 7.5)
    preview = c.post(f"{base}/runs/preview/", {"year": 2025, "period": 1}, content_type=JSON)
    assert preview.status_code == 200, preview.json()
    checks = preview.json()["checks"]
    assert checks["work_year"] == 2024
    assert checks["work_count"] == 2
    run = start_run(c, base)
    assert run.status_code == 201, run.json()
    with rls_bypass():
        inv = Invoice.objects.get(run_id=run.json()["id"], membership=m)
        lines = list(inv.lines.order_by("position"))
        assert [(line.text, line.amount) for line in lines] == [
            ("Mitgliedsbeitrag 2025", Decimal("60.00")),
            ("Ersatzbeitrag für fehlende Arbeitsstunden 2024", Decimal("37.50")),
        ]
        assert all(line.is_fee and line.membership_id == m.pk for line in lines)
        assert inv.total == Decimal("97.50")
        only = Invoice.objects.get(run_id=run.json()["id"], membership=frei)
        assert [line.amount for line in only.lines.all()] == [Decimal("20.00")]
    summary = c.get(f"{base}/runs/{run.json()['id']}/").json()
    assert summary["summary"]["members"] == 2
    # Neu berechnen legt nichts doppelt an
    c.post(f"{base}/runs/{run.json()['id']}/finalize/")
    assert c.post(f"{base}/runs/{run.json()['id']}/rebuild/").json()["created"] == 0


def test_ausgetreten_vor_dem_lauf_wird_nicht_berechnet(wclub):
    m = make_member(wclub, "Otto", "Alt")
    with rls_bypass(), tenant_context(wclub.pk):
        MembershipPeriod.objects.filter(membership=m).update(
            exit_date=datetime.date(2024, 12, 31), exit_reason="exit"
        )
    assert m.pk not in items(plan(wclub))


def test_einstellung_und_stand(wclub, setup, base, c):
    data = c.get(f"{base}/work-hours/").json()
    assert data["helpers_on"] is True
    rows = {r["name"]: r for r in data["rows"]}
    assert rows["aktiv"]["hours"] == "10.00"
    assert rows["passiv"]["hours"] is None
    resp = c.put(
        f"{base}/work-hours/",
        {
            "rows": [
                {"member_type": setup["aktiv"].pk, "hours": "12", "rate": "20"},
                {"member_type": setup["passiv"].pk, "hours": "4", "rate": ""},
            ]
        },
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    rows = {r["name"]: r for r in resp.json()["rows"]}
    assert (rows["aktiv"]["hours"], rows["aktiv"]["rate"]) == ("12.00", "20.00")
    assert (rows["passiv"]["hours"], rows["passiv"]["rate"]) == ("4.00", "0.00")
    resp = c.put(
        f"{base}/work-hours/",
        {"rows": [{"member_type": setup["passiv"].pk, "hours": "", "rate": ""}]},
        content_type=JSON,
    )
    assert {r["name"]: r["hours"] for r in resp.json()["rows"]}["passiv"] is None
    resp = c.put(
        f"{base}/work-hours/",
        {"rows": [{"member_type": setup["aktiv"].pk, "hours": "-1", "rate": "5"}]},
        content_type=JSON,
    )
    assert resp.status_code == 400

    m = make_member(wclub, "Erika", "Muster")
    worked(wclub, m, 3)
    stand = c.get(f"{base}/work-hours/balance/?jahr=2024").json()
    assert stand["people"] == [
        {
            "membership": m.pk,
            "name": "Muster, Erika",
            "member_type": "aktiv",
            "required": "12.00",
            "done": "3.00",
            "missing": "9.00",
            "amount": "180.00",
        }
    ]
    assert stand["total"] == "180.00"
