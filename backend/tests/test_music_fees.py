"""Fee templates, atomic batch drafts and accounting of partial musician payouts."""
# ruff: noqa: F811

import uuid

import pytest
from django.db import transaction

from core.tenancy import tenant_context
from finance import services
from finance.models import Booking
from music.models import Assignment, FeeTemplate, Musician, MusicianClaim

from .factories import give_role, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_settlement import expense, post, settlement  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


def template(c, club):
    url = f"/api/orgs/{club.pk}/music/fee-templates/"
    result = post(c, url, name="Konzertvergütung", fee="40.00", allowance="10.00", active=True)
    assert result.status_code == 201, result.content
    return result.json()["id"]


def test_batch_drafts_snapshot_and_retry(c, club, settlement):
    url, assignment = settlement
    source = template(c, club)
    with tenant_context(club.pk):
        other = Assignment.objects.create(
            organization=club,
            performance=assignment.performance,
            position=assignment.position,
            musician=Musician.objects.create(organization=club, name="Muster Gast"),
        )
    data = {
        "action": "batch_claims",
        "template": source,
        "rows": [
            {"assignment": assignment.pk, "attended": True},
            {"assignment": other.pk, "attended": False},
        ],
    }
    key = {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}
    first = c.post(url, data, content_type=JSON, **key)
    assert first.status_code == 200, first.content
    assert len(first.json()["claims"]) == 2
    assert {r["attended"] for r in first.json()["claims"]} == {True, False}
    assert all(
        r["status"] == "draft" and r["expenses"] == "0.00" and r["total"] == "50.00"
        for r in first.json()["claims"]
    )
    assert c.post(url, data, content_type=JSON, **key).status_code == 200
    assert (
        c.patch(
            f"/api/orgs/{club.pk}/music/fee-templates/{source}/", {"fee": "90"}, content_type=JSON
        ).status_code
        == 200
    )
    with tenant_context(club.pk):
        assert (
            MusicianClaim.objects.filter(assignment__performance=assignment.performance).count()
            == 2
        )
        assert MusicianClaim.objects.get(assignment=assignment).fee == 40
    assert c.post(url, data, content_type=JSON).status_code == 400
    assert (
        c.post(url, data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())).status_code
        == 400
    )


@pytest.mark.parametrize("bad", ["foreign", "duplicate", "missing_attendance", "archived"])
def test_batch_invalid_selection_saves_nothing(c, club, settlement, music, bad):
    url, assignment = settlement
    source = template(c, club)
    rows = [{"assignment": assignment.pk, "attended": False}]
    if bad == "foreign":
        rows.append({"assignment": 999999, "attended": True})
    elif bad == "duplicate":
        rows *= 2
    elif bad == "missing_attendance":
        rows[0].pop("attended")
    else:
        with tenant_context(club.pk):
            FeeTemplate.objects.filter(pk=source).update(active=False)
    response = c.post(
        url,
        {"action": "batch_claims", "template": source, "rows": rows},
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert response.status_code in [400, 404]
    with tenant_context(club.pk):
        assert not MusicianClaim.objects.filter(assignment=assignment).exists()


def test_partial_payments_limit_storno_and_retry(c, club, settlement):
    url, assignment = settlement
    result = post(
        c,
        url,
        action="claim",
        assignment=assignment.pk,
        fee="100",
        allowance="0",
        expenses="0",
        attended=True,
    )
    claim = result.json()["claims"][0]["id"]
    assert post(c, url, action="approve", claim=claim).status_code == 200
    one = expense(c, club, "40")
    with tenant_context(club.pk):
        original = Booking.objects.get(pk=one)

    def payout(amount):
        result = post(
            c,
            f"/api/orgs/{club.pk}/finance/bookings/",
            kind="expense",
            account=original.account_id,
            category=original.category_id,
            date=original.date.isoformat(),
            amount=amount,
            text="Muster-Teilzahlung",
        )
        assert result.status_code == 201, result.content
        return result.json()["id"]

    excessive, two = payout("70"), payout("60")
    result = post(c, url, action="payment", claim=claim, booking=one)
    assert result.status_code == 200, result.content
    data = result.json()["claims"][0]
    assert (
        data["paid"] is False and data["paid_amount"] == "40.00" and data["outstanding"] == "60.00"
    )
    assert post(c, url, action="payment", claim=claim, booking=one).status_code == 200
    assert post(c, url, action="payment", claim=claim, booking=excessive).status_code == 400
    assert post(c, url, action="void", claim=claim).status_code == 400
    assert (
        post(c, url, action="payment", claim=claim, booking=two).json()["claims"][0]["paid"] is True
    )
    with tenant_context(club.pk), transaction.atomic():
        services.cancel_booking(Booking.objects.get(pk=one), None, "Musterkorrektur")
    data = c.get(url).json()["claims"][0]
    assert (
        data["paid"] is False and data["paid_amount"] == "60.00" and data["outstanding"] == "40.00"
    )
    replacement = payout("40")
    assert (
        post(c, url, action="payment", claim=claim, booking=replacement).json()["claims"][0]["paid"]
        is True
    )


def test_template_scopes_and_negative_amount(c, api, club, settlement, orgs):
    source = template(c, club)
    url = f"/api/orgs/{club.pk}/music/fee-templates/"
    assert post(c, url, name="Ungültig", fee="-1", allowance="0").status_code == 400
    user = make_user("musikvorlage@example.org")
    give_role(user, club, permissions=["music.view", "finance.view"])
    assert api(user).get(url).status_code == 200
    assert post(api(user), url, name="Nicht erlaubt", fee="10", allowance="0").status_code == 403
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not FeeTemplate.objects.filter(pk=source).exists()
    club.enabled_modules.remove("music")
    club.save()
    assert c.get(url).status_code == 404
