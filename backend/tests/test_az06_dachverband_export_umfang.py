"""Dachverbands-Export im Umfang des Zeilenschutzes (Gesamtaudit 15.11., AZ-06, FF-18).

Mit Lesefreigabe enthielt der Export eines Dachverbands für seine Vereine mehr, als der
Zeilenschutz dem Dachverband zeigt: Fotos, Zusatzfelder der Vereine, Ehrungen und weitere
Mitgliedertabellen, die Konto-E-Mails der Vereinsrollen. Jetzt nur noch, was der Dachverband
unter der Rolle der Anwendung auch sieht. Erfundene Daten.
"""

import datetime
import json
import uuid

import pytest
from django.core.files.base import ContentFile

from core.tenancy import rls_bypass, set_rls, tenant_context
from customfields.models import FieldDefinition, FieldValue
from datatransfer import dump
from documents.models import Folder
from members.models import HonoraryTitle, Membership, MemberType
from members.photo_models import MemberPhoto
from organizations.models import Department

from .factories import give_role, make_member, make_user
from .test_datatransfer import as_doc
from .verbund_netz import app_role

pytestmark = pytest.mark.django_db
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


@pytest.fixture
def verband(orgs, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PRIVATE_ROOT = tmp_path / "private"
    fed, club = orgs["federation"], orgs["a"]
    fed.federation_member_access = "read"
    fed.save()
    vorstand = make_user("vorstand-umfang@example.org")
    give_role(vorstand, club)
    with tenant_context(club.pk):
        erika = make_member(club, "Erika", "Muster", birth_date=datetime.date(1980, 5, 17))
        eigenes = FieldDefinition.objects.create(organization=club, label="Schuhgröße", key="schuh")
        FieldValue.objects.create(
            organization=club, definition=eigenes, person=erika.person, value="42"
        )
        MemberPhoto.objects.create(
            organization=club,
            membership=erika,
            image=ContentFile(JPEG, name="erika.jpg"),
            thumbnail=ContentFile(JPEG, name="erika-klein.jpg"),
            status=MemberPhoto.Status.APPROVED,
        )
        HonoraryTitle.objects.create(organization=club, name="Ehrenmitglied")
        zug = Department.objects.create(
            self_managed=True, organization=club, name="1. Zug", founding_year=1950
        )
        Folder.objects.create(
            organization=club, department=zug, name="Zugakten", public_key=uuid.uuid4().hex
        )
        Folder.objects.create(organization=club, name="Vereinsakten", public_key=uuid.uuid4().hex)
    return {"fed": fed, "club": club, "erika": erika}


def _club(doc, club_id):
    return next(c for c in doc["organization"]["clubs"] if c["id"] == club_id)


def test_export_nur_im_umfang_des_zeilenschutzes(verband):
    fed, club = verband["fed"], verband["club"]
    content, _name, _counts = dump.export_organization(fed, with_files=True, by_platform=False)
    doc = as_doc(content)
    data = _club(doc, club.pk)
    # Jede exportierte Zeile des Vereins sieht der Dachverband auch unter dem Zeilenschutz
    exported = {
        Membership: {m["id"] for m in data["memberships"]},
        Department: {d["id"] for d in data["departments"]},
        MemberType: {t["id"] for t in data["member_types"]},
    }
    with app_role():
        set_rls(fed.pk, None, scope_id=fed.pk, fed_access="read")
        for model, ids in exported.items():
            assert ids, model
            visible = set(model.objects.filter(pk__in=ids).values_list("pk", flat=True))
            assert ids == visible, model
        assert not Folder.objects.filter(organization=club).exists()  # Ablage: unsichtbar
        set_rls()
    # Tabellen der Fachmodule (Ablage, Versammlungen, Aufgaben, Satzung …) entfallen ganz
    assert not data.get("tables")
    assert all(not d.get("tables") for d in data["departments"])
    # Was entfällt
    assert all(m["photo"] is None for m in data["memberships"])
    assert data["fields"] == []
    assert data["role_assignments"] == [] and data["roles"] == []
    assert data["letterhead"] is None and data["contact_role"] is None
    assert all(d["roles"] == [] and d["letterhead"] is None for d in data["departments"])
    assert all(m["department_roles"] == [] for m in data["memberships"])
    values = [v for p in doc["persons"] for v in p["field_values"]]
    assert values == []
    assert "vorstand-umfang@example.org" not in json.dumps(data)


def test_plattform_bekommt_weiter_alles(verband):
    fed, club = verband["fed"], verband["club"]
    content, _name, _counts = dump.export_organization(fed, with_files=True, by_platform=True)
    data = _club(as_doc(content), club.pk)
    assert any(m["photo"] for m in data["memberships"])
    assert [f["key"] for f in data["fields"]] == ["schuh"]
    assert data["role_assignments"] and data["roles"]
    assert "members.honorarytitle" in (data.get("tables") or {})
    assert "documents.folder" in (data.get("tables") or {}) or any(
        "documents.folder" in (d.get("tables") or {}) for d in data["departments"]
    )
    with rls_bypass():
        assert Membership.objects.filter(organization=club).exists()
