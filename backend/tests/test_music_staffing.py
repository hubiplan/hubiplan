"""Wiederverwendbare Sollbesetzungen und atomare, rechtegeprüfte Mehrfacheinteilung."""
# ruff: noqa: F811

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from core.tenancy import tenant_context
from datatransfer.tables import IdMap, dump_rows, load_tables
from music.models import (
    Assignment,
    EnsembleTemplate,
    EnsembleTemplatePosition,
    Musician,
    MusicianClaim,
    Performance,
    Position,
    Skill,
)
from music.views import AssignmentViewSet, MusicAssignmentSerializer

from .factories import give_role, make_member, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture
def staffing(club, music):
    base, event = music
    member = make_member(club, "Mika", "Beispiel")
    with tenant_context(club.pk):
        performance = Performance.objects.create(organization=club, event=event)
        tuba = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba", required=2
        )
        flute = Position.objects.create(
            organization=club, performance=performance, instrument="Flöte", required=1
        )
        musicians = []
        for i, instruments in enumerate(
            (["Tuba"], ["Tuba"], ["Tuba", "Flöte"], ["Flöte"], ["Tuba"])
        ):
            m = Musician.objects.create(
                organization=club,
                membership=member if i == 0 else None,
                name="" if i == 0 else f"Muster Gast {i}",
                active=i != 4,
            )
            for instrument in instruments:
                Skill.objects.create(organization=club, musician=m, instrument=instrument)
            musicians.append(m)
    return base, performance, tuba, flute, musicians


def post(c, url, data, key=None):
    return c.post(url, data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))


def endpoint(staffing):
    return f"{staffing[0]}/performances/{staffing[1].pk}/staffing/"


def template(c, base, **changes):
    data = {
        "name": "Kleine Besetzung",
        "positions": [
            {"instrument": "Tuba", "register": "", "required": 3},
            {"instrument": "Trompete", "register": "1", "required": 2},
        ],
        **changes,
    }
    response = post(c, base + "/ensemble-templates/", data)
    assert response.status_code == 201, response.content
    return response.json()


def assign(c, staffing, pairs, **kwargs):
    return post(
        c,
        endpoint(staffing),
        {
            "action": "assign",
            "assignments": [{"musician": m.pk, "position": p.pk} for m, p in pairs],
        },
        **kwargs,
    )


def test_template_crud_validation_and_retry(c, staffing):
    base = staffing[0]
    data = {"name": "Standard", "positions": [{"instrument": "Tuba", "required": 2}]}
    key = str(uuid.uuid4())
    first = post(c, base + "/ensemble-templates/", data, key)
    assert first.status_code == 201
    assert post(c, base + "/ensemble-templates/", data, key).json()["id"] == first.json()["id"]
    url = f"{base}/ensemble-templates/{first.json()['id']}/"
    response = c.patch(
        url, {"positions": [{"instrument": "Tuba", "required": 4}]}, content_type=JSON
    )
    assert response.json()["positions"][0]["required"] == 4
    assert c.patch(url, {"active": False}, content_type=JSON).json()["active"] is False
    bad = {
        **data,
        "positions": [
            {"instrument": "Tuba", "required": 1},
            {"instrument": " tuba ", "required": 1},
        ],
    }
    assert post(c, base + "/ensemble-templates/", bad).status_code == 400
    assert post(c, base + "/ensemble-templates/", {**data, "positions": []}).status_code == 400
    assert c.post(base + "/ensemble-templates/", data, content_type=JSON).status_code == 400


