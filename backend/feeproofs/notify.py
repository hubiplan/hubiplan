"""Erinnerungen, Mitteilungen und Entscheidungen per Mail (täglicher Lauf).

Je Mitglied, Ermäßigung und Beitragsjahr höchstens einmal je Art (``ProofNotice``):

- erste Erinnerung am eingestellten Tag (Vorgabe 15.01.), solange die Frist läuft,
- zweite Erinnerung so viele Tage vor der Frist (Vorgabe 14),
- nach Frist und Kulanzzeit die Mitteilung „normaler Beitrag“ (abschaltbar), höchstens
  30 Tage danach (beim Einschalten der Funktion keine Nachrichten für alte Jahre).

Erinnert wird nur, wer für das Jahr noch keinen Nachweis eingereicht hat (Stand ``open``).
Jede Erinnerung enthält einen persönlichen Link zum Hochladen ohne Zugang und eine persönliche
Antwortadresse: Wer mit der Bescheinigung im Anhang antwortet, ist damit fertig.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import date_text, language_of_org
from core.tenancy import rls_bypass, tenant_context
from outbox import mail

from . import services
from .models import DiscountAssignment, FeeProof, ProofDiscount, ProofLink, ProofNotice

logger = logging.getLogger(__name__)

AFTER_DAYS = 30
LINK_EXTRA_DAYS = 60
KEY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
KEY_LENGTH = 12


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link_url(org, token: str) -> str:
    from organizations.addresses import base_url

    return f"{base_url(org)}/nachweis/{token}"


def reply_address(key: str) -> str:
    """Persönliche Antwortadresse (leer ohne Postfach)."""
    from billing.incoming_mail import mailbox_address

    base = mailbox_address()
    if "@" not in base:
        return ""
    local, domain = base.split("@", 1)
    return f"{local}+nw{key}@{domain}"


def new_link(membership, discount: ProofDiscount, year: int, until: datetime.date):
    """Neuer Link: (Link, Geheimnis). Gespeichert wird nur die Prüfsumme."""
    for _attempt in range(5):
        token = secrets.token_urlsafe(24)
        key = "".join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_LENGTH))
        try:
            with transaction.atomic():
                link = ProofLink.objects.create(
                    organization=membership.organization,
                    membership=membership,
                    discount=discount,
                    year=year,
                    token_hash=digest(token),
                    mail_key=key,
                    valid_until=until,
                )
            return link, token
        except IntegrityError:
            continue
    raise RuntimeError("Keine freie Kennung für den Nachweis-Link gefunden.")


def _greeting(membership) -> str:
    return _("Hallo {name},").format(name=membership.person.first_name)


def reminder_text(st: services.YearState, membership, url: str, reply: str, second: bool):
    org = membership.organization
    label = org.fiscal_label(st.year)
    subject = (
        _("Erinnerung: Nachweis für „{name}“ {year} bis {day}")
        if second
        else _("Nachweis für „{name}“ {year} bis {day}")
    ).format(name=st.discount.name, year=label, day=date_text(st.dates.due))
    lines = [
        _greeting(membership),
        "",
        _(
            "für die Ermäßigung „{name}“ brauchen wir jedes Jahr einen aktuellen Nachweis. "
            "Für {year} fehlt er noch. Bitte reiche ihn bis {day} ein."
        ).format(name=st.discount.name, year=label, day=date_text(st.dates.due)),
    ]
    if st.discount.kinds:
        lines += ["", _("Als Nachweis zählt zum Beispiel:")]
        lines += [f"- {k}" for k in st.discount.kinds]
    lines += ["", _("So geht es am einfachsten:")]
    if reply:
        lines.append(_("- Antworte auf diese Mail und hänge die Bescheinigung (PDF oder Foto) an."))
    lines.append(_("- Oder lade sie hier hoch: {url}").format(url=url))
    lines.append(_("- Oder im Mitgliederbereich bzw. in der App unter „Beitragsnachweise“."))
    if st.discount.grace_days:
        lines += [
            "",
            _(
                "Wer es nicht rechtzeitig schafft, kann den Nachweis noch bis {day} nachreichen."
            ).format(day=date_text(st.dates.final)),
        ]
    lines += [
        "",
        _(
            "Ohne Nachweis gilt für {year} der normale Beitrag. Studierst du nicht mehr oder "
            "fallen die Voraussetzungen weg, musst du nichts tun."
        ).format(year=label),
        "",
        org.name,
    ]
    return subject, "\n".join(lines) + "\n"


def after_text(st: services.YearState, membership):
    org = membership.organization
    label = org.fiscal_label(st.year)
    subject = _("Kein Nachweis für „{name}“ {year}: normaler Beitrag").format(
        name=st.discount.name, year=label
    )
    lines = [
        _greeting(membership),
        "",
        _(
            "für die Ermäßigung „{name}“ ist bis {day} kein Nachweis für {year} bei uns "
            "eingegangen. Nach der Beitragsordnung gilt deshalb für {year} der normale Beitrag."
        ).format(name=st.discount.name, day=date_text(st.dates.final), year=label),
        "",
        _(
            "Für das nächste Jahr kannst du die Ermäßigung wieder mit einem Nachweis "
            "bekommen. Hast du Fragen, melde dich gern beim Vorstand."
        ),
        "",
        org.name,
    ]
    return subject, "\n".join(lines) + "\n"


def decision_text(proof: FeeProof):
    membership = proof.membership
    org = membership.organization
    label = org.fiscal_label(proof.year)
    name = proof.discount.name
    if proof.status == FeeProof.Status.ACCEPTED:
        subject = _("Nachweis für „{name}“ {year} anerkannt").format(name=name, year=label)
        body = _("dein Nachweis für die Ermäßigung „{name}“ {year} ist anerkannt. Danke!").format(
            name=name, year=label
        )
    elif proof.status == FeeProof.Status.REJECTED:
        subject = _("Nachweis für „{name}“ {year} nicht anerkannt").format(name=name, year=label)
        body = _(
            "dein Nachweis für die Ermäßigung „{name}“ {year} konnten wir leider nicht "
            "anerkennen. Grund: {note}"
        ).format(name=name, year=label, note=proof.note)
    else:
        subject = _("Rückfrage zu deinem Nachweis für „{name}“ {year}").format(
            name=name, year=label
        )
        body = _(
            "zu deinem Nachweis für die Ermäßigung „{name}“ {year} haben wir eine Rückfrage: "
            "{note}\n\nDu kannst im Mitgliederbereich, in der App oder über den Link aus der "
            "Erinnerung einen weiteren Nachweis einreichen."
        ).format(name=name, year=label, note=proof.note)
    return subject, "\n".join([_greeting(membership), "", body, "", org.name]) + "\n"


def decision(proof: FeeProof) -> None:
    """Mitglied über die Entscheidung informieren (nach dem Speichern)."""
    from events.rsvp import email_of

    if proof.status not in (
        FeeProof.Status.ACCEPTED,
        FeeProof.Status.REJECTED,
        FeeProof.Status.QUESTION,
    ):
        return
    membership = proof.membership
    org = membership.organization

    def send():
        # Auch nach Einreichen über Link oder Mail (ohne Sitzung): nur Daten dieses Mitglieds
        with rls_bypass():
            address = email_of(membership)
            if not address:
                return
            with language_of_org(org):
                subject, body = decision_text(proof)
            mail.send(address, subject, body, organization=org, kind="nachweis", fail_silently=True)

    transaction.on_commit(send)


# --- täglicher Lauf ---


def _due_kind(st: services.YearState, on: datetime.date, org) -> str | None:
    discount = st.discount
    if st.state == services.OPEN:
        second_day = (
            st.dates.due - datetime.timedelta(days=discount.remind_before_days)
            if discount.remind_before_days is not None
            else None
        )
        if second_day is not None and second_day <= on <= st.dates.final:
            return ProofNotice.Kind.SECOND
        first_day = services.first_reminder(org, discount, st.year)
        if st.dates.late_start:
            # Später begonnen: erste Erinnerung gleich zu Beginn der eigenen Frist
            first_day = st.dates.due - datetime.timedelta(days=discount.late_join_days)
        if first_day is not None and first_day <= on <= st.dates.due:
            return ProofNotice.Kind.FIRST
        return None
    if (
        st.state == services.MISSING
        and discount.notify_after
        and st.dates.final < on <= st.dates.final + datetime.timedelta(days=AFTER_DAYS)
    ):
        return ProofNotice.Kind.AFTER
    return None


def _send_one(st: services.YearState, membership, kind: str, now) -> bool:
    from events.rsvp import email_of

    org = membership.organization
    try:
        with transaction.atomic():
            ProofNotice.objects.create(
                organization=org,
                membership=membership,
                discount=st.discount,
                year=st.year,
                kind=kind,
            )
    except IntegrityError:
        return False  # schon verschickt
    if kind == ProofNotice.Kind.SECOND:
        # Die erste Erinnerung ist damit überholt und kommt nicht mehr hinterher
        ProofNotice.objects.get_or_create(
            organization=org,
            membership=membership,
            discount=st.discount,
            year=st.year,
            kind=ProofNotice.Kind.FIRST,
        )
    address = email_of(membership)
    if not address:
        return False
    with language_of_org(org):
        if kind == ProofNotice.Kind.AFTER:
            subject, body = after_text(st, membership)
            reply_to = None
        else:
            until = st.dates.final + datetime.timedelta(days=LINK_EXTRA_DAYS)
            link, token = new_link(membership, st.discount, st.year, until)
            reply = reply_address(link.mail_key)
            subject, body = reminder_text(
                st, membership, link_url(org, token), reply, kind == ProofNotice.Kind.SECOND
            )
            reply_to = [reply] if reply else None
    return bool(
        mail.send(
            address,
            subject,
            body,
            organization=org,
            kind="nachweis",
            reply_to=reply_to,
            fail_silently=True,
        )
    )


def run(now=None) -> int:
    from members.models import Membership
    from organizations.models import Organization

    now = now or timezone.now()
    on = timezone.localdate(now)
    sent = 0
    with rls_bypass():
        org_ids = sorted(
            set(
                ProofDiscount.objects.filter(is_archived=False).values_list(
                    "organization_id", flat=True
                )
            )
        )
    for org_id in org_ids:
        with rls_bypass():
            org = Organization.objects.get(pk=org_id)
        if not services.module_on(org):
            continue
        with tenant_context(org_id):
            member_ids = sorted(
                set(
                    DiscountAssignment.objects.filter(
                        organization=org, discount__is_archived=False
                    ).values_list("membership_id", flat=True)
                )
            )
            for membership in Membership.objects.filter(
                pk__in=member_ids, purged_at__isnull=True
            ).select_related("person", "organization"):
                if membership.current_period(on) is None:
                    continue
                for st in services.requirements(membership, on):
                    kind = _due_kind(st, on, org)
                    if kind is None:
                        continue
                    try:
                        sent += int(_send_one(st, membership, kind, now))
                    except Exception:  # noqa: BLE001 - ein Mitglied hält die anderen nicht auf
                        logger.exception("Beitragsnachweis: Mail an %s gescheitert", membership.pk)
    logger.info("Beitragsnachweise: %s Mails", sent)
    return sent


def cleanup(now=None) -> dict:
    """Abgelaufene Links und alte Hinweise löschen; Dateien unentschiedener Nachweise nach
    einem Jahr entfernen (Datensparsamkeit)."""
    now = now or timezone.now()
    on = timezone.localdate(now)
    with rls_bypass():
        links = ProofLink.objects.filter(valid_until__lt=on).delete()[0]
        notices = ProofNotice.objects.filter(
            sent_at__lt=now - datetime.timedelta(days=3 * 366)
        ).delete()[0]
        stale = 0
        for proof in FeeProof.objects.filter(
            created_at__lt=now - datetime.timedelta(days=366),
            file_deleted_at__isnull=True,
        ).exclude(file=""):
            services.drop_file(proof)
            proof.save(update_fields=["file", "file_deleted_at"])
            stale += 1
    return {"links": links, "notices": notices, "files": stale}
