"""Geschäftspartner P5 (Konzept geschaeftspartner.md): Verträge mit Kündigungsfrist,
Dokumente an der Akte und Serienbrief an Partnergruppen."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from billing.models import PartnerDocument
from core.tenancy import tenant_context
from todos.models import Todo

from .test_geschaeftspartner import JSON, base, c, club, create  # noqa: F401
from .test_geschaeftspartner_sponsoring import with_todos  # noqa: F401

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def test_vertrag_erinnert_vor_der_kuendigungsfrist(c, base, with_todos):
    partner = create(c, base, roles=["service"])
    response = c.post(
        f"{base}{partner['id']}/agreements/",
        {
            "kind": "contract",
            "title": "Wartung Schießstand",
            "start": "2026-01-01",
            "end": "2026-12-31",
            "notice_days": 90,
            "auto_renew": True,
            "remind_days": 30,
        },
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["notice_by"] == "2026-10-02"
    assert data["reminder_due"] == "2026-09-02"
    with tenant_context(with_todos.pk):
        assert "kündigen" in Todo.objects.get(pk=data["reminder"]).title


def test_dokumente_an_der_akte(c, base, club):
    partner = create(c, base)
    docs = f"{base}{partner['id']}/documents/"
    upload = SimpleUploadedFile("vertrag.pdf", PDF, content_type="application/pdf")
    response = c.post(docs, {"file": upload, "title": "Wartungsvertrag"})
    assert response.status_code == 201, response.content
    doc = response.json()
    assert doc["title"] == "Wartungsvertrag" and doc["name"] == "vertrag.pdf"
    assert [d["id"] for d in c.get(docs).json()] == [doc["id"]]
    # Mit Dokument lässt sich der Partner nicht löschen
    assert c.delete(f"{base}{partner['id']}/").status_code == 400
    assert c.delete(f"{docs}{doc['id']}/").status_code == 204
    with tenant_context(club.pk):
        assert not PartnerDocument.objects.exists()


def test_dokument_eines_fremden_partners_nicht_erreichbar(c, base):
    one = create(c, base)
    other = create(c, base, name="Andere GmbH")
    upload = SimpleUploadedFile("angebot.pdf", PDF, content_type="application/pdf")
    doc = c.post(f"{base}{one['id']}/documents/", {"file": upload}).json()
    assert c.get(f"{base}{other['id']}/documents/{doc['id']}/").status_code == 404


def test_serienbrief_und_verteiler(c, base):
    a = create(c, base, name="Sponsor A", roles=["sponsor"])
    c.patch(
        f"{base}{a['id']}/",
        {"details": {"street": "Musterweg 1", "postcode": "12345", "city": "Musterstadt"}},
        content_type=JSON,
    )
    c.post(
        f"{base}{a['id']}/contacts/",
        {"last_name": "Muster", "email": "kim@example.org"},
        content_type=JSON,
    )
    create(c, base, name="Sponsor ohne Anschrift", roles=["sponsor"])
    create(c, base, name="Lieferant", roles=["supplier"])
    rows = c.get(f"{base}mailing/?role=sponsor").json()
    assert [(r["name"], r["emails"], r["has_address"]) for r in rows] == [
        ("Sponsor A", ["kim@example.org"], True),
        ("Sponsor ohne Anschrift", [], False),
    ]
    letter = c.post(
        f"{base}mailing/",
        {"role": "sponsor", "subject": "Einladung Schützenfest", "text": "Wir laden ein."},
        content_type=JSON,
    )
    assert letter.status_code == 200, letter.content
    assert letter.content.startswith(b"%PDF")
    none = c.post(
        f"{base}mailing/",
        {"role": "press", "subject": "X", "text": "Y"},
        content_type=JSON,
    )
    assert none.status_code == 400
