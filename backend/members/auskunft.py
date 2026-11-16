"""Auskunft für ein einzelnes Mitglied (Art. 15 DSGVO, Gesamtaudit 31.10.b, Frage 7).

Ein ZIP nur mit den Daten dieser Person in diesem Verein: Akte, Zusatzfelder, Rechnungen
(mit PDF), Lastschriftmandate, Zuwendungen, versandte Mails, Zugang und Geräte der App,
Rückmeldungen zu Terminen, Verbund-Empfänger und das Änderungsprotokoll. Daten anderer
Personen (z. B. wer etwas geändert hat) stehen nicht darin.
"""

from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .models import Membership

README = """Auskunft über gespeicherte Daten (Art. 15 DSGVO)

Person: {name}
Verein: {org}
Erstellt: {when}

Inhalt
- akte.json: Stammdaten, Kontaktdaten, Mitgliedschaftszeiten, Mitgliedsarten, Zugehörigkeit zu
  Untereinheiten, Ämter, Ehrungen, Verbandsmeldung; bei Organisationen deren
  Ansprechpartner, bei Personen die Organisationen, für die sie Ansprechpartner sind
- zusatzfelder.json: vom Verein festgelegte zusätzliche Angaben
- rechnungen.json / rechnungen.pdf: Rechnungen an die Person mit Zahlungen; aus
  Sammelrechnungen an andere nur die eigenen Posten mit Nummer, Datum und Empfänger
- mandate.json: SEPA-Lastschriftmandate
- zuwendungen.json: Spenden und Zuwendungen
- mails.json: E-Mails, die der Verein über HUBIplan an die Person geschickt hat
- zugang.json: Mitgliederzugang, Anmeldekonto und verbundene Geräte der App
- konto.json: Anmeldekonten der Person: E-Mail-Adressen, Sprache, Zwei-Faktor-Verfahren und
  Passkeys (nur Art, Name und Zeiten, nie Schlüssel), Geräte mit Benachrichtigungsdienst,
  Nextcloud-Konten, verbundene KI-Assistenten, Anmeldungen über andere Instanzen, gespeicherte
  Unterschrift, Briefbogen-Auswahl, eigene Aufgaben und Erinnerungseinstellungen dieses Vereins
- termine.json: Zu- und Absagen zu Terminen
- qualifikationen.json: Qualifikationen und Nachweise mit Gültigkeit (bei Einsichtsvermerken wie
  dem Führungszeugnis nur das Datum der Einsicht, nie der Inhalt)
- verbund.json: Meldungen an andere HUBIplan-Instanzen (z. B. Dachverband)
- antrag.json / antrag-*.pdf: Online-Mitgliedsantrag mit Einwilligungen und Verlauf
- aenderungswuensche.json, kuendigungen.json: Wünsche aus dem Mitgliederbereich
- einwilligungen.json: Einwilligungen zur Veröffentlichung (Webseite, Fotos)
- ausweise.json, fotolinks.json: Mitgliedsausweise und Links zum Hochladen eines Fotos
- kasse.json: Buchungen, Quittungen und Zuwendungsbestätigungen zur Person
- zahler.json, geschaeftspartner.json: Zahler eines Haushalts oder einer Firma, Geschäftspartner
- rundschreiben.json: Rundschreiben und Briefe an die Person
- wettbewerbe.json, meldungen.json, wuerden.json: Starts, Auszeichnungen, Meldungen, Würden
- musik.json, material.json: Besetzung in der Musik, überlassenes Material
- wechsel.json: Vereinswechsel
- protokoll.json: Änderungen an den Daten der Person (ohne Namen der Bearbeitenden)
- foto.*: hinterlegtes Mitgliederfoto (falls vorhanden); foto-wartet-*: noch nicht
  freigegebene Fotos; wuerde-*: Fotos von Würden, auf denen die Person genannt ist
- persönliche Aufgaben: nur Stand und Daten (konto.json); den Inhalt exportiert die Person
  selbst unter „Mein Konto“ › Profil (eigene Aufgaben)

Zwecke: Mitgliederverwaltung, Beiträge und Kasse, Information der Mitglieder, Termine.
Empfänger: Vorstand und berechtigte Personen des Vereins; Meldungen an den Dachverband nur,
soweit die Mitgliedsart dafür vorgesehen ist. Rechnungen und Buchungen werden wegen der
steuerlichen Aufbewahrungsfrist aufbewahrt.
"""

