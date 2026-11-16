"""Auskunft (Art. 15): Haushaltsmandate, Mails an Erziehungsberechtigte, Untereinheiten, Fotos.

Gesamtaudit 15.11., PF-20: Es fehlten Mandate und Rechnungen eines Haushalts, für den die
Person zahlt, Mails an die Erziehungsberechtigten, Qualifikationen aus Untereinheiten und
Dateien (wartende Mitgliederfotos). Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
import io
import json
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from billing.models import HouseholdPayer, Mandate
from core.tenancy import rls_bypass, tenant_context
from members.models import ContactPerson, Household, HouseholdMember, Membership
from members.photo_models import MemberPhoto
from outbox.models import OutgoingMail
from qualifications.models import Qualification, QualificationType

from .factories import make_org
from .test_m3_workflows import member, types, url  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _private(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


def test_auskunft_rest(api, orgs, member, board_a):
    club = orgs["a"]
    unit = make_org("Spielmannszug Auskunft", "unit", parent=club)
    with rls_bypass():
        m = Membership.objects.get(pk=member["id"])
    with tenant_context(club.pk):
        home = Household.objects.create(organization=club, name="Familie Muster")
        HouseholdMember.objects.create(
            organization=club,
            household=home,
            membership=m,
            kind=home.kind,
            valid_from=datetime.date(2020, 1, 1),
        )
        HouseholdPayer.objects.create(
            organization=club, household=home, kind=HouseholdPayer.Kind.MEMBER, membership=m
        )
        Mandate.objects.create(
            organization=club,
            household=home,
            reference="HH-4711",
            holder="Erika Muster",
            iban="DE02120300000000202051",
            signed_on=datetime.date(2024, 1, 1),
            source="paper",
        )
        ContactPerson.objects.create(
            organization=club,
            membership=m,
            last_name="Muster",
            first_name="Hans",
            email="eltern.muster@example.org",
            is_guardian=True,
        )
        MemberPhoto.objects.create(
            organization=club,
            membership=m,
            status=MemberPhoto.Status.PENDING,
            image=SimpleUploadedFile("warte.jpg", b"\xff\xd8erfunden"),
            thumbnail=SimpleUploadedFile("warte-klein.jpg", b"\xff\xd8erfunden"),
        )
    with rls_bypass():
        OutgoingMail.objects.create(
            organization=club,
            to="eltern.muster@example.org",
            subject="Elternbrief",
            body="Text",
        )
    with tenant_context(unit.pk):
        kind = QualificationType.objects.create(organization=unit, name="Jugendleiter")
        Qualification.objects.create(
            organization=unit, person=m.person, kind=kind, acquired_on=datetime.date(2023, 5, 1)
        )

    resp = api(board_a).get(url(orgs, member, "auskunft/"))
    assert resp.status_code == 200, resp.content[:300]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    mandates = json.loads(zf.read("mandate.json"))
    assert [x["reference"] for x in mandates] == ["HH-4711"]
    mails = json.loads(zf.read("mails.json"))
    assert any(x["betreff"] == "Elternbrief" for x in mails)
    quals = json.loads(zf.read("qualifikationen.json"))
    assert [q["qualifikation"] for q in quals] == ["Jugendleiter"]
    assert any(name.startswith("foto-") for name in zf.namelist())