def test_apply_template_preserves_assignments_and_larger_counts(c, club, staffing):
    base, performance, tuba, flute, musicians = staffing
    with tenant_context(club.pk):
        accepted = Assignment.objects.create(
            organization=club,
            performance=performance,
            position=tuba,
            musician=musicians[0],
            status="accepted",
        )
        declined = Assignment.objects.create(
            organization=club,
            performance=performance,
            position=flute,
            musician=musicians[3],
            status="declined",
        )
        claim = MusicianClaim.objects.create(
            organization=club, assignment=accepted, status="approved", attended=True
        )
    row = template(c, base)
    payload = {"action": "apply_template", "template": row["id"]}
    assert post(c, endpoint(staffing), payload).status_code == 200
    assert post(c, endpoint(staffing), payload).status_code == 200
    with tenant_context(club.pk):
        assert performance.positions.count() == 3
        tuba.refresh_from_db()
        flute.refresh_from_db()
        accepted.refresh_from_db()
        declined.refresh_from_db()
        claim.refresh_from_db()
        assert tuba.required == 3 and flute.required == 1
        assert (
            accepted.status == "accepted"
            and declined.status == "declined"
            and claim.status == "approved"
        )
    # Änderungen an der Vorlage wirken erst bei erneutem Anwenden; kleinere Werte schrumpfen nicht.
    c.patch(
        f"{base}/ensemble-templates/{row['id']}/",
        {"positions": [{"instrument": "Tuba", "required": 1}]},
        content_type=JSON,
    )
    assert post(c, endpoint(staffing), payload).status_code == 200
    with tenant_context(club.pk):
        tuba.refresh_from_db()
        assert tuba.required == 3 and performance.positions.count() == 3
    c.patch(f"{base}/ensemble-templates/{row['id']}/", {"active": False}, content_type=JSON)
    assert post(c, endpoint(staffing), payload).status_code == 404


def test_save_current_instrumentation_as_template(c, club, staffing):
    key = str(uuid.uuid4())
    data = {"action": "save_template", "name": "Aus Musterauftritt"}
    response = post(c, endpoint(staffing), data, key)
    assert response.status_code == 200
    assert post(c, endpoint(staffing), data, key).json() == response.json()
    with tenant_context(club.pk):
        assert EnsembleTemplate.objects.count() == 1
        row = EnsembleTemplate.objects.get(pk=response.json()["template"])
        assert list(row.positions.values_list("instrument", "required")) == [
            ("Tuba", 2),
            ("Flöte", 1),
        ]
    # Mehrdeutige bestehende Positionen werden nicht stillschweigend zusammengelegt.
    with tenant_context(club.pk):
        Position.objects.create(
            organization=club, performance=staffing[1], instrument="tuba", required=1
        )
    assert post(c, endpoint(staffing), data).status_code == 400
    row = template(c, staffing[0])
    assert (
        post(c, endpoint(staffing), {"action": "apply_template", "template": row["id"]}).status_code
        == 400
    )


def test_batch_assignments_candidates_and_idempotency(c, club, staffing):
    _, performance, tuba, flute, musicians = staffing
    data = c.get(endpoint(staffing)).json()
    assert len(data["candidates"]) == 4
    multi = next(r for r in data["candidates"] if r["id"] == musicians[2].pk)
    assert set(multi["positions"]) == {tuba.pk, flute.pk}
    assert (
        next(r for r in data["candidates"] if r["id"] == musicians[0].pk)["name"]
        == "Beispiel, Mika"
    )
    pairs = [(musicians[0], tuba), (musicians[1], tuba), (musicians[3], flute)]
    key = str(uuid.uuid4())
    assert assign(c, staffing, pairs, key=key).json() == {"created": 3}
    assert assign(c, staffing, pairs, key=key).json() == {"created": 3}
    assert assign(c, staffing, pairs).json() == {"created": 0}
    assert assign(c, staffing, pairs[:1], key=key).status_code == 409
    with tenant_context(club.pk):
        assert performance.assignments.count() == 3
        assert set(performance.assignments.values_list("status", flat=True)) == {"pending"}
    data = c.get(endpoint(staffing)).json()
    assert [r["id"] for r in data["candidates"]] == [musicians[2].pk]
    assert [r["assigned"] for r in data["positions"]] == [2, 1]


