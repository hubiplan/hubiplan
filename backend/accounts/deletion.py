"""Benutzerkonten löschen (Gesamtaudit 15.11., PF-02/PF-23, Fachfrage FF-05 (c)).

Zwei Wege:

- **Selbst** über „Mein Konto“ (``DeleteAccountView``): sofort, nach Bestätigung.
- **Automatisch**, wenn ein Konto keinen Zugang mehr hat (kein Mitgliederzugang, keine
  laufende oder künftige Rolle, kein Superuser): ``ORPHAN_NOTICE_DAYS`` Tage danach eine
  Hinweismail, nach ``ORPHAN_DAYS`` Tagen die Löschung. Bekommt das Konto vorher wieder einen
  Zugang, beginnt die Frist neu.

Gelöscht wird das Konto samt allem, was nur an ihm hängt (Passkeys und Zwei-Faktor, E-Mail-
Adressen, Geräte mit Push-Adresse, Nextcloud- und KI-Freigaben, Anmeldungen über andere
Instanzen, gespeicherte Unterschrift, Briefbogen-Auswahl, Erinnerungen) und die persönlichen,
nicht geteilten Aufgaben. Was der Verein führt (Mitgliedsakte, Rechnungen, Protokoll), bleibt;
Verweise darauf, wer etwas angelegt oder bearbeitet hat, werden leer. Ämter mit Akte bleiben
in der Ämterchronik, ohne Konto.
"""

from __future__ import annotations

import datetime
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.tenancy import rls_bypass

logger = logging.getLogger(__name__)

ORPHAN_DAYS = 90
ORPHAN_NOTICE_DAYS = 76  # Hinweis zwei Wochen vor der Löschung


def _active_roles(on: datetime.date | None = None):
    from access.models import RoleAssignment

    on = on or timezone.localdate()
    # Laufende und künftige Ämter: Wer ab nächstem Monat Kassenwart wird, braucht das Konto
    return RoleAssignment.objects.filter(
        user__isnull=False, valid_until__isnull=True
    ) | RoleAssignment.objects.filter(user__isnull=False, valid_until__gte=on)


def with_access():
    """Konten mit Zugang: Superuser, Mitgliederzugang oder laufende bzw. künftige Rolle."""
    from portal.models import PortalAccess

    from .models import User

    return User.objects.filter(
        Q(is_superuser=True)
        | Q(is_staff=True)
        | Q(pk__in=PortalAccess.objects.values("user_id"))
        | Q(pk__in=_active_roles().values("user_id"))
    )


def blockers(user) -> list[str]:
    """Warum sich das Konto nicht selbst löschen lässt (leer: es geht)."""
    from django.utils.translation import gettext

    if user.is_superuser or user.is_staff:
        return [gettext("Plattform-Verwaltung")]
    with rls_bypass():
        names = sorted(
            {
                a.organization.name
                for a in _active_roles().filter(user=user).select_related("organization")
            }
        )
    return names


@transaction.atomic
def delete_account(user, *, reason: str) -> None:
    """Konto und alles, was nur an ihm hängt, endgültig löschen."""
    from access.models import RoleAssignment
    from changes.tracking import suppress
    from todos.models import Todo

    with suppress(), rls_bypass():
        # Persönliche Aufgaben (nicht geteilt) gehören nur der Person
        for todo in Todo.objects.filter(
            Q(owner=user) | Q(created_by=user), shared=False
        ).select_for_update():
            todo.delete()
        # Ämterchronik: Ämter mit Akte bleiben ohne Konto stehen; ohne Akte bliebe nur das
        # Konto als Inhaber, sie gehen mit ihm
        RoleAssignment.objects.filter(user=user).filter(
            Q(person__isnull=False) | Q(membership__isnull=False)
        ).update(user=None)
        user.delete()
    logger.info("Konto gelöscht (%s)", reason)