# Felder, die nie in eine Auskunft gehören (Prüfsummen, Schlüssel, interne Verweise)
SECRET = {
    "token_hash",
    "previous_token_hash",
    "retired_hashes",
    "admin_token_hash",
    "token",
    "wallet_passes",
    "fingerprint",
    "pdf_sha256",
    "cancel_sha256",
    "old_token_hash",
    "access_hash",
    "refresh_hash",
    "previous_refresh_hash",
    "push_endpoint",
    "push_p256dh",
    "push_auth",
    "checksums",
}

# Wer etwas angelegt, bearbeitet oder entschieden hat, sind Daten anderer Personen
STAFF = frozenset(
    {
        "created_by",
        "decided_by",
        "user",
        "recorded_by",
        "issued_by",
        "cancelled_by",
        "finalized_by",
        "treasurer_user",
        "treasurer_name",
        "treasurer_signature",
        "signer_name",
        "liaison",
    }
)


def _row(obj, exclude: set[str] | frozenset = frozenset()) -> dict:
    data = {}
    for field in obj._meta.concrete_fields:
        if field.name in exclude or field.name in SECRET:
            continue
        if isinstance(field, models.FileField | models.BinaryField):
            continue
        if isinstance(field, models.ForeignKey):
            data[field.attname] = getattr(obj, field.attname)
            continue
        data[field.name] = field.value_from_object(obj)
    return data


def _rows(queryset, exclude: set[str] | frozenset = frozenset()) -> list[dict]:
    """Zeilen eines Bestands ohne Verweise auf den Verein, die Person selbst und Bearbeiter."""
    skip = STAFF | {"organization", "membership", "person"} | set(exclude)
    return [_row(obj, skip) for obj in queryset]


def _dump(value) -> str:
    return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)


def _org_ids(org) -> list[int]:
    """Verein und alle Einheiten darunter (Mails und Protokoll der Untereinheiten)."""
    from organizations.models import Organization

    ids, level = [org.pk], [org.pk]
    while level:
        level = list(Organization.objects.filter(parent_id__in=level).values_list("pk", flat=True))
        ids += level
    return ids


def _emails(membership: Membership, org) -> set[str]:
    from members.models import ContactDetails
    from portal.models import PortalAccess

    found = set()
    for c in ContactDetails.objects.filter(person=membership.person):
        if c.email:
            found.add(c.email.lower())
    for access in PortalAccess.objects.filter(membership=membership).select_related("user"):
        if access.user and access.user.email:
            found.add(access.user.email.lower())
    # Mails, die für das Kind an die Erziehungsberechtigten gingen (Gesamtaudit 15.11., PF-20)
    from members.models import ContactPerson

    for contact in ContactPerson.objects.filter(membership=membership, is_guardian=True):
        if contact.email:
            found.add(contact.email.lower())
    return found


def _paid_households(membership: Membership) -> list[int]:
    """Haushalte und Firmen, für die die Person zahlt (Gesamtaudit 15.11., PF-20)."""
    from billing.models import HouseholdPayer

    return list(
        HouseholdPayer.objects.filter(membership=membership).values_list("household_id", flat=True)
    )


def _own(inv, membership: Membership, households: list[int]) -> bool:
    """Rechnung an die Person selbst: an sie oder an einen Haushalt, für den sie zahlt."""
    return inv.membership_id == membership.pk or (
        inv.household_id is not None and inv.household_id in households
    )


