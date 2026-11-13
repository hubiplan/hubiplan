"""Abläufe des Online-Antrags: einreichen, bestätigen, prüfen, zustimmen, annehmen, ablehnen.

Konzept: konzepte/online-beitrittsformular.md. Die Annahme ruft ``members.services.admit``
auf; Mandat und Einwilligungen entstehen erst dann. Alle Mails an den Antragsteller gehen in
der Sprache des Antrags.
"""

from __future__ import annotations

import datetime
import logging
import secrets

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from access.catalog import MEMBERS_EDIT
from access.models import RoleAssignment
from audit.log import record
from core.tenancy import rls_bypass, tenant_context
from organizations.addresses import base_url
from outbox.mail import send

from . import rules
from .models import (
    UNCONFIRMED_HOURS,
    Application,
    ApplicationEvent,
    ApplicationForm,
    Approval,
    KioskLink,
    hash_token,
)

KIND = "mitgliedsantrag"
CONSENT_PHOTO = "club_photo"  # nicht "photo": so heißt die Webseiten-Kategorie Foto
CONFIRM_STATUTE = "statute"
CONFIRM_FEE_RULES = "fee_rules"
CONFIRM_PRIVACY = "privacy"
CONFIRM_MANDATE = "mandate"
CONFIRM_GUARDIAN = "guardian"

logger = logging.getLogger(__name__)


def form_for(org) -> ApplicationForm:
    form = ApplicationForm.objects.filter(organization=org).first()
    if form is None:
        form = ApplicationForm.objects.create(
            organization=org, public_key=secrets.token_urlsafe(18)
        )
    return form


def text_of(form: ApplicationForm, key: str, language: str) -> str:
    texts = (form.texts or {}).get(key) or {}
    if not isinstance(texts, dict):
        return ""
    return (texts.get(language) or texts.get("de") or "").strip()


def event(app: Application, kind: str, user=None, note: str = "") -> None:
    ApplicationEvent.objects.create(
        organization_id=app.organization_id, application=app, kind=kind, user=user, note=note[:500]
    )


def links(app: Application, token: str) -> dict:
    base = f"{base_url(app.organization)}/antrag/{token}"
    return {
        "status": base,
        "confirm": f"{base}?bestaetigen=1",
        "withdraw": f"{base}?zurueckziehen=1",
    }


# --- Einreichen und bestätigen ---


def create(form: ApplicationForm, clean: dict, *, source: str = "web", kiosk=None) -> tuple:
    """Legt den Antrag an. Gibt (Antrag, Schlüssel für die Links) zurück."""
    token = secrets.token_urlsafe(24)
    app = Application.objects.create(
        organization=form.organization,
        source=source,
        language=clean["language"],
        kind=clean["kind"],
        data=clean["data"],
        member_type=clean["member_type"],
        unit=clean.get("unit"),
        entry_wish=clean.get("entry_wish"),
        mandate=clean.get("mandate") or {},
        consents=clean.get("consents") or [],
        guardians=clean.get("guardians") or [],
        signature=clean.get("signature") or {},
        signed_at=timezone.now() if clean.get("signature") else None,
        token_hash=hash_token(token),
    )
    event(
        app, "submitted", note=gettext("Stand: {label}").format(label=kiosk.label) if kiosk else ""
    )
    if source == Application.Source.KIOSK:
        # Am Stand ist der Vorstand dabei: keine E-Mail-Bestätigung (Ralf 12.11.)
        confirmed(app, token)
    else:
        send_confirmation(app, token)
    return app, token


def confirmation_email(app: Application) -> str:
    """Minderjährige: die Bestätigung geht an den ersten Erziehungsberechtigten (B3)."""
    if app.guardians:
        return (app.guardians[0] or {}).get("email") or app.email
    return app.email


