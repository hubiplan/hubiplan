"""Mein Bereich › Musik nur für aktive Musiker (Menüprüfung 2, N-09)."""

import pytest

from core.tenancy import tenant_context

from .factories import make_member, make_org, make_user

pytestmark = pytest.mark.django_db


def test_musiker_flag_im_mitgliederbereich(api):
    from music.models import Musician
    from portal.models import PortalAccess

    org = make_org("Kapelle Muster", member_portal_enabled=True)
    org.enabled_modules = sorted({*org.enabled_modules, "events", "music"})
    org.save()
    user = make_user("musikerin@example.org")
    membership = make_member(org, "Erika", "Muster", user.email)
    with tenant_context(org.pk):
        PortalAccess.objects.create(organization=org, membership=membership, user=user)
    client = api(user)
    summary = client.get("/api/me/contexts/").json()["portal"][0]
    assert summary["musician"] is False

    with tenant_context(org.pk):
        Musician.objects.create(organization=org, membership=membership)
    summary = client.get("/api/me/contexts/").json()["portal"][0]
    assert summary["musician"] is True

    org.enabled_modules = [m for m in org.enabled_modules if m != "music"]
    org.save()
    summary = client.get("/api/me/contexts/").json()["portal"][0]
    assert summary["musician"] is False
