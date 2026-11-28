"""Push für die Verwaltung: Etwas Neues wartet unter „Zu erledigen“.

Anders als die Hinweise des Mitgliederbereichs (``push.notify_membership``) geht dieser Push an
Konten mit Rolle, auch ohne Mitgliederbereich. Er nennt nur die Art und die Einheit, keine
Namen und keine Beträge; gelesen wird erst in der freigeschalteten Verwaltung. Empfänger sind
Konten, die den Eintrag unter „Zu erledigen“ sehen dürfen (Recht in der Einheit, geprüft beim
Senden), und nur Geräte, auf denen der Schalter „Verwaltung“ an ist (``Device.admin_push``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_save
from django.utils.translation import gettext, gettext_noop

from access.catalog import FINANCE_EDIT, MEMBERS_EDIT, PHOTOS_MANAGE
from core.tenancy import rls_bypass, user_view

logger = logging.getLogger(__name__)

# Mehrere neue Einträge kurz nacheinander: je Konto und Einheit höchstens ein Push in dieser Zeit
QUIET_SECONDS = 120


@dataclass(frozen=True)
class Source:
    kind: str
    permission: str
    title: str
    # Modul, das in der Einheit eingeschaltet sein muss (leer: keines)
    module: str = ""
    # Wert von ``status``, mit dem ein neuer Eintrag auf eine Entscheidung wartet (leer: jeder)
    status: tuple[str, ...] = ()


# Modell („app.Modell“) → Anlass. Die Arten heißen wie unter „Zu erledigen“ (open_tasks).
SOURCES: dict[str, Source] = {
    "billing.IncomingInvoice": Source(
        "incoming_review",
        FINANCE_EDIT,
        gettext_noop("Neue Eingangsrechnung"),
        "finance",
        ("review",),
    ),
    "portal.ChangeRequest": Source(
        "change_request", MEMBERS_EDIT, gettext_noop("Neue Datenänderung"), "members", ("pending",)
    ),
    "portal.CancellationRequest": Source(
        "cancellation", MEMBERS_EDIT, gettext_noop("Neue Kündigung"), "members", ("pending",)
    ),
    "members.MemberPhoto": Source(
        "photo", PHOTOS_MANAGE, gettext_noop("Neues Foto zur Freigabe"), "members", ("pending",)
    ),
    "bookings.Booking": Source(
        "booking", "bookings.edit", gettext_noop("Neue Belegungsanfrage"), "", ("requested",)
    ),
}


# Anlässe ohne eigenes Signal: Die Fachlogik meldet sie mit ``announce`` (Mitgliedsantrag erst
# nach bestätigter E-Mail-Adresse, nicht schon beim Anlegen)
OTHER: dict[str, Source] = {
    "application": Source(
        "application", MEMBERS_EDIT, gettext_noop("Neuer Mitgliedsantrag"), "members"
    ),
}


def announce(org_id: int, kind: str, *, by_user_id: int | None = None) -> None:
    """Nach dem Speichern die Zuständigen der Einheit benachrichtigen.

    ``by_user_id``: Konto, das den Eintrag selbst angelegt hat; es bekommt keinen Hinweis.
    """
    if _source(kind) is None or not org_id:
        return
    transaction.on_commit(lambda: notify.delay(org_id, kind, by_user_id), robust=True)


def _on_created(sender, instance, created, **kwargs):
    if not created:
        return
    source = SOURCES.get(sender._meta.label)
    org_id = getattr(instance, "organization_id", None)
    if source is None or not org_id:
        return
    if source.status and str(getattr(instance, "status", "")) not in source.status:
        return
    # Belegung in einer Untereinheit entscheidet deren Leitung, nicht die Einheit
    if getattr(instance, "department_id", None):
        return
    announce(org_id, source.kind, by_user_id=getattr(instance, "created_by_id", None))


def connect() -> None:
    from django.apps import apps

    for label in SOURCES:
        model = apps.get_model(label)
        post_save.connect(_on_created, sender=model, dispatch_uid=f"devices-adminpush-{label}")


def _source(kind: str) -> Source | None:
    return next((s for s in (*SOURCES.values(), *OTHER.values()) if s.kind == kind), None)


def recipients(org, source: Source) -> list:
    """Konten mit dem Recht in der Einheit, die ein Gerät mit Push für die Verwaltung haben."""
    from access.models import RoleAssignment
    from access.permissions import own_permissions_in
    from accounts.mfa_policy import gate
    from accounts.models import User

    from .push import push_devices

    with rls_bypass():
        user_ids = set(
            RoleAssignment.objects.active()
            .filter(organization=org, user__is_active=True)
            .values_list("user_id", flat=True)
        )
        with_push = set(
            push_devices(user_ids).filter(admin_push=True).values_list("user_id", flat=True)
        )
        users = list(User.objects.filter(pk__in=with_push))
    result = []
    for user in users:
        # Rechte wie im Browser, in der Sicht genau dieses Kontos
        with user_view(user.pk):
            perms = gate(user, own_permissions_in(user, org))
        if source.permission in perms:
            result.append(user)
    return result


@shared_task
def notify(org_id: int, kind: str, by_user_id: int | None = None) -> int:
    """Hinweis an die Apps der Zuständigen; gibt die Zahl der erreichten Konten zurück."""
    from core.i18n import language_of
    from organizations.models import Organization

    from .push import send_to_user

    source = _source(kind)
    if source is None:
        return 0
    with rls_bypass():
        org = Organization.objects.filter(pk=org_id, is_active=True).first()
    if org is None or (source.module and source.module not in (org.enabled_modules or [])):
        return 0
    reached = 0
    for user in recipients(org, source):
        if user.pk == by_user_id:
            continue
        if not cache.add(f"app:adminpush:{user.pk}:{org.pk}", 1, QUIET_SECONDS):
            continue
        with language_of(user):
            title = gettext(source.title)
        data = {
            "v": 1,
            "t": "admin",
            "unit": org.pk,
            "kind": source.kind,
            "title": title,
            "text": org.name,
        }
        reached += int(send_to_user(user.pk, data, admin=True) > 0)
    return reached