@pytest.mark.parametrize(
    "invalid",
    ["unskilled", "inactive", "overfull", "duplicate", "foreign_musician", "foreign_position"],
)
def test_invalid_batch_is_atomic(c, club, orgs, staffing, invalid):
    _, performance, tuba, flute, m = staffing
    pairs = [(m[0], tuba)]
    if invalid == "unskilled":
        pairs.append((m[1], flute))
    elif invalid == "inactive":
        pairs.append((m[4], tuba))
    elif invalid == "overfull":
        pairs.extend([(m[1], tuba), (m[2], tuba)])
    elif invalid == "duplicate":
        pairs.append((m[0], tuba))
    elif invalid == "foreign_musician":
        with tenant_context(orgs["b"].pk):
            foreign = Musician.objects.create(organization=orgs["b"], name="Fremder Gast")
        pairs.append((foreign, tuba))
    else:
        with tenant_context(club.pk):
            from events.models import Event

            event = Event.objects.create(
                organization=club,
                title="Anderer Auftritt",
                starts_at=performance.event.starts_at,
                ends_at=performance.event.ends_at,
            )
            other = Performance.objects.create(organization=club, event=event)
            position = Position.objects.create(
                organization=club, performance=other, instrument="Tuba"
            )
        pairs.append((m[1], position))
    assert assign(c, staffing, pairs).status_code in (400, 404)
    with tenant_context(club.pk):
        assert not performance.assignments.exists()


def test_existing_declines_and_cancellation_are_preserved(c, club, staffing):
    _, performance, tuba, flute, m = staffing
    with tenant_context(club.pk):
        row = Assignment.objects.create(
            organization=club,
            performance=performance,
            position=tuba,
            musician=m[0],
            status="declined",
        )
    assert assign(c, staffing, [(m[3], flute), (m[0], tuba)]).status_code == 400
    assert m[0].pk not in [r["id"] for r in c.get(endpoint(staffing)).json()["candidates"]]
    with tenant_context(club.pk):
        row.refresh_from_db()
        assert row.status == "declined" and performance.assignments.count() == 1
        performance.event.is_cancelled = True
        performance.event.save()
    assert assign(c, staffing, [(m[3], flute)]).status_code == 400


def test_rights_module_and_foreign_templates(api, c, club, orgs, staffing):
    base = staffing[0]
    user = make_user("besetzunglesen@example.org")
    role = give_role(user, club, permissions=["music.view", "events.view"], name="Besetzung lesen")
    client = api(user)
    assert client.get(endpoint(staffing)).status_code == 200
    assert client.get(base + "/ensemble-templates/").status_code == 200
    assert (
        post(
            client, endpoint(staffing), {"action": "save_template", "name": "Unzulässig"}
        ).status_code
        == 403
    )
    with tenant_context(orgs["b"].pk):
        foreign = EnsembleTemplate.objects.create(organization=orgs["b"], name="Fremd")
    assert (
        post(
            c, endpoint(staffing), {"action": "apply_template", "template": foreign.pk}
        ).status_code
        == 404
    )
    role.role.is_board = False
    role.role.save()
    with tenant_context(club.pk):
        staffing[1].event.visibility = "board"
        staffing[1].event.save()
    assert client.get(endpoint(staffing)).status_code == 404
    club.enabled_modules.remove("music")
    club.save()
    assert c.get(base + "/ensemble-templates/").status_code == 404
    assert c.get(endpoint(staffing)).status_code == 404


def test_template_roundtrip_and_rls(c, club, orgs, staffing):
    template(c, staffing[0])
    with tenant_context(club.pk):
        tables = {
            model._meta.label_lower: dump_rows(model, club, None)
            for model in (EnsembleTemplate, EnsembleTemplatePosition)
        }
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert (
            not EnsembleTemplate.objects.exists() and not EnsembleTemplatePosition.objects.exists()
        )
    with tenant_context(orgs["b"].pk):
        assert load_tables(tables, orgs["b"], IdMap(), None) == 3
        row = EnsembleTemplate.objects.get(organization=orgs["b"])
        assert row.name == "Kleine Besetzung" and row.positions.count() == 2


def test_single_assignment_revalidates_after_batch(c, club, staffing):
    user = make_user("einteilen@example.org")
    give_role(user, club)
    _, performance, position, _, musicians = staffing
    with tenant_context(club.pk):
        view = AssignmentViewSet()
        view.org = club
        view.org_permissions = {"music.edit", "events.view"}
        view.request = SimpleNamespace(user=user)
        serializer = MusicAssignmentSerializer(
            data={
                "performance": performance.pk,
                "position": position.pk,
                "musician": musicians[0].pk,
            },
            context={"view": view},
        )
        assert serializer.is_valid(), serializer.errors
        Assignment.objects.create(
            organization=club, performance=performance, position=position, musician=musicians[0]
        )
        with pytest.raises(ValidationError):
            view.perform_create(serializer)
        assert performance.assignments.count() == 1
