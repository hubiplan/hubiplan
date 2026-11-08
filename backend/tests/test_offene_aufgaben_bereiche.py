"""„Zu erledigen“ aus allen Bereichen (Menüprüfung 2, N-03): Versammlungen, Helferdienste,
Meldungen, Rechnungen, Konten; jeder Eintrag nennt seinen Bereich."""

import datetime

import pytest
from django.utils import timezone

from core.tenancy import tenant_context

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def url(org):
    return f"/api/orgs/{org.pk}/open-tasks/"


def items(client, org, area=None):
    resp = client.get(url(org))
    assert resp.status_code == 200, resp.content
    rows = resp.json()["items"]
    assert all(r.get("area") for r in rows)
    return [r for r in rows if area is None or r["area"] == area]


def test_versammlung_einladung_antrag_protokoll(api, orgs):
    from meetings.models import Meeting, Motion

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "meetings", "events"})
    org.save()
    chef = make_user("vorsitz@example.org")
    give_role(chef, org, permissions=["meetings.edit"], name="Vorsitz")
    leser = make_user("beisitz@example.org")
    give_role(leser, org, permissions=["meetings.view"], name="Beisitz")
    c = api(chef)
    base = f"/api/orgs/{org.pk}/meetings/"
    kind = next(k for k in c.get(base + "kinds/").json() if k["name"] == "Jahreshauptversammlung")
    start = timezone.now() + datetime.timedelta(days=10)
    m = c.post(
        base,
        {
            "kind": kind["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + datetime.timedelta(hours=2)).isoformat(),
        },
        content_type=JSON,
    ).json()
    erika = make_member(org, "Erika", "Muster")
    with tenant_context(org.pk):
        Motion.objects.create(
            organization=org,
            meeting_id=m["id"],
            membership=erika,
            name="Erika Muster",
            title="Neue Fahne",
            text="Begründung",
        )
        past = timezone.now() - datetime.timedelta(days=3)
        old = Meeting.objects.get(pk=m["id"])
        # Zweite, schon gehaltene Versammlung mit offenem Protokoll
        from events.models import Event

        ev = Event.objects.create(
            organization=org, title="Vorstandssitzung", starts_at=past, ends_at=past
        )
        Meeting.objects.create(
            organization=org, kind=old.kind, event=ev, status=Meeting.Status.HELD
        )
    kinds = {r["kind"]: r for r in items(c, org, "meetings")}
    assert set(kinds) == {"meeting_invite", "meeting_motions", "meeting_minutes"}
    assert kinds["meeting_invite"]["highlight"] is True  # Frist (14 Tage) schon vorbei
    assert kinds["meeting_invite"]["link"] == f"/versammlungen?versammlung={m['id']}"
    assert items(api(leser), org, "meetings") == []


def test_helferdienste_offene_plaetze(api, orgs):
    from helpers.models import Duty, HelperPlan, Shift

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "helpers", "events"})
    org.save()
    chef = make_user("festwart@example.org")
    give_role(chef, org, permissions=["helpers.edit"], name="Festwart")
    soon = timezone.now() + datetime.timedelta(days=3)
    with tenant_context(org.pk):
        plan = HelperPlan.objects.create(
            organization=org, title="Schützenfest", status=HelperPlan.Status.PUBLISHED
        )
        duty = Duty.objects.create(organization=org, plan=plan, name="Theke")
        Shift.objects.create(organization=org, duty=duty, starts_at=soon, ends_at=soon, needed=3)
        entwurf = HelperPlan.objects.create(organization=org, title="Entwurf")
        d2 = Duty.objects.create(organization=org, plan=entwurf, name="Kasse")
        Shift.objects.create(organization=org, duty=d2, starts_at=soon, ends_at=soon, needed=2)
    rows = items(api(chef), org, "helpers")
    assert [r["title"] for r in rows] == ["Schützenfest: 3 Plätze offen"]
    assert rows[0]["link"] == f"/helferdienste?plan={plan.pk}"


def test_meldung_rueckfrage_und_meldeschluss(api, orgs):
    from entries.models import Call, Entry

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "entries"})
    org.save()
    melder = make_user("sport@example.org")
    give_role(melder, org, permissions=["entries.submit"], name="Sportleiter")
    today = timezone.localdate()
    with tenant_context(org.pk):
        frage = Call.objects.create(organization=org, title="Pokal", organizer="Bezirk")
        Entry.objects.create(organization=org, call=frage, status=Entry.Status.RETURNED)
        bald = Call.objects.create(
            organization=org,
            title="Meisterschaft",
            organizer="Kreis",
            deadline=today + datetime.timedelta(days=3),
        )
        Entry.objects.create(organization=org, call=bald)
        # Nur an Untereinheiten verteilt: keine eigene Meldung, kein Eintrag
        Call.objects.create(
            organization=org,
            title="Zugpokal",
            organizer="Verein",
            deadline=today + datetime.timedelta(days=2),
        )
    rows = items(api(melder), org, "entries")
    assert [(r["kind"], r["link"]) for r in rows] == [
        ("entry_returned", f"/meldungen/{frage.pk}"),
        ("entry_deadline", f"/meldungen/{bald.pk}"),
    ]


def test_rechnungen_nur_mit_recht_und_im_bereich_finanzen(api, orgs, board_a):
    from billing.models import Invoice

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "billing"})
    org.save()
    erika = make_member(org, "Erika", "Muster")
    with tenant_context(org.pk):
        Invoice.objects.create(
            organization=org,
            membership=erika,
            recipient_kind="member",
            recipient_name="Erika Muster",
            date=timezone.localdate(),
            due_date=timezone.localdate() + datetime.timedelta(days=14),
            status=Invoice.Status.DRAFT,
        )
    leser = make_user("pruefer@example.org")
    give_role(leser, org, permissions=["billing.view"], name="Kassenprüfer")
    kinds = [r["kind"] for r in items(api(board_a), org, "finance")]
    assert "invoices_draft" in kinds
    assert "invoices_draft" not in [r["kind"] for r in items(api(leser), org)]
