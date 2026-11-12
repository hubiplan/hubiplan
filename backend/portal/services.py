"""Wer hat welchen Zugang? Anmeldelinks und Einladungen."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import APIException, ValidationError

from access.catalog import effective_for
from access.models import RoleAssignment
from accounts.models import User
from core.i18n import language_of, user_language
from core.tenancy import tenant_context, user_view
from members.models import DepartmentRoleHolder, Membership, today
from members.services import contact_for
from organizations.addresses import base_url
from organizations.models import Department, Organization
from organizations.platform_public import instance_name
from organizations.tree import UnitTree
from outbox import mail

from .models import LoginLink, PortalAccess, hash_token

# Vom Verein verschickte Links (Einladung) gelten 7 Tage, selbst angeforderte eine Stunde
# (Gesamtaudit 11.11., Fachfrage 3). Ein neuer Link entwertet die älteren offenen Links.
LINK_DAYS = 7
SELF_LINK_HOURS = 1

# Felder, die ein Mitglied als Änderung melden darf
# Kontaktdaten ändern Mitglieder direkt (außer der Verein verlangt Bestätigung);
# Name, Geburtsdatum und Geschlecht bestätigt immer der Verein.
DIRECT_FIELDS = ("email", "phone", "street", "postal_code", "city", "country")

CHANGEABLE_FIELDS = (
    "last_name",
    "first_name",
    "birth_date",
    "gender",
    "email",
    "phone",
    "street",
    "postal_code",
    "city",
    "country",
)


@dataclass
class DepartmentContext:
    department: Department
    club: Organization
    membership_id: int
    permissions: set[str] = field(default_factory=set)


def accesses_of(user) -> list[PortalAccess]:
    if not user.is_authenticated:
        return []
    return list(
        PortalAccess.objects.filter(user=user, organization__is_active=True).select_related(
            "organization", "organization__parent"
        )
    )


def _is_current(membership: Membership, on: datetime.date) -> bool:
    return membership.current_period(on) is not None


def department_contexts(user) -> dict[int, DepartmentContext]:
    """Abteilungen, in denen der Benutzer über eine Abteilungsrolle Rechte hat."""
    result: dict[int, DepartmentContext] = {}
    on = today()
    for access in accesses_of(user):
        club = access.organization
        if club.type != Organization.Type.CLUB or not club.department_access_enabled:
            continue
        with tenant_context(club.pk, user.pk):
            membership = Membership.objects.filter(pk=access.membership_id).first()
            if membership is None or not _is_current(membership, on):
                continue
            holders = (
                DepartmentRoleHolder.objects.filter(
                    membership=membership,
                    valid_from__lte=on,
                    role__department__is_active=True,
                    # Von oben verwaltete Untereinheiten: ihre Rollen sind reine Ämter
                    role__department__self_managed=True,
                )
                .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
                .select_related("role__department")
            )
            for holder in holders:
                perms = effective_for(holder.role.permissions, club, dept=True)
                if not perms:
                    continue
                dept = holder.role.department
                ctx = result.setdefault(
                    dept.pk, DepartmentContext(dept, club, membership.pk, set())
                )
                ctx.permissions |= perms
            # Eine Rolle gilt auch für alle Untereinheiten darunter
            tree = UnitTree.of(club.pk)
            for dept_id, ctx in list(result.items()):
                if ctx.club.pk != club.pk:
                    continue
                for sub_id in tree.subtree(dept_id)[1:]:
                    if not tree.nodes[sub_id].is_active:
                        continue
                    sub = result.get(sub_id)
                    if sub is None:
                        sub = result[sub_id] = DepartmentContext(
                            Department.objects.get(pk=sub_id), club, membership.pk, set()
                        )
                    sub.permissions |= ctx.permissions
    # Pflicht-2FA: Rollenverwaltung ruht nach der Übergangsfrist ohne zweiten Faktor
    from accounts.mfa_policy import gate

    for ctx in result.values():
        ctx.permissions = gate(user, ctx.permissions)
    return result


def portal_accesses(user) -> list[PortalAccess]:
    """Mitgliedschaften, die der Benutzer im Mitgliederbereich sehen darf."""
    return [
        a
        for a in accesses_of(user)
        if a.organization.type == Organization.Type.CLUB and a.organization.member_portal_enabled
    ]


def has_admin_access(user) -> bool:
    """Vorstand, Plattform oder Abteilungsrolle: Anmeldung nur mit Passwort (und 2FA)."""
    if user.is_superuser or user.is_staff:
        return True
    # Immer mit Blick auf genau dieses Konto: Bei der Anmeldung (Anmeldelink, Verbund) ist
    # noch niemand angemeldet, und unter RLS wären die Rollen sonst unsichtbar (AT-S01).
    with user_view(user.pk):
        if RoleAssignment.objects.active().filter(user=user).exists():
            return True
        return bool(department_contexts(user))


def uses_mfa(user) -> bool:
    from allauth.mfa.models import Authenticator

    return Authenticator.objects.filter(user=user).exists()


def link_login_allowed(user) -> bool:
    return user.is_active and not uses_mfa(user) and not has_admin_access(user)


# --- Zugang einrichten ---


def member_email(club: Organization, membership: Membership) -> str:
    contact = contact_for(membership.person, club)
    if not contact or not contact.email:
        raise ValidationError(gettext("Für dieses Mitglied ist keine E-Mail-Adresse hinterlegt."))
    return contact.email.lower()


class TransferNeeded(APIException):
    """Zugang hängt an einer anderen Adresse (409): nur ausdrücklich übertragen."""

    status_code = 409
    default_code = "transfer_needed"


TRANSFER_NEEDED = (
    "Das Mitglied hat schon einen Zugang mit {old}. Eine neue E-Mail-Adresse überträgt ihn "
    "nicht von selbst: Bitte „Zugang auf neue Adresse übertragen“ wählen."
)


def contact_email(club: Organization, contact) -> str:
    """E-Mail-Adresse eines Ansprechpartners (verknüpft: aus seiner Akte)."""
    if contact.person_id is not None:
        linked = contact_for(contact.person, club)
        email = linked.email if linked else ""
    else:
        email = contact.email
    if not email:
        raise ValidationError(
            gettext("Für diesen Ansprechpartner ist keine E-Mail-Adresse hinterlegt.")
        )
    return email.lower()


def contact_names(contact) -> tuple[str, str]:
    if contact.person_id is not None:
        return contact.person.first_name, contact.person.last_name
    return contact.first_name, contact.last_name


def ensure_access(
    club: Organization,
    membership: Membership,
    created_by,
    transfer: bool = False,
    contact=None,
) -> PortalAccess:
    """Legt den Zugang an.

    Gibt es schon einen Zugang mit einer anderen Adresse, wird er nur mit ``transfer``
    auf die neue Adresse übertragen (FQ-15): die alte Adresse bekommt eine Mitteilung.
    Bei Organisationsmitgliedern bekommt jeder Ansprechpartner (``contact``) einen eigenen
    Zugang; die Organisation selbst hat keinen (J5).
    """
    if contact is None and membership.person.is_organization:
        raise ValidationError(
            gettext("Bei Organisationen bekommt jeder Ansprechpartner einen eigenen Zugang.")
        )
    if contact is not None:
        email = contact_email(club, contact)
        first_name, last_name = contact_names(contact)
    else:
        email = member_email(club, membership)
        first_name, last_name = membership.person.first_name, membership.person.last_name
    access = (
        PortalAccess.objects.filter(membership=membership, contact_person=contact)
        .select_related("user")
        .first()
    )
    if access is not None and access.user.email.lower() != email and not transfer:
        raise TransferNeeded(TRANSFER_NEEDED.format(old=access.user.email))
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(email=email, password=None)
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=["first_name", "last_name"])
    if access is None:
        access = PortalAccess.objects.create(
            organization=club,
            membership=membership,
            contact_person=contact,
            user=user,
            created_by=created_by,
        )
    elif access.user_id != user.pk:
        old_user = access.user
        access.user = user
        access.save(update_fields=["user"])
        _notify_transfer(club, membership, old_user, email, first_name)
    if contact is not None and not contact.member_access:
        contact.member_access = True
        contact.save(update_fields=["member_access", "updated_at"])
    return access


def _notify_transfer(
    club: Organization, membership: Membership, old_user, new: str, first_name: str = ""
) -> None:
    """Mitteilung an die bisherige Adresse: ohne Link und ohne die neue Adresse ganz."""
    old = old_user.email
    local, _, domain = new.partition("@")
    hint = f"{local[:1]}…@{domain}"
    with language_of(old_user):
        subject = gettext("Ihr Zugang zu {instanz} – {org} wurde übertragen").format(
            instanz=instance_name(), org=club.name
        )
        body = (
            gettext("Hallo {name},").format(name=first_name or membership.person.first_name)
            + "\n\n"
            + gettext(
                "{org} hat Ihren Zugang zum Mitgliederbereich auf eine neue E-Mail-Adresse "
                "({hint}) übertragen. Mit dieser Adresse ({old}) ist der Zugang zu Ihrer "
                "Mitgliedschaft nicht mehr möglich."
            ).format(org=club.name, hint=hint, old=old)
            + "\n\n"
            + gettext(
                "Wenn Sie das nicht veranlasst haben, wenden Sie sich bitte an {org}."
            ).format(org=club.name)
            + "\n"
        )
    mail.send(
        old,
        subject,
        body,
        organization=club,
        kind="zugang",
        language=user_language(old_user),
    )


def create_login_link(user, organization=None, created_by=None) -> str:
    """Neuer Anmeldelink; ohne Verein (selbst angefordert) gilt er eine Stunde.

    Ältere offene Links des Kontos laufen dabei sofort ab, damit höchstens einer gilt.
    """
    from core.tenancy import rls_bypass

    now = timezone.now()
    if organization is None:
        valid = datetime.timedelta(hours=SELF_LINK_HOURS)
    else:
        valid = datetime.timedelta(days=LINK_DAYS)
    token = LoginLink.new_token()
    with rls_bypass():
        LoginLink.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).update(
            expires_at=now
        )
    LoginLink.objects.create(
        user=user,
        organization=organization,
        token_hash=hash_token(token),
        created_by=created_by,
        expires_at=now + valid,
    )
    return f"{base_url(organization)}/anmelden/link/{token}"


def send_access_mail(club: Organization, access: PortalAccess, created_by) -> str:
    """Schickt einen Anmeldelink – oder, wenn das Konto mehr darf, nur einen Hinweis.

    Gibt die Art zurück: "link" oder "password" (Anmeldung mit dem bestehenden Konto).
    """
    user = access.user
    if access.contact_person_id is not None:
        first_name = contact_names(access.contact_person)[0] or access.contact_person.display_name
    else:
        first_name = access.membership.person.first_name
    link = link_login_allowed(user)
    url = create_login_link(user, club, created_by) if link else ""
    with language_of(user):
        greeting = gettext("Hallo {name},").format(name=first_name) + "\n\n"
        if link:
            body = (
                greeting
                + (
                    gettext(
                        "{org} lädt Sie als Ansprechpartner von {member} in den "
                        "Mitgliederbereich von {instanz} ein. Dort sehen Sie die Daten der "
                        "Mitgliedschaft und können Änderungen melden."
                    ).format(
                        org=club.name,
                        member=access.membership.person.display_name,
                        instanz=instance_name(),
                    )
                    if access.contact_person_id is not None
                    else gettext(
                        "{org} lädt Sie in den Mitgliederbereich von {instanz} ein. Dort sehen "
                        "Sie Ihre Daten und können Änderungen melden."
                    ).format(org=club.name, instanz=instance_name())
                )
                + "\n\n"
                + gettext(
                    "Mit diesem persönlichen Link melden Sie sich ohne Passwort an "
                    "(gültig {days} Tage, einmal nutzbar):"
                ).format(days=LINK_DAYS)
                + f"\n\n{url}\n\n"
                + gettext(
                    "Einen neuen Link können Sie jederzeit auf der Anmeldeseite anfordern. "
                    "Wenn Sie lieber ein Passwort nutzen, wählen Sie dort „Passwort vergessen“."
                )
                + "\n"
            )
        else:
            # Konten mit Verwaltungsrechten oder 2FA: kein Anmelde- oder Passwortlink aus dem
            # Mitgliederbereich heraus (die Mail läge im Postausgang der Einheit).
            body = (
                greeting
                + gettext(
                    "{org} hat Ihnen den Mitgliederbereich von {instanz} freigeschaltet."
                ).format(org=club.name, instanz=instance_name())
                + "\n\n"
                + gettext(
                    "Melden Sie sich wie gewohnt mit Ihrem bestehenden Konto ({email}) an: {url}"
                ).format(email=user.email, url=f"{base_url(club)}/anmelden")
                + "\n\n"
                + gettext(
                    "Falls Sie Ihr Passwort nicht kennen, wählen Sie dort „Passwort vergessen“."
                )
                + "\n"
            )
        subject = gettext("Ihr Zugang zu {instanz} – {org}").format(
            instanz=instance_name(), org=club.name
        )
    mail.send(
        user.email,
        subject,
        body,
        organization=club,
        kind="zugang",
        language=user_language(user),
    )
    kind = "link" if link else "password"
    return kind


def access_info(access: PortalAccess | None) -> dict | None:
    if access is None:
        return None
    return {
        "email": access.user.email,
        "created_at": access.created_at,
        "last_login": access.user.last_login,
        "login": "link" if link_login_allowed(access.user) else "password",
    }