def send_confirmation(app: Application, token: str) -> None:
    org = app.organization
    url = links(app, token)["confirm"]
    with translation.override(app.language):
        if app.guardians:
            intro = gettext(
                "für {name} wurde ein Mitgliedsantrag bei {org} gestellt. Sie sind als "
                "Erziehungsberechtigte(r) angegeben. Bitte bestätigen Sie den Antrag und Ihre "
                "Zustimmung über diesen Link (gültig {hours} Stunden):"
            ).format(name=app.display_name, org=org.name, hours=UNCONFIRMED_HOURS)
        else:
            intro = gettext(
                "vielen Dank für deinen Mitgliedsantrag bei {org}. Bitte bestätige deine "
                "E-Mail-Adresse über diesen Link (gültig {hours} Stunden):"
            ).format(org=org.name, hours=UNCONFIRMED_HOURS)
        body = (
            gettext("Guten Tag,")
            + "\n\n"
            + intro
            + f"\n\n{url}\n\n"
            + gettext(
                "Ohne Bestätigung wird der Antrag nach {hours} Stunden gelöscht. Hast du "
                "keinen Antrag gestellt, kannst du diese Mail einfach ignorieren."
            ).format(hours=UNCONFIRMED_HOURS)
            + "\n"
        )
        subject = gettext("Bitte Mitgliedsantrag bestätigen: {org}").format(org=org.name)
    send(
        [confirmation_email(app)],
        subject,
        body,
        organization=org,
        kind=KIND,
        fail_silently=True,
        language=app.language,
    )


def find(token: str) -> Application | None:
    if not token or len(token) > 100:
        return None
    with rls_bypass():
        return (
            Application.objects.select_related("organization", "member_type")
            .filter(token_hash=hash_token(token))
            .first()
        )


@transaction.atomic
def confirm(app: Application, token: str) -> Application:
    if app.status != Application.Status.UNCONFIRMED:
        return app
    confirmed(app, token)
    return app


def confirmed(app: Application, token: str) -> None:
    form = form_for(app.organization)
    app.confirmed_at = timezone.now()
    needs_signature = form.signature == ApplicationForm.Signature.REQUIRED and not app.signature
    app.status = Application.Status.UNSIGNED if needs_signature else Application.Status.OPEN
    app.save(update_fields=["confirmed_at", "status", "updated_at"])
    event(app, "confirmed")
    send_receipt(app, token, needs_signature)
    notify_board(app)


def send_receipt(app: Application, token: str, needs_signature: bool) -> None:
    org = app.organization
    form = form_for(org)
    url = links(app, token)
    with translation.override(app.language):
        lines = [
            gettext("Guten Tag,"),
            "",
            gettext("dein Mitgliedsantrag bei {org} ist eingegangen (Nummer {number}).").format(
                org=org.name, number=app.number
            ),
        ]
        thanks = text_of(form, "thanks", app.language)
        if thanks:
            lines += ["", thanks]
        if needs_signature:
            lines += [
                "",
                gettext(
                    "Der Verein braucht deine Unterschrift. Du kannst auf dieser Seite mit dem "
                    "Finger unterschreiben oder den Antrag als PDF ausdrucken, unterschreiben "
                    "und dem Verein schicken:"
                ),
                url["status"],
            ]
        lines += ["", gettext("Deine Angaben:"), *summary_lines(app)]
        lines += [
            "",
            gettext(
                "Den Stand deines Antrags siehst du hier; dort kannst du ihn auch zurückziehen:"
            ),
            url["status"],
        ]
        subject = gettext("Mitgliedsantrag eingegangen: {org}").format(org=org.name)
    send(
        [confirmation_email(app)],
        subject,
        "\n".join(lines) + "\n",
        organization=org,
        kind=KIND,
        fail_silently=True,
        language=app.language,
    )