def _invoices(membership: Membership):
    from billing.models import Invoice

    households = _paid_households(membership)
    return list(
        Invoice.objects.filter(
            Q(membership=membership)
            | Q(lines__membership=membership)
            | Q(household_id__in=households)
        )
        .distinct()
        .prefetch_related("lines", "payments")
        .order_by("date", "pk")
    )


# Sammelrechnung an jemand anderen: nur der nötige Zusammenhang (Fachfrage FQ13)
SHARED_INVOICE_FIELDS = (
    "number",
    "year",
    "status",
    "recipient_name",
    "date",
    "due_date",
    "subject",
    "cancelled_at",
)


def _invoice_rows(invoices, membership: Membership | None = None) -> list[dict]:
    """Rechnungen an die Person vollständig. Steht die Person nur in einzelnen Posten einer
    Sammelrechnung an jemand anderen, gehören nur ihre eigenen Posten in die Auskunft, mit
    Nummer, Datum und Rechnungsempfänger als Zusammenhang; Posten, Anschrift und Zahlungen
    der anderen bleiben draußen (Fachfrage FQ13)."""
    rows = []
    households = _paid_households(membership) if membership is not None else []
    for inv in invoices:
        if membership is not None and not _own(inv, membership, households):
            own = [line for line in inv.lines.all() if line.membership_id == membership.pk]
            row = {name: getattr(inv, name) for name in SHARED_INVOICE_FIELDS}
            row["sammelrechnung"] = True
            row["positionen"] = [_row(line) for line in own]
            row["eigene_summe"] = sum((line.amount for line in own), Decimal("0"))
            rows.append(row)
            continue
        row = _row(inv, {"created_by"})
        row["positionen"] = [_row(line) for line in inv.lines.all()]
        row["zahlungen"] = [_row(p, {"created_by", "booking"}) for p in inv.payments.all()]
        rows.append(row)
    return rows


def _applications(membership: Membership) -> dict[str, str | bytes]:
    """Online-Anträge der Person (Gesamtaudit 13.11. K-02)."""
    from admission.models import Application

    files: dict[str, str | bytes] = {}
    rows = []
    for app in Application.objects.filter(membership=membership).order_by("pk"):
        rows.append(
            {
                "nummer": app.number,
                "stand": app.get_status_display(),
                "herkunft": app.get_source_display(),
                "gestellt": app.created_at,
                "bestaetigt": app.confirmed_at,
                "unterschrieben": app.signed_at,
                "entschieden": app.decided_at,
                "vermerk": app.decision_note,
                "wunsch_eintritt": app.entry_wish,
                "angaben": app.data,
                "angaben_entfernt": app.data_purged_at,
                "einwilligungen": app.consents,
                "erziehungsberechtigte": app.guardians,
                "mandat": app.mandate,
                # ohne Namen der Entscheidenden
                "zustimmungen": [
                    {"rollen": a.role_names, "entscheidung": a.decision, "am": a.created_at}
                    for a in app.approvals.all()
                ],
                "verlauf": [
                    {"ereignis": e.kind, "vermerk": e.note, "am": e.created_at}
                    for e in app.events.all()
                ],
            }
        )
        if app.pdf:
            try:
                with app.pdf.open("rb") as fh:
                    files[f"antrag-{app.number}.pdf"] = fh.read()
            except OSError:
                pass
    files["antrag.json"] = _dump(rows)
    return files


