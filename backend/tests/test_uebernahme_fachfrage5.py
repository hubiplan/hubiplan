"""Vollübernahme nimmt die restlichen Vereinsdaten mit (Gesamtaudit 13.11., V-03, Fachfrage 5).

Online-Anträge bleiben ausdrücklich auf der alten Instanz.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest

from circulars.models import Circular, MailingList
from competitions.models import PhotoSample, PhotoSampleConsent
from core.tenancy import rls_bypass, tenant_context
from datatransfer.tables import IdMap, remap_design
from exchange.models import ExportTemplate, ImportTemplate
from finance.models import ReopenedClosing
from members.models import Membership, MemberType
from organizations.models import Department
from places.models import Place
from portal.models import CancellationRequest, ChangeRequest
from todos.models import TodoCleanupSetting
from website.models import DesignVersion, Website
from website.social_models import SocialDraft

from .test_audit_3110_daten_umzug import run_import
from .test_datatransfer import (  # noqa: F401
    _eager,
    _on_commit_now,
    as_doc,
    club_c,
    export,
    platform_admin,
    types,
)

pytestmark = pytest.mark.django_db
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
EINGANG = datetime.datetime(2025, 3, 4, 10, 30, tzinfo=datetime.UTC)


def test_restliche_vereinsdaten_ziehen_mit(api, club_c, board_c, platform_admin):
    club = club_c["club"]
    with tenant_context(club.pk):
        ms = Membership.objects.filter(organization=club).order_by("pk").first()
        nachname = ms.person.last_name
        art = MemberType.objects.filter(organization=club).order_by("pk").first()
        zug = Department.objects.get(organization=club, name="1. Zug")
        Place.objects.create(organization=club, name="Schützenhalle", address="Musterweg 1")
        TodoCleanupSetting.objects.create(organization=club, purge_done=True)
        closed = ReopenedClosing.objects.create(
            organization=club,
            year=2024,
            closed_at=EINGANG,
            closed_by_name="Erika Muster",
            snapshot={"saldo": "12.50"},
            reopened_by=board_c,
            reopened_by_name="Erika Muster",
            reason="Beleg nachgetragen",
        )
        ReopenedClosing.objects.filter(pk=closed.pk).update(reopened_at=EINGANG)
        PhotoSampleConsent.objects.create(organization=club, enabled=True)
        PhotoSample.objects.create(
            organization=club,
            target="lg10",
            target_data={"ring": 0.5},
            image=JPEG,
            px_per_mm="12.50",
            hits=[[1.0, 2.0]],
            detected=[],
        )
        pattern = Circular.objects.create(
            organization=club, subject="Verteiler Vorstand", created_by=board_c
        )
        MailingList.objects.create(
            organization=club,
            name="Vorstand",
            local_part="vorstand-c",
            aliases=["vorstand-verein-c"],
            pattern=pattern,
        )
        site = Website.objects.filter(organization=club).first() or Website.objects.create(
            organization=club
        )
        DesignVersion.objects.create(
            organization=club,
            website=site,
            data={"design": "klassisch", "header_image": 987654},
            published_by=board_c,
        )
        SocialDraft.objects.create(
            organization=club, website=site, text="Schützenfest!", images=[987654]
        )
        change = ChangeRequest.objects.create(
            organization=club,
            membership=ms,
            user=board_c,
            data={"street": "Neuer Weg 2"},
            previous={"street": "Alter Weg 1"},
        )
        ChangeRequest.objects.filter(pk=change.pk).update(created_at=EINGANG)
        cancel = CancellationRequest.objects.create(
            organization=club,
            membership=ms,
            user=board_c,
            exit_date=datetime.date(2025, 12, 31),
            earliest_date=datetime.date(2025, 12, 31),
        )
        CancellationRequest.objects.filter(pk=cancel.pk).update(created_at=EINGANG)
        ExportTemplate.objects.create(
            organization=club,
            name="Zugliste",
            columns=["last_name"],
            filters={"status": "aktiv", "art": art.pk, "abteilung": str(zug.pk), "haushalt": "mit"},
        )
        ImportTemplate.objects.create(
            organization=club,
            name="Altprogramm",
            mapping={"Name": "last_name"},
            value_mapping={
                "member_type": {"A": str(art.pk), "X": "99999999"},
                "exit_reason": {"gest.": "death"},
            },
        )

    content, _ = export(api(board_c), f"/api/orgs/{club.pk}")
    tables = as_doc(content)["organization"]["tables"]
    # Konten der alten Instanz stehen nicht in der Datei
    for name in ("portal.changerequest", "portal.cancellationrequest"):
        assert "user" not in tables[name][0] and "decided_by" not in tables[name][0]
    assert "reopened_by" not in tables["finance.reopenedclosing"][0]
    assert "published_by" not in tables["website.designversion"][0]
    assert not any(name.startswith("admission.") for name in tables)

    new = run_import(api(platform_admin), content)
    with rls_bypass():
        assert Place.objects.get(organization=new).address == "Musterweg 1"
        assert TodoCleanupSetting.objects.get(organization=new).purge_done is True
        closed = ReopenedClosing.objects.get(organization=new)
        assert closed.reopened_at == EINGANG and closed.reason == "Beleg nachgetragen"
        assert closed.reopened_by_name == "Erika Muster" and closed.reopened_by_id is None
        assert PhotoSampleConsent.objects.get(organization=new).enabled is True
        assert bytes(PhotoSample.objects.get(organization=new).image) == JPEG
        # Die Adresse gibt es auf dieser Instanz schon: neue Adresse, Verteiler bleibt aus
        ml = MailingList.objects.get(organization=new)
        assert ml.local_part == "vorstand-c-2" and ml.is_active is False and ml.aliases == []
        assert ml.pattern.organization_id == new.pk and ml.pattern.subject == "Verteiler Vorstand"
        version = DesignVersion.objects.get(organization=new)
        assert version.data == {"design": "klassisch", "header_image": None}
        assert version.website.organization_id == new.pk
        assert SocialDraft.objects.get(organization=new).images == []
        change = ChangeRequest.objects.get(organization=new)
        assert change.membership.organization_id == new.pk and change.created_at == EINGANG
        assert change.membership.person.last_name == nachname
        assert change.data == {"street": "Neuer Weg 2"} and change.user_id is None
        cancel = CancellationRequest.objects.get(organization=new)
        assert cancel.created_at == EINGANG and cancel.exit_date == datetime.date(2025, 12, 31)
        new_art = MemberType.objects.get(organization=new, name=art.name)
        new_zug = Department.objects.get(organization=new, name="1. Zug")
        assert ExportTemplate.objects.get(organization=new).filters == {
            "status": "aktiv",
            "art": new_art.pk,
            "abteilung": str(new_zug.pk),
            "haushalt": "mit",
        }
        assert ImportTemplate.objects.get(organization=new).value_mapping == {
            "member_type": {"A": str(new_art.pk)},
            "exit_reason": {"gest.": "death"},
        }


def test_fruehere_gestaltung_bekommt_neue_nummern():
    ids = IdMap()
    ids.set("website.websiteimage", 5, 50)
    ids.set("honors.dignity", 7, 70)
    data = remap_design(
        {
            "design": "klassisch",
            "header_image": 5,
            "home_sections": [{"kind": "image", "data": {"image": 5}}],
            "menu": [
                {"key": "dignity:7", "children": [{"key": "dignity:8"}]},
                {"key": "dignity:9"},
                {"key": "termine"},
            ],
            "block_names": {"dignity:7": "Könige", "dignity:9": "weg"},
            "menu_button": "dignity:9",
        },
        ids,
    )
    assert data == {
        "design": "klassisch",
        "header_image": 50,
        "home_sections": [{"kind": "image", "data": {"image": 50}}],
        "menu": [{"key": "dignity:70", "children": []}, {"key": "termine", "children": []}],
        "block_names": {"dignity:70": "Könige"},
        "menu_button": "",
    }