def summary_lines(app: Application) -> list[str]:
    """Angaben als Text (ohne volle IBAN) für Mails und PDF."""
    d = app.data or {}
    rows = []
    if app.kind == "organization":
        rows.append((gettext("Organisation"), d.get("last_name", "")))
    else:
        rows.append((gettext("Name"), app.display_name))
        if d.get("birth_date"):
            rows.append((gettext("Geburtsdatum"), _date(d["birth_date"])))
    address = ", ".join(
        p
        for p in (
            d.get("street", ""),
            d.get("address_extra", ""),
            f"{d.get('postal_code', '')} {d.get('city', '')}".strip(),
        )
        if p
    )
    rows.append((gettext("Anschrift"), address))
    rows.append((gettext("E-Mail"), d.get("email", "")))
    if d.get("phone"):
        rows.append((gettext("Telefon"), d["phone"]))
    if app.member_type_id:
        rows.append((gettext("Mitgliedsart"), app.member_type.name))
    if app.unit_id:
        rows.append((gettext("Untereinheit"), app.unit.name))
    if app.entry_wish:
        rows.append((gettext("Gewünschter Eintritt"), app.entry_wish.strftime("%d.%m.%Y")))
    if d.get("company_name"):
        rows.append((gettext("Beitrag zahlt"), d["company_name"]))
    for f in d.get("family") or []:
        parts = [f"{f.get('first_name', '')} {f.get('last_name', '')}".strip()]
        if f.get("birth_date"):
            parts.append(_date(f["birth_date"]))
        if f.get("member_type_label"):
            parts.append(f["member_type_label"])
        rows.append((gettext("Weitere Person"), ", ".join(parts)))
    if app.mandate:
        from billing.sepa import masked_iban

        rows.append(
            (
                gettext("Lastschrift"),
                f"{app.mandate.get('holder', '')}, {masked_iban(app.mandate.get('iban', ''))}",
            )
        )
    for g in app.guardians or []:
        rows.append(
            (
                gettext("Erziehungsberechtigt"),
                f"{g.get('first_name', '')} {g.get('last_name', '')}".strip(),
            )
        )
    for item in (d.get("custom") or {}).items():
        rows.append(item)
    if d.get("note"):
        rows.append((gettext("Bemerkung"), d["note"]))
    return [f"{k}: {v}" for k, v in rows if v]


def _date(value) -> str:
    try:
        return datetime.date.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def board_recipients(org, form: ApplicationForm) -> list[str]:
    """Hinweismail: eingestellte Rollen oder alle mit Recht „Mitglieder bearbeiten“."""
    qs = RoleAssignment.objects.active().filter(
        organization=org, membership__isnull=True, user__isnull=False
    )
    if form.notify_roles:
        qs = qs.filter(role_id__in=form.notify_roles)
    emails = []
    for a in qs.select_related("role", "user"):
        if not form.notify_roles and MEMBERS_EDIT not in (a.role.permissions or []):
            continue
        if a.user.email and a.user.is_active:
            emails.append(a.user.email)
    # Wer nach der Regel zustimmen muss, erfährt es ebenfalls
    rule = form.rule or {}
    if rule.get("mode") == "rule" and (rule.get("roles") or rule.get("pool")):
        wanted = set(rule.get("roles") or []) | set(rule.get("pool") or [])
        for a in (
            RoleAssignment.objects.active()
            .filter(organization=org, role_id__in=wanted, user__isnull=False)
            .select_related("user")
        ):
            if a.user.email and a.user.is_active:
                emails.append(a.user.email)
    return sorted(set(emails))


def notify_board(app: Application) -> None:
    org = app.organization
    with tenant_context(org.pk):
        form = form_for(org)
        emails = board_recipients(org, form)
    if not emails:
        return
    url = f"{base_url(org)}/mitglieder/antraege/{app.pk}"
    body = (
        gettext("Neuer Mitgliedsantrag für {org}: {name} ({number}).").format(
            org=org.name, name=app.display_name, number=app.number
        )
        + "\n\n"
        + gettext("Zum Antrag:")
        + f"\n{url}\n"
    )
    send(
        emails,
        gettext("Neuer Mitgliedsantrag: {name}").format(name=app.display_name),
        body,
        organization=org,
        kind=KIND,
        fail_silently=True,
    )


@transaction.atomic
def withdraw(app: Application) -> Application:
    if app.status in Application.DONE_STATES:
        raise ValidationError(gettext("Über den Antrag ist schon entschieden."))
    app.status = Application.Status.WITHDRAWN
    app.decided_at = timezone.now()
    app.purge_after = purge_date(app)
    app.save(update_fields=["status", "decided_at", "purge_after", "updated_at"])
    event(app, "withdrawn")
    return app


def purge_date(app: Application) -> datetime.date:
    form = form_for(app.organization)
    return timezone.localdate() + relativedelta(months=form.purge_months or 1)