def _further(membership: Membership, org_ids: list[int]) -> dict[str, str | bytes]:
    """Alle übrigen Bestände mit Bezug zur Person (Gesamtaudit 13.11. K-02).

    ``tests/test_auskunft_vollstaendig.py`` prüft, dass jedes Modell mit Verweis auf Person
    oder Mitgliedschaft hier, in der Akte oder auf der begründeten Ausnahmeliste steht.
    """
    from billing.models import BusinessPartner, HouseholdPayer
    from cards.models import MemberCard
    from circulars.models import CircularRecipient
    from competitions.models import AwardGrant, ShootOffEntry, Starter
    from entries.models import EntryPerson
    from finance.models import Booking, CashReceipt, DonationStatement
    from honors.models import Companion, Reign
    from materials.models import MaterialItem
    from music.models import Musician
    from peering.models import RemoteTransfer
    from portal.models import CancellationRequest, ChangeRequest
    from website.models import PublicationConsent

    from .models import PhotoUploadLink, TransferRequest

    person = membership.person
    mine = {"membership": membership}
    files = _applications(membership)
    files["aenderungswuensche.json"] = _dump(_rows(ChangeRequest.objects.filter(**mine)))
    files["kuendigungen.json"] = _dump(_rows(CancellationRequest.objects.filter(**mine)))
    files["einwilligungen.json"] = _dump(_rows(PublicationConsent.objects.filter(**mine)))
    files["ausweise.json"] = _dump(_rows(MemberCard.objects.filter(**mine)))
    files["fotolinks.json"] = _dump(_rows(PhotoUploadLink.objects.filter(**mine)))
    files["kasse.json"] = _dump(
        {
            "buchungen": _rows(Booking.objects.filter(**mine)),
            "quittungen": _rows(CashReceipt.objects.filter(**mine)),
            "zuwendungsbestaetigungen": _rows(DonationStatement.objects.filter(**mine)),
        }
    )
    files["zahler.json"] = _dump(_rows(HouseholdPayer.objects.filter(**mine)))
    files["geschaeftspartner.json"] = _dump(_rows(BusinessPartner.objects.filter(**mine)))
    files["rundschreiben.json"] = _dump(
        [
            {"rundschreiben": str(r.circular), **_row(r, STAFF | {"organization", "membership"})}
            for r in CircularRecipient.objects.filter(**mine).select_related("circular")
        ]
    )
    files["wettbewerbe.json"] = _dump(
        {
            "starts": [
                {"wettbewerb": str(s.competition), **_row(s, {"organization", "membership"})}
                for s in Starter.objects.filter(**mine).select_related("competition")
            ],
            "stechen": _rows(ShootOffEntry.objects.filter(**mine)),
            "auszeichnungen": _rows(AwardGrant.objects.filter(**mine)),
        }
    )
    files["meldungen.json"] = _dump(_rows(EntryPerson.objects.filter(**mine)))
    files["wuerden.json"] = _dump(
        {
            "wuerden": [
                {"wuerde": str(r.dignity), **_row(r, {"organization", "person"})}
                for r in Reign.objects.filter(
                    person=person, organization_id__in=org_ids
                ).select_related("dignity")
            ],
            "begleitung": _rows(
                Companion.objects.filter(person=person, organization_id__in=org_ids)
            ),
        }
    )
    files["musik.json"] = _dump(_rows(Musician.objects.filter(**mine)))
    files["material.json"] = _dump(
        _rows(MaterialItem.objects.filter(member=membership), {"member", "version"})
    )
    files["wechsel.json"] = _dump(
        {
            "anfragen": _rows(
                TransferRequest.objects.filter(person=person).filter(
                    Q(from_org_id__in=org_ids) | Q(to_org_id__in=org_ids)
                )
            ),
            "verbund": _rows(RemoteTransfer.objects.filter(**mine), {"coupling", "transfer"}),
        }
    )
    return files


