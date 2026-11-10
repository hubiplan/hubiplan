"""Modultabellen (Kasse, Beiträge, …) allgemein exportieren und importieren.

Jede Tabelle hier hat eine Spalte ``organization``. Exportiert werden alle
Spalten außer Nummer, Organisation und Protokollfeldern. Fremdschlüssel werden
als Nummern der Quelle geschrieben und beim Import über ``IdMap`` auf die neuen
Nummern umgesetzt. Neue Module tragen ihre Modelle in ``MODULE_MODELS`` ein, in
der Reihenfolge, in der sie angelegt werden müssen (Verweisziele zuerst).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext

from .validation import validate_url_data, validate_urls

MODULE_MODELS = (
    "music.Musician",
    "music.MusicianAbsence",
    "music.Skill",
    "todos.TodoSeries",
    "todos.Todo",
    "finance.Account",
    "finance.Category",
    "finance.ProjectSeries",
    "finance.Project",
    # Zweckbindungen vor Buchungen und Zuwendungen (beide verweisen darauf)
    "finance.Earmark",
    "finance.Booking",
    "finance.Receipt",
    "finance.YearClosing",
    "finance.DonationSettings",
    "finance.DonationStatement",
    "finance.Donation",
    "billing.BillingSettings",
    "billing.FeeRate",
    "billing.AgeRate",
    "billing.SizeRate",
    "billing.FeeRun",
    "billing.BusinessPartner",
    "billing.PartnerContact",
    "billing.PartnerAgreement",
    "billing.Invoice",
    "billing.InvoiceArtifact",
    "billing.InvoiceHybridArtifact",
    "billing.InvoiceDelivery",
    "billing.IncomingInvoice",
    "billing.IncomingValidation",
    "billing.InvoiceLine",
    "billing.Payment",
    "billing.InvoiceAdvance",
    # Quittungen nach Buchung, Beleg (PDF), Rechnung und Zahlung (Gesamtaudit 30.10., B-F01)
    "finance.CashReceipt",
    "billing.DunningLevel",
    "billing.Dunning",
    "billing.Mandate",
    "billing.DebitRun",
    "billing.DebitItem",
    "finance.BankStatement",
    "finance.BankLine",
    # Rücklagen (Finanzamt-Prüfung C4)
    "finance.Reserve",
    "finance.ReserveMovement",
    # Kassenzählungen/Festberichte mit Original-PDF (Gesamtaudit 01.11., GA-F08)
    "finance.CashCount",
    "statutes.StatuteVersion",
    "statutes.StatutePublication",
    "documents.Folder",
    "documents.Document",
    "documents.DocumentVersion",
    "todos.TodoAttachment",
    "members.HonoraryTitle",
    "members.HonoraryTitleAward",
    # Ansprechpartner von Organisationsmitgliedern (J2)
    "members.ContactPerson",
    "members.BillingAddress",
    "honors.Dignity",
    "honors.Reign",
    "honors.Companion",
    "honors.ReignPhoto",
    "events.EventCategory",
    # Fremde Kalender vor den Terminen (Verweis der Kopien); Token und Link kommen nicht mit
    "events.ExternalCalendar",
    "events.Event",
    "events.EventException",
    "events.EventAttachment",
    "events.CalendarPublication",
    "events.EventResponse",
    "music.Performance",
    "music.EnsembleTemplate",
    "music.EnsembleTemplatePosition",
    "music.Position",
    "music.Assignment",
    "music.PerformanceNotice",
    "music.PerformanceAccount",
    "music.EngagementDocument",
    "music.FeeTemplate",
    "music.MusicianClaim",
    "music.PerformanceExpense",
    "music.PayoutRun",
    "music.PayoutItem",
    "music.PreviousPerformanceInvoice",
    "music.Piece",
    "music.Arrangement",
    "music.ScorePart",
    "music.ScoreDocument",
    "music.ScoreFolder",
    "music.ScoreFolderUnit",
    "music.ScoreFolderItem",
    "music.ProgramEntry",
    "music.Rehearsal",
    "music.RehearsalItem",
    "music.MusicLeader",
    "music.RehearsalProgram",
    "music.RehearsalProgramItem",
    "music.RehearsalInvitation",
    "music.RehearsalResponse",
    "music.ScoreLoan",
    "music.ScoreReturn",
    "materials.MaterialItem",
    "music.Equipment",
    "music.EquipmentLoan",
    "music.EquipmentMaintenance",
    "materials.MaterialEventLink",
    "materials.MaterialTodoLink",
    "materials.MaterialDocumentLink",
    "materials.MaterialPhoto",
    # Anlagenverzeichnis nach Buchungen und Inventar (Verweise auf beide)
    "finance.FixedAsset",
    # Wettbewerbe nach den Terminen (Verweis auf den Termin)
    "competitions.Series",
    "competitions.Trophy",
    "competitions.CertificateTemplate",
    "competitions.Competition",
    "competitions.ShootingProgram",
    "competitions.Scoring",
    "competitions.Starter",
    "competitions.Score",
    "competitions.Hit",
    "competitions.ShootOff",
    "competitions.ShootOffEntry",
    "competitions.Shot",
    "competitions.Prize",
    "competitions.Team",
    "competitions.TeamMember",
    "competitions.Placing",
    "competitions.Award",
    "competitions.AwardGrant",
    # Meldungen nach den Wettbewerben (Verweise auf Wettbewerb, Mannschaft und Starter)
    "entries.Call",
    "entries.CallBlock",
    "entries.Entry",
    "entries.EntryTeam",
    "entries.EntryPerson",
    "entries.EntryAnswer",
    "entries.EntryVersion",
    # Buchungskalender nach Material, Terminen und Wettbewerben; Belegungen (BookingSlot)
    # werden nach dem Import neu ausgerechnet
    "bookings.Booking",
    "bookings.BookingException",
    # Versammlungen nach den Terminen (jede Versammlung hat ihren Termin)
    "meetings.MeetingKind",
    "meetings.Meeting",
    "meetings.AgendaItem",
    "meetings.Resolution",
    "meetings.Attendance",
    "meetings.MinutesVersion",
    "meetings.Motion",
    # Kassenprüfung nach den Versammlungen (Verknüpfung zum Bericht der Kassenprüfer)
    "finance.CashAudit",
    "finance.CashAuditSample",
    "finance.CashAuditAccount",
    # Helferdienste nach den Terminen (ein Plan kann an einem Termin hängen)
    "helpers.HelperPlan",
    "helpers.Duty",
    "helpers.Shift",
    "helpers.ShiftQuota",
    "helpers.ShiftAssignment",
    "circulars.CircularTemplate",
    "circulars.Circular",
    "circulars.CircularAttachment",
    "circulars.CircularRecipient",
    "website.Website",
    "website.WebsiteImage",
    "website.WebsiteText",
    "website.WebsiteRevision",
    # Galerie (Ralf 05.11.2026): Alben vor ihren Bildern
    "website.GalleryAlbum",
    "website.GalleryItem",
    # Pressespiegel und eigene Dokumente (Ralf 05.11.)
    "website.WebsiteDocument",
    "website.PublicationConsent",
    # Social-Media-Beiträge mit Freigabe/Ausblendung (Audit 31.10. D31-03); Zugangsdaten
    # zu Meta kommen nicht mit (SECRET_FIELDS), der Kanal muss neu verbunden werden
    "website.SocialFeed",
    "website.SocialPost",
    "website.SocialPostImage",
)

# Diese Tabellen gehören zu jeder Organisation und zu Abteilungen (Spalte department),
# nicht zum Kassen- und Beitragsbereich: Sie kommen immer mit.
PUBLIC_MODELS = {"statutes.statuteversion", "statutes.statutepublication"}
# Die Dokumentenablage kommt im vollständigen Export und im Export einer Abteilung
# mit, nicht aber im Dachverbands-Export der Vereine (dort nur die Satzung).
DEPARTMENT_MODELS = {
    "meetings.meetingkind",
    "meetings.meeting",
    "meetings.agendaitem",
    "meetings.resolution",
    "meetings.minutesversion",
    "helpers.helperplan",
    "helpers.duty",
    "helpers.shift",
    "helpers.shiftquota",
    "bookings.booking",
    "bookings.bookingexception",
    "materials.materialitem",
    "materials.materialeventlink",
    "materials.materialtodolink",
    "materials.materialdocumentlink",
    "materials.materialphoto",
    "todos.todoseries",
    "documents.folder",
    "documents.document",
    "documents.documentversion",
    "todos.todo",
    "todos.todoattachment",
}
# Mitgliederbezogene Tabellen: kommen mit, wenn die Mitgliedsdaten mitkommen
# (nicht im Export einer Abteilung).
MEMBER_MODELS = {
    "members.honorarytitle",
    "members.honorarytitleaward",
    "events.eventresponse",
    "circulars.circularrecipient",
    "website.publicationconsent",
    "honors.dignity",
    "honors.reign",
    "honors.companion",
    "honors.reignphoto",
    # Wettbewerbe verweisen auf Mitgliedschaften (Starter, Schützen im Stechen)
    "competitions.competition",
    "competitions.scoring",
    "competitions.starter",
    "competitions.score",
    "competitions.hit",
    "competitions.shootoff",
    "competitions.shootoffentry",
    "competitions.shot",
    "competitions.prize",
    "competitions.team",
    "competitions.teammember",
    "competitions.placing",
    "competitions.series",
    "competitions.trophy",
    "competitions.certificatetemplate",
    "competitions.award",
    "competitions.awardgrant",
    # Meldungen nennen Mitglieder (gemeldete Personen, Fassungen mit Angaben je Person)
    "entries.entry",
    "entries.entryteam",
    "entries.entryperson",
    "entries.entryanswer",
    "entries.entryversion",
    # Anwesenheit nennt Mitglieder (Name, Vertretung)
    "meetings.attendance",
    # Anträge nennen das Mitglied, das sie gestellt hat
    "meetings.motion",
    # Einteilungen nennen Mitglieder und Externe mit Telefon
    "helpers.shiftassignment",
}
# Ein Abteilungsimport legt eine neue Untereinheit im bestehenden Verein an. Er darf nur
# die Tabellen schreiben, die auch der Export einer Abteilung enthält, nie Kasse oder
# Beiträge des Vereins (dafür fehlen dem Importierenden ggf. die Rechte).
DEPARTMENT_IMPORT_MODELS = PUBLIC_MODELS | DEPARTMENT_MODELS
# Zeilen, deren Verweis auf diese Spalte in der Datei fehlt, fallen beim Import weg
# (z. B. Ehrungen des Dachverbands an Personen, deren Daten nicht exportiert wurden).
DROP_IF_MISSING = {
    "bookings.booking": "item",
    "bookings.bookingexception": "booking",
    "materials.materialeventlink": "item",
    "materials.materialtodolink": "todo",
    "materials.materialdocumentlink": "document",
    "materials.materialphoto": "item",
    "todos.todoattachment": "todo",
    "members.honorarytitleaward": "person",
    "events.eventresponse": "membership",
    # Empfänger in anderen Vereinen (Rundschreiben des Dachverbands) kommen nicht mit
    "circulars.circularrecipient": "club",
    # Bild nicht in der Datei (Export ohne Dateien): fällt aus dem Album
    "website.galleryitem": "image",
}


def _new_statute_key():
    from statutes.models import StatutePublication

    return StatutePublication.new_key()


# Werte, die beim Import neu entstehen müssen (z. B. eindeutige öffentliche Schlüssel)
def _new_folder_key():
    from documents.models import Folder

    return Folder.new_key()


def _new_social_key():
    from website.social_models import SocialPostImage

    return SocialPostImage.new_key()


def _new_calendar_key():
    from events.models import CalendarPublication

    return CalendarPublication.new_key()


def _new_website_key():
    from website.models import Website

    return Website.new_key()


def _new_photo_key():
    from honors.models import ReignPhoto

    return ReignPhoto.new_key()


FRESH_VALUES = {
    "statutes.statutepublication": {"public_key": _new_statute_key},
    "documents.folder": {"public_key": _new_folder_key},
    "events.calendarpublication": {"public_key": _new_calendar_key},
    # Eine übernommene Webseite startet in der Wartung; Domains und Vorschau-Links
    # kommen nicht mit, die Auswahl der Untereinheiten verweist auf alte Nummern.
    "honors.reignphoto": {"key": _new_photo_key},
    "website.website": {
        "public_key": _new_website_key,
        "state": lambda: "maintenance",
        "unit_ids": list,
        "units_mode": lambda: "all",
    },
    "website.socialpostimage": {"key": _new_social_key},
}

# Nie exportiert: Zugangsdaten und Anmeldezustand (Social-Media-Kanäle)
SECRET_FIELDS = {
    "todos.todoseries": {"owner", "source_series", "shares", "documents"},
    # Zugriffsrechte werden am Ziel ausdrücklich neu vergeben, keine fremden Kontonummern.
    "todos.todo": {
        "origin",
        "remote_origin",
        "remote_mode",
        "owner",
        "done_by",
        "shared",
        "per_unit",
        "distributed",
        "central_attachment_ids",
    },
    # Freigaben gelten nur für die lokale Kopplung, nie für importierte Nummern.
    "competitions.starter": {"result_coupling"},
    "events.externalcalendar": {
        "token",
        "secret",
        "last_error",
        "last_sync_at",
        "last_successful_sync_at",
    },
    "website.socialfeed": {
        "sync_job_id",
        "sync_requested_at",
        "app_secret",
        "access_token",
        "token_expires_at",
        "token_refreshed_at",
        "pending_pages",
        "oauth_state",
        "oauth_started_at",
        "oauth_user",
        "connected_at",
        "status",
        "last_error",
        "last_sync_at",
        "warned_at",
    },
}

SKIP = {
    "id",
    "organization",
    "created_by",
    "uploaded_by",
    "closed_by",
    "deleted_by",
    "recorded_by",
    "created_at",
    "updated_at",
}

# Ziele von Fremdschlüsseln, die aus dem übrigen Export kommen
CORE_TARGETS = {
    "organizations.organization": "organization",
    "organizations.department": "department",
    "members.membership": "membership",
    "members.membertype": "member_type",
    "members.person": "person",
}


# Erlaubte Dateiarten je Tabelle (am Inhalt erkannt, wie beim normalen Hochladen)
FILE_TYPES = {
    "materials.materialphoto": {"image/jpeg"},
    "finance.receipt": {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
    },
    "statutes.statuteversion": {"application/pdf"},
    "finance.donationstatement": {"application/pdf"},
    "billing.invoice": {"application/pdf"},
    "events.eventattachment": {"application/pdf", "image/jpeg", "image/png"},
    "circulars.circularattachment": {"application/pdf"},
    "website.websiteimage": {"image/jpeg", "image/png"},
    "website.websitedocument": {"application/pdf", "image/jpeg", "image/png"},
    "website.socialpostimage": {"image/jpeg", "image/png", "image/webp"},
    "honors.reignphoto": {"image/jpeg", "image/png"},
    "finance.cashcount": {"application/pdf"},
}

# Versammlungsdaten ohne eigene Spalte für die Untereinheit
MEETING_CHILDREN = ("meetings.agendaitem", "meetings.resolution", "meetings.minutesversion")
HELPER_CHILDREN = {
    "helpers.duty": "plan__department",
    "helpers.shift": "duty__plan__department",
    "helpers.shiftquota": "shift__duty__plan__department",
}
# Dateien mit gespeicherter Prüfsumme: Inhalt muss unverändert sein
FILE_HASHES = {
    "finance.cashcount": "pdf_sha256",
    "finance.bankstatement": "source_sha256",
    "meetings.minutesversion": "sha256",
}


def check_file(name: str, obj, content: bytes, path: str, field_name: str = "") -> None:
    """Datei aus dem Import prüfen; die Dateiart kommt aus dem Inhalt, nicht aus der Datei."""
    from django.core.exceptions import ValidationError

    from core.filecheck import sniff

    if name in {
        "billing.invoiceartifact",
        "billing.incominginvoice",
        "billing.incomingvalidation",
        "billing.invoicehybridartifact",
    }:
        import hashlib
        from xml.etree.ElementTree import ParseError

        from defusedxml import ElementTree
        from defusedxml.common import DefusedXmlException

        if len(content) > 15 * 1024 * 1024:
            raise ValidationError(gettext("Die Datei ist größer als 15 MB."))
        hash_field = {
            "original": "sha256",
            "xml": "sha256" if name == "billing.invoiceartifact" else "",
            "cancellation_xml": "cancellation_sha256",
        }.get(field_name)
        if name == "billing.invoicehybridartifact":
            hash_field = {"pdf": "sha256", "xml": "xml_sha256"}.get(field_name)
        if hash_field and hashlib.sha256(content).hexdigest() != getattr(obj, hash_field):
            raise ValidationError(gettext("Die Prüfsumme des Rechnungsoriginals stimmt nicht."))
        if name == "billing.invoicehybridartifact" and field_name == "pdf":
            if sniff(content) != "application/pdf":
                raise ValidationError(gettext("Die Datei ist keine PDF-Datei."))
            return
        # Ungültige Eingänge bleiben absichtlich als unveränderte, private Originale
        # erhalten. Reports und ausgegebene Rechnungen müssen sich sicher lesen lassen.
        if name == "billing.incominginvoice" and field_name in {"original", "xml"}:
            return
        try:
            ElementTree.fromstring(content, forbid_dtd=True)
        except (ParseError, DefusedXmlException) as exc:
            raise ValidationError(gettext("Die Datei ist kein gültiges XML.")) from exc
        return
    if name == "finance.receipt" and getattr(obj, "content_type", "") in {
        "text/xml",
        "application/xml",
    }:
        from finance.einvoice import EInvoiceError, parse_xml

        try:
            parse_xml(content)
        except EInvoiceError as exc:
            raise ValidationError(str(exc)) from exc
        return

    if name in {"documents.documentversion", "todos.todoattachment"}:
        from documents import notation
        from documents.services import ALLOWED_TYPES

        fname = getattr(obj, "name", "") or path
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if name == "documents.documentversion" and ext in notation.NOTATION_TYPES:
            ctype, magic = notation.NOTATION_TYPES[ext]
            if magic and not content.startswith(magic):
                raise ValidationError(
                    gettext("Datei „{fname}“: Inhalt und Dateiendung passen nicht.").format(
                        fname=fname
                    )
                )
            try:
                notation.check(content, ctype)
            except ValidationError as exc:
                raise ValidationError(
                    gettext("Datei „{fname}“: Die Notendatei lässt sich nicht lesen.").format(
                        fname=fname
                    )
                ) from exc
            obj.content_type = ctype
            return
        if ext not in ALLOWED_TYPES:
            raise ValidationError(
                gettext("Datei „{fname}“: Diese Dateiart ist nicht erlaubt.").format(fname=fname)
            )
        ctype, magic = ALLOWED_TYPES[ext]
        if magic is None:
            if b"\x00" in content[:4096]:
                raise ValidationError(
                    gettext("Datei „{fname}“ ist keine Textdatei.").format(fname=fname)
                )
        elif not content.startswith(magic):
            raise ValidationError(
                gettext("Datei „{fname}“: Inhalt und Dateiendung passen nicht.").format(fname=fname)
            )
        obj.content_type = ctype
        if name == "todos.todoattachment":
            from documents.models import MAX_DOCUMENT_BYTES
            from documents.services import check_budget

            if len(content) > MAX_DOCUMENT_BYTES:
                raise ValidationError(gettext("Die Datei ist größer als 20 MB."))
            check_budget(obj.organization, len(content))
            obj.size = len(content)
            obj.kind = "file"
            obj.document_id = None
        return
    hash_field = FILE_HASHES.get(name)
    if hash_field and getattr(obj, hash_field, ""):
        import hashlib

        if hashlib.sha256(content).hexdigest() != getattr(obj, hash_field):
            raise ValidationError(
                gettext("Datei „{path}“ passt nicht zu ihrer Prüfsumme.").format(path=path)
            )
    if name == "finance.bankstatement":
        # Original eines Kontoauszugs (CAMT als XML oder ZIP), Gesamtaudit 01.11., GA-F09
        from finance import camt

        try:
            camt.parse(content)
        except camt.CamtError as exc:
            raise ValidationError(
                gettext("Datei „{path}“ ist kein lesbarer Kontoauszug.").format(path=path)
            ) from exc
        return
    allowed = FILE_TYPES.get(name)
    if allowed is None:
        raise ValidationError(
            gettext("Datei „{path}“ wird hier nicht übernommen.").format(path=path)
        )
    ctype = sniff(content)
    if ctype not in allowed:
        raise ValidationError(
            gettext("Datei „{path}“: Diese Dateiart ist nicht erlaubt.").format(path=path)
        )
    if hasattr(obj, "content_type"):
        obj.content_type = ctype


def fix_json_ids(name: str, obj, ids: IdMap) -> None:
    """Kennungen in JSON-Feldern auf die neuen Zeilen umstellen (GA-F08)."""
    if name == "finance.cashcount":
        obj.booking_ids = [
            new for old in obj.booking_ids or [] if (new := ids.get("finance.booking", old))
        ]
        lines = []
        for line in obj.lines or []:
            line = dict(line)
            line["category"] = ids.get("finance.category", line.get("category"))
            lines.append(line)
        obj.lines = lines
    if name == "meetings.meetingkind":
        obj.voter_types = [
            new for old in obj.voter_types or [] if (new := ids.get("member_type", old))
        ]


def fix_website_keys(name: str, obj, ids: IdMap) -> None:
    """Bilder der Webseite behalten ihre Kennung (Texte verweisen mit ``bild:<key>``
    darauf). Ist sie hier schon vergeben, bekommt das Bild eine neue, und die Texte
    werden angepasst."""
    from website.models import WebsiteDocument, WebsiteImage
    from website.timeline import entry_images, with_images

    renamed = ids.maps.setdefault("website.imagekey", {})
    if name == "website.websitedocument":
        if not obj.key or WebsiteDocument.objects.filter(key=obj.key).exists():
            obj.key = WebsiteDocument.new_key()
    elif name == "website.websiteimage":
        if not obj.key or WebsiteImage.objects.filter(key=obj.key).exists():
            new = WebsiteImage.new_key()
            if obj.key:
                renamed[obj.key] = new
            obj.key = new
    elif name == "website.website":
        # Menü und Häkchen verweisen mit ``dignity:<Nummer>`` auf Würden und mit
        # ``membertype:<Nummer>`` auf Mitgliedsarten: neue Nummern
        targets = {"dignity": "honors.dignity", "membertype": "member_type"}

        def remap(key):
            prefix = key.split(":", 1)[0] if isinstance(key, str) else None
            if prefix not in targets:
                return key
            try:
                new = ids.get(targets[prefix], key.split(":", 1)[1])
            except ValueError:
                return None
            return f"{prefix}:{new}" if new is not None else None

        if isinstance(obj.blocks, dict):
            obj.blocks = {remap(k): v for k, v in obj.blocks.items() if remap(k) is not None}
        if isinstance(obj.menu, list):
            obj.menu = [
                {
                    **node,
                    "key": remap(node.get("key")),
                    "children": [
                        {**c, "key": remap(c.get("key"))}
                        for c in node.get("children") or []
                        if isinstance(c, dict) and remap(c.get("key")) is not None
                    ],
                }
                for node in obj.menu
                if isinstance(node, dict) and remap(node.get("key")) is not None
            ]
        if isinstance(obj.block_names, dict):
            obj.block_names = {
                remap(k): v for k, v in obj.block_names.items() if remap(k) is not None
            }
        # Hervorgehobener Menüpunkt (z. B. eine Textseite) zeigt auf die neue Nummer
        if getattr(obj, "menu_button", ""):
            obj.menu_button = remap(obj.menu_button) or ""
        # Ziel der Hinweisleiste (G6): Menüpunkt oder Termin mit neuer Nummer
        target = getattr(obj, "notice_target", None)
        if isinstance(target, dict) and "page" in target:
            page = remap(target["page"])
            obj.notice_target = {"page": page} if page else {}
        elif isinstance(target, dict) and "event" in target:
            try:
                new = ids.get("events.event", target["event"])
            except (TypeError, ValueError):
                new = None
            obj.notice_target = {"event": new} if new is not None else {}
        # Entwurf der Gestaltung verweist auf Bildnummern des alten Servers: nicht übernehmen
        obj.draft = {}
        # Abschnitte der Startseite: Bilder kommen erst nach der Webseite, ihre Verweise
        # fallen weg (der Abschnitt bleibt und lässt sich neu bestücken)
        from website.home import remap as remap_sections

        obj.home_sections = remap_sections(obj.home_sections, ids.get)
    elif name in ("website.websitetext", "website.websiterevision"):
        # Abschnitte (G3/G4) verweisen mit Nummern auf Bilder, Alben, Termine und Rollen
        from website.home import remap as remap_sections

        for field in ("sections", "published_sections"):
            if isinstance(getattr(obj, field, None), list):
                setattr(obj, field, remap_sections(getattr(obj, field), ids.get))
        for old, new in renamed.items():
            for field in ("body", "published_body"):
                if hasattr(obj, field):
                    setattr(obj, field, getattr(obj, field).replace(f"bild:{old}", f"bild:{new}"))
        # Bilderkarussell verweist mit Nummern auf die Bilder: auf die neuen umstellen
        for field in ("gallery", "published_gallery"):
            if isinstance(getattr(obj, field, None), list):
                mapped = [ids.get("website.websiteimage", pk) for pk in getattr(obj, field)]
                setattr(obj, field, [pk for pk in mapped if pk is not None])
        # Zeitleiste der Chronik: Bildnummern ebenso umstellen
        for field in ("timeline", "published_timeline"):
            entries = getattr(obj, field, None)
            if isinstance(entries, list):
                setattr(
                    obj,
                    field,
                    [
                        with_images(
                            e,
                            [
                                pk
                                for pk in (
                                    ids.get("website.websiteimage", i) for i in entry_images(e)
                                )
                                if pk is not None
                            ],
                        )
                        if isinstance(e, dict)
                        else e
                        for e in entries
                    ],
                )


def check_cash_receipts(tables: dict, warn) -> None:
    """Ältere Exporte enthalten keine Quittungen: darauf hinweisen (Gesamtaudit 30.10.)."""
    if not isinstance(tables, dict) or tables.get("finance.cashreceipt"):
        return
    quittung = [
        b
        for b in tables.get("finance.booking") or []
        if isinstance(b, dict) and b.get("reference") == "Quittung"
    ]
    if quittung:
        warn(
            f"Die Datei enthält {len(quittung)} Buchung(en) aus Quittungen, aber keine "
            "Quittungen (älterer Export). Unterschriften und Stornomöglichkeit fehlen danach; "
            "die Buchungen sind nicht gegen Änderungen gesperrt."
        )


def label(model) -> str:
    return model._meta.label_lower


def module_models() -> list[type[models.Model]]:
    result = []
    for name in MODULE_MODELS:
        app_label, model_name = name.split(".")
        if not apps.is_installed(app_label):
            continue
        try:
            result.append(apps.get_model(app_label, model_name))
        except LookupError:
            continue
    return result


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    return value


def dump_rows(model, org, packer, department=None) -> list[dict]:
    rows = []
    secret = SECRET_FIELDS.get(label(model), set())
    fields = [f for f in model._meta.concrete_fields if f.name not in SKIP | secret]
    qs = model.objects.filter(organization=org)
    if model._meta.app_label == "materials":
        from materials.exports import rows as material_rows

        qs = material_rows(model, org, department)
    if model._meta.app_label == "bookings":
        from materials.exports import rows as material_rows
        from materials.models import MaterialItem

        items = material_rows(MaterialItem, org, department)
        qs = qs.filter(
            **{"item__in" if label(model) == "bookings.booking" else "booking__item__in": items}
        )
    if label(model) == "todos.todo":
        from todos.exports import shared_rows

        qs = shared_rows(org, department)
    elif label(model) == "todos.todoseries":
        from todos.exports import series_rows

        qs = series_rows(org, department)
    elif label(model) == "todos.todoattachment":
        from todos.exports import attachment_rows

        qs = attachment_rows(org, department)
    if department is not None and label(model) in MEETING_CHILDREN:
        qs = qs.filter(meeting__department=department)
    elif department is not None and label(model) in HELPER_CHILDREN:
        qs = qs.filter(**{HELPER_CHILDREN[label(model)]: department})
    elif department is not None and label(model) != "bookings.bookingexception":
        # Ausfälle hängen an der Buchung; die ist oben schon auf die Abteilung begrenzt
        qs = qs.filter(department=department)
    templates = {}
    if label(model) == "todos.todoseries":
        from todos.exports import shared_rows

        for task in (
            shared_rows(org, department)
            .only("series_id", "sequence_no", "title", "description", "due_time", "timezone")
            .order_by("sequence_no", "pk")
        ):
            templates[task.series_id] = task
    for obj in qs.order_by("pk"):
        row = {"id": obj.pk}
        for f in fields:
            if label(model) == "todos.todoseries" and f.name in {
                "title",
                "description",
                "due_time",
                "timezone",
            }:
                row[f.name] = _plain(getattr(templates[obj.pk], f.name))
            elif f.is_relation:
                row[f.name] = getattr(obj, f.attname)
            elif isinstance(f, models.FileField):
                row[f.name] = packer.add(getattr(obj, f.name), label(model).replace(".", "-"))
            else:
                row[f.name] = _plain(getattr(obj, f.attname))
        if label(model) == "materials.materialitem":
            from materials.exports import redact_member

            redact_member(row, obj)
        if label(model) == "todos.todoattachment" and obj.kind == "document":
            from todos.attachments import document_for
            from todos.exports import export_scope

            if (
                document_for(
                    obj, export_scope(org, obj.department if obj.department_id else department)
                )
                is None
            ):
                row["document"] = None
        rows.append(row)
    return rows


def dump_tables(
    org, packer, *, everything=True, department=None, members=True
) -> dict[str, list[dict]]:
    """Alle Modultabellen (``everything``) oder nur die immer enthaltenen.

    Mit ``department`` nur die Zeilen dieser Abteilung (Export einer Abteilung).
    ``members``: mitgliederbezogene Tabellen (Ehrungen) mitnehmen.
    """
    tables = {}
    for model in module_models():
        name = label(model)
        if name in MEMBER_MODELS:
            if department is not None or not members:
                continue
        elif department is not None:
            if name not in PUBLIC_MODELS and name not in DEPARTMENT_MODELS:
                continue
        elif not everything and name not in PUBLIC_MODELS:
            continue
        rows = dump_rows(model, org, packer, department)
        if rows:
            tables[label(model)] = rows
    return tables


class IdMap:
    """Nummern der Quelle → neue Nummern, je Tabelle."""

    def __init__(self):
        self.maps: dict[str, dict[int, int]] = {}

    def set(self, table: str, old, new: int) -> None:
        if old is not None:
            self.maps.setdefault(table, {})[int(old)] = new

    def get(self, table: str, old):
        if old is None:
            return None
        return self.maps.get(table, {}).get(int(old))


def target_key(field) -> str:
    target = label(field.related_model)
    return CORE_TARGETS.get(target, target)


# Fachfrage 12 (Audit 31.10.): bewusst nicht mitgenommen, im Umzugsbericht genannt
NOT_INCLUDED = [
    "Zurückgehaltene Nachrichten des Kontaktformulars",
    "Vorlagen für Rundschreiben",
    "Änderungsprotokoll (bleibt auf der alten Instanz)",
    "Zugangsdaten für Instagram/Facebook (neu verbinden)",
    "Anmeldung an der Nextcloud (neu eintragen, neues Geheimnis)",
    "Benutzerkonten und Passwörter",
]


def check_tables(
    tables: dict,
    known: dict[str, set],
    errors: list,
    where: str,
    allowed: set | None = None,
    per_class: dict | None = None,
) -> int:
    """Prüft Tabellen und Verweise. ``known`` = Nummern je Ziel, die die Datei enthält.

    ``allowed``: nur diese Tabellen dürfen vorkommen (z. B. beim Abteilungsimport).
    """
    count = 0
    models_by_label = {label(m): m for m in module_models()}
    if not isinstance(tables, dict):
        errors.append(
            gettext("{where}: Die Tabellen in der Datei sind ungültig.").format(where=where)
        )
        return 0
    for name in list(tables):
        if name in models_by_label and allowed is not None and name not in allowed:
            errors.append(
                gettext(
                    "{where}: Tabelle „{name}“ darf bei diesem Import nicht übernommen werden."
                ).format(where=where, name=name)
            )
    for name, rows in tables.items():
        model = models_by_label.get(name)
        if model is None:
            errors.append(
                gettext("{where}: Tabelle „{name}“ ist hier unbekannt.").format(
                    where=where, name=name
                )
            )
            continue
        if allowed is not None and name not in allowed:
            continue
        ids = known.setdefault(name, set())
        for row in rows:
            if isinstance(row, dict) and "id" in row:
                ids.add(row["id"])
    for name, rows in tables.items():
        model = models_by_label.get(name)
        if model is None or (allowed is not None and name not in allowed):
            continue
        relations = [
            f
            for f in model._meta.concrete_fields
            if f.is_relation and f.name not in SKIP and label(f.related_model) != "accounts.user"
        ]
        if per_class is not None and rows:
            key = str(model._meta.verbose_name_plural)
            per_class[key] = per_class.get(key, 0) + len(rows)
        for row in rows:
            count += 1
            try:
                validate_url_data(model, row)
            except ValidationError as exc:
                errors.append(
                    gettext("{where}: {name} {x2}: {x3}").format(
                        where=where, name=name, x2=row.get("id"), x3="; ".join(exc.messages)
                    )
                )
            for f in relations:
                value = row.get(f.name)
                if value is None:
                    continue
                if value not in known.get(target_key(f), set()):
                    if f.null or DROP_IF_MISSING.get(name) == f.name:
                        continue  # Verweis fällt weg (z. B. Mitglied nicht in der Datei)
                    errors.append(
                        gettext(
                            "{where}: {x1} {x2} verweist auf „{x3}“ {value}, das in der Datei "
                            "fehlt."
                        ).format(
                            where=where,
                            x1=model._meta.verbose_name,
                            x2=row.get("id"),
                            x3=f.verbose_name,
                            value=value,
                        )
                    )
    return count


def load_tables(tables: dict, org, ids: IdMap, files, user=None, allowed=None) -> int:
    """Legt die Zeilen in der Reihenfolge von ``MODULE_MODELS`` an.

    ``allowed``: nur diese Tabellen anlegen; andere in der Datei brechen den Import ab.
    """
    from django.core.files.base import ContentFile

    count = 0
    if allowed is not None:
        extra = sorted(set(tables or {}) - set(allowed))
        if extra:
            raise ValidationError(
                gettext("Tabelle „{x}“ darf hier nicht importiert werden.").format(x=extra[0])
            )
    for model in module_models():
        name = label(model)
        rows = (tables or {}).get(name) or []
        secret = SECRET_FIELDS.get(name, set())
        fields = [f for f in model._meta.concrete_fields if f.name not in SKIP | secret]
        drop_key = DROP_IF_MISSING.get(name)
        if name == "website.galleryalbum":
            # Oberalben zuerst, damit Unteralben ihr Oberalbum finden
            rows = sorted(rows, key=lambda r: isinstance(r, dict) and r.get("parent") is not None)
        if name == "meetings.attendance":
            # Vertretene nach ihren Vertretern (Verweis auf die eigene Tabelle)
            rows = sorted(
                rows, key=lambda r: isinstance(r, dict) and r.get("represented_by") is not None
            )
        if name == "materials.materialitem":
            # Infrastruktur vor Material, Gebäude vor ihren Bereichen (Verweise auf sich selbst)
            rows = sorted(
                rows,
                key=lambda r: (
                    isinstance(r, dict) and r.get("kind", "material") != "facility",
                    isinstance(r, dict) and r.get("location_kind") == "facility",
                ),
            )
        for row in rows:
            if drop_key:
                field = model._meta.get_field(drop_key)
                if ids.get(target_key(field), row.get(drop_key)) is None:
                    continue
            obj = model(organization=org)
            pending_files = []
            for f in fields:
                if f.name not in row:
                    continue
                value = row[f.name]
                if f.is_relation:
                    if label(f.related_model) == "accounts.user":
                        continue
                    setattr(obj, f.attname, ids.get(target_key(f), value))
                elif isinstance(f, models.FileField):
                    if value:
                        pending_files.append((f.name, value))
                else:
                    setattr(obj, f.attname, f.to_python(value))
            for field_name, make in FRESH_VALUES.get(name, {}).items():
                setattr(obj, field_name, make())
            fix_website_keys(name, obj, ids)
            fix_json_ids(name, obj, ids)
            if name.startswith("materials."):
                if name == "materials.materialitem":
                    if obj.location_kind == "member" and not obj.member_id:
                        obj.location_kind = "unknown"
                    if obj.location_kind != "member":
                        obj.member_id = None
                    if obj.location_kind == "facility" and not obj.facility_id:
                        obj.location_kind = "unknown"
                    if obj.location_kind != "facility":
                        obj.facility_id = None
                elif not getattr(obj, "item_id", None):
                    continue
            if hasattr(obj, "created_by_id") and user is not None:
                obj.created_by_id = user.pk
            if name == "todos.todo":
                # Übernahme erhält Inhalt, aber keine Freigaben der Quelle.
                obj.owner_id = user.pk if user is not None else None
                obj.shared = False
                if obj.local_note:
                    obj.description = (
                        f"{obj.description}\n\n{gettext('Lokale Notiz')}:\n{obj.local_note}".strip()
                    )
                    obj.local_note = ""
            if name == "todos.todoseries":
                obj.owner_id = user.pk if user is not None else None
                obj.active = False
                obj.kind = "sequence"
            for field_name, path in pending_files:
                content = files.read(path)
                if content is not None:
                    check_file(name, obj, content, path, field_name)
                    getattr(obj, field_name).save(
                        path.rsplit("/", 1)[-1].split("-", 1)[-1], ContentFile(content), save=False
                    )
            if name == "todos.todoattachment" and obj.kind == "document":
                obj.file = ""
                if not obj.document_id:
                    continue
            elif any(f.name == "file" for f in fields) and not getattr(obj, "file", True):
                continue  # Beleg ohne Datei (Export ohne Dateien) wird nicht angelegt
            validate_urls(obj)
            obj.save()
            ids.set(name, row.get("id"), obj.pk)
            count += 1
    if (tables or {}).get("bookings.booking"):
        from bookings.models import Booking
        from bookings.services import rebuild

        # Belegungen werden nicht übertragen, sondern neu ausgerechnet
        for booking in Booking.objects.filter(
            pk__in=ids.maps.get("bookings.booking", {}).values()
        ).select_related("item"):
            rebuild(booking, strict=False)
    return count