@transaction.atomic
def sign(app: Application, strokes) -> Application:
    """Unterschrift nachreichen (auf dem eigenen Gerät, nach der Bestätigung)."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    from finance import signature

    if app.status not in (Application.Status.UNSIGNED, Application.Status.UNCONFIRMED):
        raise ValidationError(gettext("Der Antrag braucht keine Unterschrift mehr."))
    try:
        app.signature = signature.normalize(strokes)
    except DjangoValidationError as exc:
        raise ValidationError({"signature": exc.messages}) from exc
    app.signed_at = timezone.now()
    fields = ["signature", "signed_at", "updated_at"]
    if app.status == Application.Status.UNSIGNED:
        app.status = Application.Status.OPEN
        fields.append("status")
    app.save(update_fields=fields)
    event(app, "signed")
    return app


# --- Prüfen und entscheiden (Vorstand) ---


def valid_approvals(app: Application):
    return app.approvals.all()


def state(app: Application, form: ApplicationForm) -> rules.State:
    names = rules.role_names(app.organization)
    return rules.evaluate(form.rule or {}, valid_approvals(app), names)


@transaction.atomic
def mark_signed(app: Application, user) -> Application:
    """Unterschriebenes Papier ist eingegangen."""
    if app.status != Application.Status.UNSIGNED:
        raise ValidationError(gettext("Der Antrag wartet nicht auf eine Unterschrift."))
    app.status = Application.Status.OPEN
    app.save(update_fields=["status", "updated_at"])
    event(app, "paper_signed", user)
    return app


def ask(app: Application, user, text: str) -> None:
    """Rückfrage per Mail; Antworten gehen an die fragende Person (Antwort-an)."""
    if app.status in Application.DONE_STATES or app.status == Application.Status.UNCONFIRMED:
        raise ValidationError(gettext("Für diesen Antrag ist keine Rückfrage möglich."))
    text = (text or "").strip()
    if len(text) < 5:
        raise ValidationError({"text": gettext("Bitte die Frage eingeben.")})
    org = app.organization
    with translation.override(app.language):
        body = (
            gettext("Guten Tag,")
            + "\n\n"
            + gettext(
                "zu deinem Mitgliedsantrag bei {org} ({number}) gibt es eine Rückfrage:"
            ).format(org=org.name, number=app.number)
            + f"\n\n{text}\n\n"
            + gettext("Bitte antworte einfach auf diese Mail.")
            + "\n"
        )
        subject = gettext("Rückfrage zu deinem Mitgliedsantrag: {org}").format(org=org.name)
    send(
        [confirmation_email(app)],
        subject,
        body,
        organization=org,
        kind=KIND,
        reply_to=[user.email] if getattr(user, "email", "") else None,
        language=app.language,
    )
    app.status = Application.Status.QUERY
    app.save(update_fields=["status", "updated_at"])
    event(app, "query", user, text)


@transaction.atomic
def resume(app: Application, user) -> Application:
    if app.status != Application.Status.QUERY:
        raise ValidationError(gettext("Es läuft keine Rückfrage."))
    app.status = Application.Status.OPEN
    app.save(update_fields=["status", "updated_at"])
    event(app, "resumed", user)
    return app


@transaction.atomic
def update_data(app: Application, user, changes: dict) -> Application:
    """Vorstand korrigiert Angaben; erteilte Zustimmungen gelten dann nicht mehr."""
    if not app.is_open:
        raise ValidationError(gettext("Der Antrag ist nicht mehr offen."))
    data = dict(app.data or {})
    changed = [k for k, v in changes.items() if data.get(k) != v]
    if not changed:
        return app
    data.update(changes)
    app.data = data
    app.save(update_fields=["data", "updated_at"])
    event(app, "corrected", user, ", ".join(sorted(changed)))
    if app.approvals.exists():
        app.approvals.all().delete()
        event(app, "approvals_reset", user)
    return app


@transaction.atomic
def set_choice(
    app: Application, user, member_type=None, unit=None, unit_given=False
) -> Application:
    if not app.is_open:
        raise ValidationError(gettext("Der Antrag ist nicht mehr offen."))
    fields = []
    if member_type is not None and member_type.pk != app.member_type_id:
        app.member_type = member_type
        fields.append("member_type")
    if unit_given and (unit.pk if unit else None) != app.unit_id:
        app.unit = unit
        fields.append("unit")
    if fields:
        app.save(update_fields=[*fields, "updated_at"])
        event(app, "corrected", user, ", ".join(fields))
        if app.approvals.exists():
            app.approvals.all().delete()
            event(app, "approvals_reset", user)
    return app


@transaction.atomic
def approve(
    app: Application, user, perms: set[str], decision: str, note: str = "", for_unit: bool = False
):
    form = form_for(app.organization)
    rule = form.rule or {}
    if app.status != Application.Status.OPEN:
        raise ValidationError(gettext("Zustimmen geht nur bei eingegangenen Anträgen."))
    if rule.get("mode") != "rule":
        raise ValidationError(gettext("Für diesen Verein sind keine Zustimmungen eingestellt."))
    roles = rules.user_roles(user, app.organization)
    if for_unit:
        if not rule.get("unit") or not app.unit_id:
            raise ValidationError(gettext("Eine Zustimmung der Untereinheit ist nicht nötig."))
        if MEMBERS_EDIT not in perms:
            raise ValidationError(gettext("Dafür fehlt dir die Berechtigung."))
    elif not rules.may_approve(rule, roles, perms):
        raise ValidationError(gettext("Deine Zustimmung ist nach der Regel nicht vorgesehen."))
    if decision not in ("approve", "reject"):
        raise ValidationError({"decision": gettext("Ungültige Entscheidung.")})
    if decision == "reject" and len((note or "").strip()) < 3:
        raise ValidationError({"note": gettext("Bitte kurz begründen.")})
    Approval.objects.filter(application=app, user=user, for_unit=for_unit).delete()
    Approval.objects.create(
        organization=app.organization,
        application=app,
        user=user,
        user_name=_user_name(user),
        role_ids=sorted(roles),
        role_names=", ".join(sorted(roles.values()))[:300],
        for_unit=for_unit,
        decision=decision,
        note=(note or "").strip()[:500],
    )
    event(app, "approved" if decision == "approve" else "objected", user, note)
    result = state(app, form)
    if decision == "approve" and result.met and not result.disputed and rule.get("auto_admit"):
        return accept(app, user, perms, {}, auto=True)
    return app


def _user_name(user) -> str:
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return (name or getattr(user, "email", "") or "?")[:200]


def entry_date_for(app: Application, form: ApplicationForm) -> datetime.date:
    today = timezone.localdate()
    if form.entry_date == ApplicationForm.EntryDate.WISH and app.entry_wish:
        return max(app.entry_wish, today)
    if form.entry_date == ApplicationForm.EntryDate.NEXT_MONTH:
        return today.replace(day=1) + relativedelta(months=1)
    return today


@transaction.atomic
def accept(app: Application, user, perms: set[str], options: dict, *, auto: bool = False):
    """Nimmt auf: Mitglied, Mandat, Einwilligungen, Begrüßung, auf Wunsch Mitgliederbereich."""
    from members import services as member_services

    org = app.organization
    form = form_for(org)
    rule = form.rule or {}
    Application.objects.select_for_update().filter(pk=app.pk).first()
    app.refresh_from_db()
    if app.status != Application.Status.OPEN:
        raise ValidationError(gettext("Aufnehmen geht nur bei eingegangenen Anträgen."))
    if not auto and MEMBERS_EDIT not in perms:
        raise ValidationError(gettext("Dafür fehlt dir die Berechtigung."))
    result = state(app, form)
    if result.disputed:
        raise ValidationError(
            gettext("Es gibt eine Ablehnung. Bitte klärt das, bevor ihr aufnehmt.")
        )
    if not result.met:
        raise ValidationError(
            gettext("Es fehlen noch Zustimmungen: {missing}").format(
                missing=", ".join(result.missing)
            )
        )
    note = (options.get("note") or "").strip()
    if rule.get("mode") == "assembly" and not note:
        raise ValidationError({"note": gettext("Bitte den Beschluss der Versammlung angeben.")})
    member_type = options.get("member_type") or app.member_type
    if member_type is None:
        raise ValidationError({"member_type": gettext("Bitte eine Mitgliedsart wählen.")})
    entry_date = options.get("entry_date") or entry_date_for(app, form)
    d = app.data or {}
    data = {
        "kind": app.kind,
        "person": options.get("person"),
        "last_name": d.get("last_name", ""),
        "first_name": d.get("first_name", ""),
        "birth_date": _parse_date(d.get("birth_date")),
        "gender": d.get("gender", ""),
        "club_number": options.get("club_number", ""),
        "member_type": member_type,
        "entry_date": entry_date,
        "departments": [app.unit] if app.unit_id else [],
    }
    for f in ("email", "phone", "street", "postal_code", "city", "country", "address_extra"):
        if d.get(f):
            data[f] = d[f]
    if app.kind == "organization" and d.get("legal_form"):
        data["legal_form"] = d["legal_form"]
    membership = member_services.admit(org, data, keep_contact=True)
    record(
        org,
        user if not auto else None,
        "create",
        membership,
        {
            "Mitgliedsart": [None, member_type.name],
            "Aufnahme": [None, f"Online-Antrag {app.number}"],
        },
        person=membership.person,
    )
    _accept_extras(app, membership, user)
    if d.get("family"):
        _accept_family(app, membership, data, user)
    app.status = Application.Status.ACCEPTED
    app.membership = membership
    app.decided_at = timezone.now()
    app.decided_by = user
    app.decision_note = note[:500]
    app.mandate = {}  # liegt jetzt im Mandat (billing)
    app.save()
    event(app, "accepted", user, note)
    if options.get("welcome", True):
        send_welcome(app, form)
    if options.get("invite"):
        _invite(org, membership, user)
    return app


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


def _accept_extras(app: Application, membership, user) -> None:
    """Mandat, Einwilligungen, Erziehungsberechtigte, Zusatzfelder (B2/B3/B5)."""
    org = app.organization
    signed_on = (app.confirmed_at or app.created_at).date()
    if app.mandate and app.mandate.get("iban"):
        from billing import sepa
        from billing.models import Mandate

        mandate = sepa.create_mandate(
            org,
            membership=membership,
            signed_on=signed_on,
            source=Mandate.Source.APPLICATION,
            user=user,
            holder=app.mandate.get("holder", ""),
            iban=app.mandate.get("iban", ""),
            bic=app.mandate.get("bic", ""),
        )
        record(
            org,
            user,
            "create",
            mandate,
            {"SEPA-Mandat": [None, f"{mandate.reference} im Online-Antrag {app.number} erteilt"]},
        )
    company = (app.data or {}).get("company_household")
    if company:
        _join_company(app, membership, company, user)
    keys = {c.get("key") for c in app.consents or [] if c.get("given")}
    if CONSENT_PHOTO in keys:
        membership.photo_consent_at = signed_on
        membership.photo_consent_source = "member"
        membership.save(update_fields=["photo_consent_at", "photo_consent_source", "updated_at"])
    from website.models import PublicationConsent

    categories = set(PublicationConsent.Category.values)
    for key in sorted(keys & categories):
        PublicationConsent.objects.create(
            organization=org,
            membership=membership,
            category=key,
            since=signed_on,
            source=PublicationConsent.Source.MEMBER,
            recorded_by=user,
        )
    from members.models import ContactPerson

    for i, g in enumerate(app.guardians or []):
        ContactPerson.objects.create(
            organization=org,
            membership=membership,
            last_name=g.get("last_name", ""),
            first_name=g.get("first_name", ""),
            function=gettext("Erziehungsberechtigt"),
            email=g.get("email", ""),
            phone=g.get("phone", ""),
            is_primary=i == 0,
            receives_mail=True,
            receives_invoices=True,
            represents=True,
            is_guardian=True,
            since=signed_on,
        )
    custom = (app.data or {}).get("custom_values") or {}
    if custom:
        from customfields.models import FieldValue
        from customfields.views import definitions_for

        defs = {
            str(d.pk): d for d in definitions_for(org) if not d.is_archived and not d.repeatable
        }
        for def_id, value in custom.items():
            definition = defs.get(str(def_id))
            if definition is None or value in ("", None, []):
                continue
            FieldValue.objects.update_or_create(
                definition=definition,
                person=membership.person,
                defaults={"value": value, "organization": definition.organization},
            )


def _accept_family(app: Application, main, main_data: dict, user) -> None:
    """Familienantrag (H6): weitere Personen aufnehmen, Haushalt anlegen. Mit dem Modul
    Beiträge zahlt der Antragsteller für alle (ein Mandat, eine Rechnung)."""
    from members import services as member_services
    from members.guardians import is_minor
    from members.households import add_member
    from members.models import ContactPerson, Household, HouseholdMember, MemberType

    org = app.organization
    d = app.data or {}
    billing = "billing" in (org.enabled_modules or [])
    household = Household.objects.create(
        organization=org,
        kind=Household.Kind.FAMILY,
        name=gettext("Familie {name}").format(name=d.get("last_name", "")),
    )
    entry = main_data["entry_date"]
    # Zahlt schon eine Firma für den Antragsteller (H5), bleibt sein Beitrag dort
    via_company = HouseholdMember.objects.filter(membership=main, pays_via=True).exists()
    add_member(
        household,
        main,
        role=HouseholdMember.Role.ADULT,
        valid_from=entry,
        pays_via=billing and not via_company,
    )
    signed_on = (app.confirmed_at or app.created_at).date()
    added = []
    for f in d.get("family") or []:
        member_type = (
            MemberType.objects.filter(organization=org, pk=f.get("member_type")).first()
            or main_data["member_type"]
        )
        data = {
            "kind": "person",
            "last_name": f.get("last_name") or d.get("last_name", ""),
            "first_name": f.get("first_name", ""),
            "birth_date": _parse_date(f.get("birth_date")),
            "member_type": member_type,
            "entry_date": entry,
            "departments": main_data["departments"],
        }
        for key in ("street", "postal_code", "city", "country", "address_extra"):
            if d.get(key):
                data[key] = d[key]
        membership = member_services.admit(org, data, keep_contact=True)
        minor = is_minor(membership.person)
        add_member(
            household,
            membership,
            role=HouseholdMember.Role.CHILD if minor else HouseholdMember.Role.ADULT,
            valid_from=entry,
            pays_via=billing,
        )
        if minor:
            ContactPerson.objects.create(
                organization=org,
                membership=membership,
                person=main.person,
                last_name=d.get("last_name", ""),
                first_name=d.get("first_name", ""),
                function=gettext("Erziehungsberechtigt"),
                email=d.get("email", ""),
                phone=d.get("phone", ""),
                is_primary=True,
                receives_mail=True,
                receives_invoices=True,
                represents=True,
                is_guardian=True,
                since=signed_on,
            )
        record(
            org,
            user,
            "create",
            membership,
            {
                "Mitgliedsart": [None, member_type.name],
                "Aufnahme": [None, f"Online-Antrag {app.number} (Familie)"],
            },
            person=membership.person,
        )
        added.append(str(membership.person))
    if billing:
        from billing.models import HouseholdPayer

        HouseholdPayer.objects.create(
            organization=org,
            household=household,
            kind=HouseholdPayer.Kind.MEMBER,
            membership=main,
        )
    record(
        org,
        user,
        "create",
        household,
        {"Familienantrag": [None, f"{app.number}: {', '.join(added)}"]},
        person=main.person,
    )


def _join_company(app: Application, membership, household_id, user) -> None:
    """Gemeldeter Mitarbeiter (H5): mit „Beitrag über die Firma“ zur Firma."""
    from members.households import add_member
    from members.models import Household

    household = Household.objects.filter(
        organization=app.organization, pk=household_id, kind=Household.Kind.COMPANY
    ).first()
    if household is None:
        return
    start = membership.periods.order_by("entry_date").values_list("entry_date", flat=True).first()
    try:
        with transaction.atomic():
            link = add_member(household, membership, valid_from=start, pays_via=True)
    except ValidationError:
        # Schon in einer anderen Firma oder Beitrag läuft über einen Haushalt: Aufnahme
        # bleibt gültig, der Vorstand ordnet von Hand zu.
        logger.info("Antrag %s: Mitglied nicht zur Firma %s", app.number, household.pk)
        return
    record(
        app.organization,
        user,
        "create",
        link,
        {"Firma": [None, f"{household.name} (Online-Antrag {app.number})"]},
        person=membership.person,
    )


def _invite(org, membership, user) -> None:
    from access.modules import module_on
    from portal import services as portal_services

    if not (getattr(org, "member_portal_enabled", False) and module_on(org, "portal")):
        return
    if membership.person.is_organization:
        return
    try:
        access = portal_services.ensure_access(org, membership, user)
        portal_services.send_access_mail(org, access, user)
    except Exception:  # noqa: BLE001 - Aufnahme gilt, Einladung kann später erfolgen
        return


def send_welcome(app: Application, form: ApplicationForm) -> None:
    org = app.organization
    with translation.override(app.language):
        own = text_of(form, "welcome", app.language)
        body = (
            gettext("Guten Tag,")
            + "\n\n"
            + (
                own
                or gettext(
                    "herzlich willkommen bei {org}! Dein Mitgliedsantrag wurde angenommen."
                ).format(org=org.name)
            )
            + "\n"
        )
        subject = gettext("Willkommen bei {org}").format(org=org.name)
    send(
        [confirmation_email(app)],
        subject,
        body,
        organization=org,
        kind=KIND,
        fail_silently=True,
        language=app.language,
    )


@transaction.atomic
def reject(app: Application, user, note: str, send_mail: bool, text: str = "") -> Application:
    if not app.is_open:
        raise ValidationError(gettext("Der Antrag ist nicht mehr offen."))
    app.status = Application.Status.REJECTED
    app.decided_at = timezone.now()
    app.decided_by = user
    app.decision_note = (note or "").strip()[:500]
    app.mandate = {}
    app.purge_after = purge_date(app)
    app.save()
    event(app, "rejected", user, note)
    if send_mail:
        form = form_for(app.organization)
        org = app.organization
        with translation.override(app.language):
            own = (text or "").strip() or text_of(form, "rejection", app.language)
            body = (
                gettext("Guten Tag,")
                + "\n\n"
                + (
                    own
                    or gettext(
                        "leider können wir deinen Mitgliedsantrag bei {org} nicht annehmen."
                    ).format(org=org.name)
                )
                + "\n"
            )
            subject = gettext("Dein Mitgliedsantrag bei {org}").format(org=org.name)
        send(
            [confirmation_email(app)],
            subject,
            body,
            organization=org,
            kind=KIND,
            fail_silently=True,
            language=app.language,
        )
    return app


# --- Aufräumen ---


def purge(now: datetime.datetime | None = None) -> int:
    """Unbestätigte Anträge nach 48 Stunden, abgelehnte und zurückgezogene nach der Frist."""
    now = now or timezone.now()
    with rls_bypass():
        old = now - datetime.timedelta(hours=UNCONFIRMED_HOURS)
        n1, _ = Application.objects.filter(status="unconfirmed", created_at__lt=old).delete()
        n2, _ = Application.objects.filter(
            status__in=("rejected", "withdrawn"), purge_after__lte=now.date()
        ).delete()
        KioskLink.objects.filter(valid_until__lt=now - datetime.timedelta(days=30)).delete()
    return n1 + n2


# --- Stand-Modus (B5) ---


def create_kiosk(org, user, label: str, hours: int) -> tuple[KioskLink, str]:
    if not 1 <= hours <= 24 * 7:
        raise ValidationError({"hours": gettext("Zwischen 1 Stunde und 7 Tagen.")})
    token = secrets.token_urlsafe(24)
    link = KioskLink.objects.create(
        organization=org,
        label=(label or "").strip()[:100] or gettext("Stand"),
        token_hash=hash_token(token),
        valid_until=timezone.now() + datetime.timedelta(hours=hours),
        created_by=user,
    )
    return link, f"{base_url(org)}/mitglied-werden/stand/{token}"


def find_kiosk(token: str) -> KioskLink | None:
    if not token or len(token) > 100:
        return None
    with rls_bypass():
        return (
            KioskLink.objects.select_related("organization")
            .filter(
                token_hash=hash_token(token),
                revoked_at__isnull=True,
                valid_until__gt=timezone.now(),
            )
            .first()
        )