def _users(membership: Membership, org_ids: list[int]) -> list:
    """Anmeldekonten der Person: Mitgliederzugang und Ämter in diesem Verein."""
    from access.models import RoleAssignment
    from portal.models import PortalAccess

    ids = set(
        PortalAccess.objects.filter(membership=membership, user__isnull=False).values_list(
            "user_id", flat=True
        )
    )
    ids.update(
        RoleAssignment.objects.filter(
            Q(membership=membership)
            | Q(person_id=membership.person_id, organization_id__in=org_ids),
            user__isnull=False,
        ).values_list("user_id", flat=True)
    )
    from django.contrib.auth import get_user_model

    return list(get_user_model().objects.filter(pk__in=ids).order_by("pk"))


def _host(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).hostname or "" if url else ""


def _account(user, org_ids: list[int]) -> dict:
    """Alles, was am Anmeldekonto hängt (Gesamtaudit 15.11., PF-02/PF-20).

    Kontoweite Angaben vollständig; was einer Einheit gehört (Nextcloud, KI-Assistenten,
    Aufgaben, Briefbogen) nur aus diesem Verein und seinen Untereinheiten. Schlüssel,
    Prüfsummen und die Push-Adresse (sie erlaubt das Senden an das Gerät) stehen nie darin.
    Persönliche, nicht geteilte Aufgaben nur mit Status und Daten: Ihren Inhalt sieht in
    HUBIplan nur die Person selbst."""
    from allauth.account.models import EmailAddress
    from allauth.mfa.models import Authenticator

    from accounts.models import EmailChange, StoredSignature
    from devices.models import Device
    from letterhead.models import LetterheadChoice
    from mcpserver.models import McpGrant
    from music.models import MusicReminderPreference
    from oidc.models import Account
    from peering.models import RemoteAccount
    from todos.models import (
        Todo,
        TodoNotice,
        TodoPreference,
        TodoReminder,
        TodoReminderConfig,
        TodoShare,
    )

    signature = StoredSignature.objects.filter(user=user).first()
    own = Todo.objects.filter(owner=user, organization_id__in=org_ids, deleted_at__isnull=True)
    shared_with = Todo.objects.filter(
        shares__user=user, organization_id__in=org_ids, deleted_at__isnull=True
    ).distinct()

    def todo(t, content: bool) -> dict:
        row = {
            "status": t.get_status_display(),
            "frist": t.due_date,
            "angelegt": t.created_at,
            "erledigt": t.done_at,
            "geteilt": t.shared,
        }
        if content:
            row["titel"] = t.title
        return row

    return {
        "anmelde_email": user.email,
        "vorname": user.first_name,
        "nachname": user.last_name,
        "angelegt": user.date_joined,
        "letzte_anmeldung": user.last_login,
        "aktiv": user.is_active,
        "sprache": user.language,
        "darstellung": user.color_scheme,
        "email_adressen": [
            {"email": a.email, "bestätigt": a.verified, "haupt": a.primary}
            for a in EmailAddress.objects.filter(user=user)
        ],
        "email_wechsel": _rows(EmailChange.objects.filter(user=user)),
        "zwei_faktor": [
            {
                "art": a.type,
                "name": (a.data or {}).get("name", "") if a.type == "webauthn" else "",
                "angelegt": a.created_at,
                "zuletzt_benutzt": a.last_used_at,
            }
            for a in Authenticator.objects.filter(user=user)
        ],
        "gespeicherte_unterschrift": (
            {"vorhanden": True, "geändert": signature.updated_at} if signature else None
        ),
        "geräte": [
            {
                **_row(d, {"user", "device_key", "admin_key"}),
                "benachrichtigungsdienst": _host(d.push_endpoint),
            }
            for d in Device.objects.filter(user=user)
        ],
        "nextcloud": [
            {
                "dienst": a.client.name,
                "benutzername": a.nc_user,
                "erste_anmeldung": a.first_login_at,
                "letzte_anmeldung": a.last_login_at,
                "von_hubiplan_deaktiviert": a.disabled_by_hubiplan,
            }
            for a in Account.objects.filter(user=user, organization_id__in=org_ids).select_related(
                "client"
            )
        ],
        "ki_assistenten": [
            {
                "assistent": g.client.name,
                "rechte": g.scopes,
                "verbunden": g.created_at,
                "zuletzt_benutzt": g.last_used_at,
                "gültig_bis": g.expires_at,
                "getrennt": g.revoked_at,
            }
            for g in McpGrant.objects.filter(user=user, organization_id__in=org_ids).select_related(
                "client"
            )
        ],
        "andere_instanzen": [
            {"instanz": r.peer.base_url, "angelegt": r.created_at, "zuletzt": r.last_used_at}
            for r in RemoteAccount.objects.filter(user=user).select_related("peer")
        ],
        "briefbogen": _rows(
            LetterheadChoice.objects.filter(user=user, unit_id__in=org_ids), {"user", "unit"}
        ),
        "aufgaben": {
            "eigene": [todo(t, t.shared) for t in own.order_by("created_at")],
            "mit_dir_geteilt": [todo(t, True) for t in shared_with.order_by("created_at")],
            "freigaben": TodoShare.objects.filter(user=user, organization_id__in=org_ids).count(),
            "einstellungen": _rows(TodoPreference.objects.filter(user=user)),
            "erinnerungen": _rows(
                TodoReminderConfig.objects.filter(user=user, organization_id__in=org_ids)
            ),
            "geplante_erinnerungen": TodoReminder.objects.filter(
                user=user, organization_id__in=org_ids
            ).count(),
            "hinweise": TodoNotice.objects.filter(user=user, organization_id__in=org_ids).count(),
        },
        "musik_erinnerungen": _rows(
            MusicReminderPreference.objects.filter(user=user, organization_id__in=org_ids)
        ),
    }