def orphan_run(now: datetime.datetime | None = None) -> dict[str, int]:
    """Täglich: verwaiste Konten vormerken, benachrichtigen und nach Frist löschen.

    Je Konto für sich: Ein Fehler hält die übrigen nicht auf."""
    from .models import User

    now = now or timezone.now()
    counts = {"vorgemerkt": 0, "benachrichtigt": 0, "geloescht": 0, "zurueck": 0, "fehler": 0}
    with rls_bypass():
        access = with_access().values("pk")
        # Wieder mit Zugang: Frist endet
        counts["zurueck"] = User.objects.filter(orphaned_since__isnull=False, pk__in=access).update(
            orphaned_since=None, deletion_notice_at=None
        )
        orphans = User.objects.exclude(pk__in=access)
        counts["vorgemerkt"] = orphans.filter(orphaned_since__isnull=True).update(
            orphaned_since=now
        )
        notice_before = now - datetime.timedelta(days=ORPHAN_NOTICE_DAYS)
        for user in orphans.filter(
            orphaned_since__lte=notice_before, deletion_notice_at__isnull=True
        ).order_by("pk"):
            try:
                _notify(user, user.orphaned_since + datetime.timedelta(days=ORPHAN_DAYS))
                User.objects.filter(pk=user.pk).update(deletion_notice_at=now)
                counts["benachrichtigt"] += 1
            except Exception:  # noqa: BLE001 – ein Konto darf die übrigen nicht aufhalten
                logger.exception("Hinweis zur Kontolöschung an Konto %s gescheitert", user.pk)
                counts["fehler"] += 1
        delete_before = now - datetime.timedelta(days=ORPHAN_DAYS)
        # Ohne Hinweis wird nie gelöscht; der Hinweis liegt mindestens 14 Tage zurück
        notice_due = now - datetime.timedelta(days=ORPHAN_DAYS - ORPHAN_NOTICE_DAYS)
        for user in orphans.filter(
            orphaned_since__lte=delete_before, deletion_notice_at__lte=notice_due
        ).order_by("pk"):
            try:
                delete_account(user, reason="ohne Zugang seit 90 Tagen")
                counts["geloescht"] += 1
            except Exception:  # noqa: BLE001
                logger.exception("Verwaistes Konto %s nicht gelöscht", user.pk)
                counts["fehler"] += 1
    return counts


def _notify(user, when: datetime.datetime) -> None:
    from django.utils.translation import gettext

    from core.i18n import date_text, language_of, user_language
    from organizations.platform_public import instance_name
    from outbox import mail

    with language_of(user):
        subject = gettext("Ihr Konto bei {instanz} wird gelöscht").format(instanz=instance_name())
        body = (
            gettext("Guten Tag,")
            + "\n\n"
            + gettext(
                "Ihr Konto {email} bei {instanz} hat seit drei Monaten keinen Zugang mehr zu "
                "einem Verein: kein Mitgliederzugang und keine Rolle. Am {datum} löschen wir "
                "es deshalb mit allen Kontodaten (Passkeys, verbundene Geräte, Freigaben, "
                "persönliche Aufgaben)."
            ).format(
                email=user.email,
                instanz=instance_name(),
                datum=date_text(timezone.localtime(when).date()),
            )
            + "\n\n"
            + gettext(
                "Was Ihr Verein über Sie als Mitglied führt, betrifft das nicht. Brauchen Sie "
                "das Konto weiter, bitten Sie Ihren Verein um einen Zugang; dann bleibt es."
            )
            + "\n"
        )
    mail.send(user.email, subject, body, kind="konto", language=user_language(user))


DEVICE_IDLE_DAYS = 180


def retire_idle_devices(now: datetime.datetime | None = None) -> int:
    """App-Geräte nach 180 Tagen ohne Nutzung abmelden und ihre Push-Adresse löschen
    (docs/aufbewahrung.md: „nach 180 Tagen ohne Nutzung abgemeldet“)."""
    from devices.models import Device

    now = now or timezone.now()
    with rls_bypass():
        return Device.objects.filter(
            revoked_at__isnull=True,
            last_seen_at__lt=now - datetime.timedelta(days=DEVICE_IDLE_DAYS),
        ).update(
            revoked_at=now,
            revoked_reason="180 Tage ohne Nutzung",
            push_kind=Device.Push.NONE,
            push_endpoint="",
            push_p256dh="",
            push_auth="",
        )
