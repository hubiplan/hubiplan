"""Schnittstellenfassungen des Verbunds.

1: Grundfassung. 2: Organisationsmitglieder (Firma, Verein, Behörde …) in den Paketen
„members“ und „unit_members“ (Konzept juristische Personen, J6). Eine Gegenstelle, die 2
nicht meldet, bekommt keine Organisationsmitglieder; ihr fehlte sonst das Pflicht-Geburtsdatum.
"""

API_VERSIONS = [1, 2]
ORGANIZATIONS = 2


def supports_organizations(peer) -> bool:
    return ORGANIZATIONS in (getattr(peer, "versions", None) or [])


def withheld_organizations(coupling) -> int:
    """Organisationsmitglieder, die diese Seite der Gegenstelle nicht schickt (zu alt)."""
    from core.tenancy import tenant_context
    from members.models import Membership, PersonKind

    from .models import Coupling

    if coupling.direction != Coupling.Direction.PARENT or supports_organizations(coupling.peer):
        return 0
    with tenant_context(coupling.local_unit_id):
        return Membership.objects.filter(
            organization_id=coupling.local_unit_id,
            person__kind=PersonKind.ORGANIZATION,
            purged_at__isnull=True,
        ).count()