def build(membership: Membership, org) -> bytes:
    """ZIP mit allen Daten der Person in diesem Verein."""
    from audit.models import AuditEntry
    from billing.models import Mandate
    from customfields.models import FieldValue
    from devices.models import Device
    from events.models import EventResponse
    from finance.models import Donation
    from outbox.models import OutgoingMail
    from peering.models import RemoteMember
    from portal.models import PortalAccess

    from .serializers import member_detail

    person = membership.person
    org_ids = _org_ids(org)
    files: dict[str, str | bytes] = {}

    akte = member_detail(membership, org)
    for key in ("exit_reasons", "contact_shared", "photo", "other_memberships"):
        akte.pop(key, None)
    files["akte.json"] = _dump(akte)

    values = FieldValue.objects.filter(person=person, organization_id__in=org_ids)
    files["zusatzfelder.json"] = _dump(
        [
            {"feld": v.definition.label, "wert": v.value, "geändert": v.updated_at}
            for v in values.select_related("definition")
        ]
    )

    invoices = _invoices(membership)
    files["rechnungen.json"] = _dump(_invoice_rows(invoices, membership))
    # Als PDF nur Rechnungen an die Person selbst; eine Sammelrechnung zeigt alle Posten
    households = _paid_households(membership)
    issued = [i for i in invoices if i.number and _own(i, membership, households)]
    if issued:
        from billing import pdf

        files["rechnungen.pdf"] = pdf.render(issued)
    # Auch Mandate eines Haushalts, für den die Person zahlt (PF-20)
    files["mandate.json"] = _dump(
        [
            _row(m)
            for m in Mandate.objects.filter(
                Q(membership=membership) | Q(household_id__in=households)
            )
        ]
    )
    files["zuwendungen.json"] = _dump(
        [_row(d, {"created_by"}) for d in Donation.objects.filter(membership=membership)]
    )

    emails = _emails(membership, org)
    mails = []
    if emails:
        match = Q()
        for address in emails:
            match |= Q(to__icontains=address)
        for mail in OutgoingMail.objects.filter(match, organization_id__in=org_ids):
            # Nur Mails an diese Person (kein Teiltreffer in einer längeren Adresse)
            to = {a.strip().lower() for a in mail.to.replace(";", ",").split(",")}
            if to & emails:
                mails.append(
                    {
                        "an": mail.to,
                        "betreff": mail.subject,
                        "text": mail.body,
                        "anhänge": [a.get("name") for a in mail.attachments or []],
                        "status": mail.get_status_display(),
                        "erstellt": mail.created_at,
                    }
                )
    files["mails.json"] = _dump(mails)

    access_rows = []
    for access in PortalAccess.objects.filter(membership=membership).select_related("user"):
        user = access.user
        devices = Device.objects.filter(user=user) if user else Device.objects.none()
        access_rows.append(
            {
                "zugang_seit": access.created_at,
                "anmelde_email": user.email if user else None,
                "letzte_anmeldung": user.last_login if user else None,
                "geräte": [
                    {
                        "name": d.name,
                        "plattform": d.platform,
                        "app_version": d.app_version,
                        "verbunden": d.created_at,
                        "zuletzt_gesehen": d.last_seen_at,
                        "abgemeldet": d.revoked_at,
                        "benachrichtigungen": d.push_kind,
                    }
                    for d in devices
                ],
            }
        )
    files["zugang.json"] = _dump(access_rows)
    files["konto.json"] = _dump([_account(u, org_ids) for u in _users(membership, org_ids)])

    files["termine.json"] = _dump(
        [
            {"termin": r.event.title, **_row(r, {"event", "membership", "organization"})}
            for r in EventResponse.objects.filter(membership=membership).select_related("event")
        ]
    )

    from helpers.models import ShiftAssignment
    from meetings.models import Attendance, Ballot, Motion, PollOption, Resolution, VoteCast

    files["versammlungen.json"] = _dump(
        {
            "anwesenheit": [
                {
                    "versammlung": a.meeting.event.title,
                    "beginn": a.meeting.event.starts_at,
                    **_row(
                        a,
                        {
                            "meeting",
                            "membership",
                            "organization",
                            "represented_by",
                            "delegate_membership",
                        },
                    ),
                }
                for a in Attendance.objects.filter(membership=membership).select_related(
                    "meeting__event"
                )
            ],
            "gewaehlt": [
                {
                    "versammlung": r.meeting.event.title,
                    "amt": r.office,
                    "ergebnis": r.get_result_display(),
                    "nummer": r.number,
                }
                for r in Resolution.objects.filter(elected=membership).select_related(
                    "meeting__event"
                )
            ],
            # Online-Abstimmungen (V7): offene mit Antwort, geheime nur „abgestimmt“
            "abstimmungen": [
                {
                    "versammlung": c.poll.meeting.event.title,
                    "frage": c.poll.question,
                    "geheim": c.poll.secret,
                    "antwort": ""
                    if c.poll.secret
                    else next(
                        (
                            b.option.label
                            for b in Ballot.objects.filter(
                                poll=c.poll, attendance=c.attendance
                            ).select_related("option")
                        ),
                        "",
                    ),
                }
                for c in VoteCast.objects.filter(attendance__membership=membership).select_related(
                    "poll__meeting__event"
                )
            ],
            # Zur Wahl gestanden (Online-Wahl, V7)
            "kandidaturen": [
                {
                    "versammlung": o.poll.meeting.event.title,
                    "frage": o.poll.question,
                    "amt": o.poll.office,
                    "name": o.label,
                }
                for o in PollOption.objects.filter(membership=membership).select_related(
                    "poll__meeting__event"
                )
            ],
            "antraege": [
                {
                    "versammlung": m.meeting.event.title,
                    "titel": m.title,
                    "begruendung": m.text,
                    "stand": m.get_status_display(),
                    "antwort": m.reply,
                    "eingereicht": m.created_at,
                }
                for m in Motion.objects.filter(membership=membership).select_related(
                    "meeting__event"
                )
            ],
        }
    )
    files["helferdienste.json"] = _dump(
        [
            {
                "dienstplan": a.shift.duty.plan.title,
                "dienst": a.shift.duty.name,
                "beginn": a.shift.starts_at,
                "ende": a.shift.ends_at,
                **_row(a, {"shift", "membership", "organization", "created_by", "phone"}),
            }
            for a in ShiftAssignment.objects.filter(membership=membership).select_related(
                "shift__duty__plan"
            )
        ]
    )

    from surveys.models import SurveyAnswer, SurveyParticipation

    # Umfragen: eigene Antworten mit Namen; anonyme Antworten sind keiner Person zuzuordnen
    files["umfragen.json"] = _dump(
        [
            {
                "umfrage": p.survey.title,
                "beantwortet": p.answered_at,
                "anonym": p.survey.anonymous,
                "antworten": []
                if p.survey.anonymous
                else [
                    {
                        "frage": a.question.text,
                        "antwort": a.option.label if a.option_id else "",
                        "termin": a.option.starts_at if a.option_id else None,
                        "wert": a.value,
                        "menge": a.quantity,
                        "text": a.text,
                    }
                    for a in SurveyAnswer.objects.filter(participation=p).select_related(
                        "question", "option"
                    )
                ],
            }
            for p in SurveyParticipation.objects.filter(membership=membership).select_related(
                "survey"
            )
        ]
    )

    from qualifications.models import Qualification

    files["qualifikationen.json"] = _dump(
        [
            {
                "qualifikation": q.kind.name,
                **_row(q, {"kind", "person", "organization", "created_by", "reminded_at"}),
            }
            # Verein und Untereinheiten (Gesamtaudit 15.11., PF-20)
            for q in Qualification.objects.filter(
                organization_id__in=org_ids, person_id=membership.person_id
            ).select_related("kind")
        ]
    )

    files["verbund.json"] = _dump(
        [
            {
                "gegenstelle": rm.coupling.peer.base_url,
                "einheit": str(rm.coupling.remote_uuid),
                "verbandsnummer": rm.number,
                "status": rm.get_status_display(),
                "stand": rm.updated_at,
            }
            for rm in RemoteMember.objects.filter(membership=membership).select_related(
                "coupling__peer"
            )
        ]
    )

    files.update(_further(membership, org_ids))

    entries = AuditEntry.objects.filter(organization_id__in=org_ids, person_id=person.pk)
    files["protokoll.json"] = _dump(
        [
            {
                "zeit": e.timestamp,
                "aktion": e.get_action_display(),
                "objekt": e.object_repr,
                "änderungen": e.changes,
            }
            for e in entries.order_by("timestamp")
        ]
    )

    # Alle Fotos: das freigegebene, wartende und Fotos von Würden (Gesamtaudit 15.11., PF-20)
    def add_file(name, field):
        if not field:
            return
        try:
            with field.open("rb") as fh:
                suffix = field.name.rsplit(".", 1)[-1] if "." in field.name else "jpg"
                files[f"{name}.{suffix}"] = fh.read()
        except OSError:
            pass

    photos = list(membership.photos.order_by("-status", "pk"))
    approved = [p for p in photos if p.status == "approved"]
    if approved:
        add_file("foto", approved[0].image)
    for p in photos:
        if p.status != "approved":
            add_file(f"foto-{p.get_status_display()}-{p.pk}".replace(" ", "-"), p.image)
    from honors.models import ReignPhoto

    for rp in ReignPhoto.objects.filter(
        Q(reign__person_id=membership.person_id)
        | Q(reign__companions__person_id=membership.person_id),
        organization_id__in=org_ids,
    ).distinct():
        add_file(f"wuerde-{rp.reign_id}", rp.file)

    files["LIESMICH.txt"] = README.format(
        name=f"{person.first_name} {person.last_name}".strip(),
        org=org.name,
        when=timezone.localtime().strftime("%d.%m.%Y %H:%M"),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()
