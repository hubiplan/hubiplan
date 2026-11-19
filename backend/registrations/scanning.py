"""Scanpersonal mit Link (Anmeldung A6, Konzept 3.11): Wer den Link auf dem Handy öffnet,
bekommt nur den Kartenscanner, ohne Konto und ohne Liste.

Ein Link gilt für eine Station: den Einlass (hakt die Person ab) oder eine Zusatzleistung
(löst sie ein, z. B. Essen ausgegeben). Der Scan zeigt, ob die Karte gilt, wofür (Termin,
Tarif, gebuchte Leistungen mit Zeitpunkt der Einlösung), ob sie schon gescannt wurde und wer
sie besitzt (Name und Geburtsdatum zum Abgleich mit dem Ausweis). Der Link läuft ab und lässt
sich jederzeit sperren.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets

from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from core.tenancy import rls_bypass

from . import materials, services, tickets
from .models import Booking, Participant, Redemption, Registration, ScanLink

MAX_LINKS = 20


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def default_expiry(setup) -> datetime.datetime:
    """Bis zum Ende des Tags nach der Veranstaltung."""
    event = setup.event
    end = timezone.localtime(event.ends_at or event.starts_at)
    day = end.date() + datetime.timedelta(days=1)
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(23, 59)))


def create(
    setup,
    *,
    label: str,
    addon=None,
    material=None,
    material_return=False,
    expires_at=None,
    allow_search=False,
    user=None,
) -> ScanLink:
    token = secrets.token_urlsafe(24)
    return ScanLink.objects.create(
        setup=setup,
        label=label.strip()[:100],
        addon=addon,
        material=material,
        material_return=bool(material) and material_return,
        token=token,
        token_hash=hash_token(token),
        expires_at=expires_at or default_expiry(setup),
        allow_search=allow_search,
        created_by=user,
    )


def url(link: ScanLink) -> str:
    from organizations.addresses import base_url

    return f"{base_url(link.setup.organization)}/kartenscan/{link.token}"


def usable(link: ScanLink, now: datetime.datetime | None = None) -> bool:
    now = now or timezone.now()
    org = link.setup.organization
    return (
        link.revoked_at is None
        and link.expires_at > now
        and org.is_active
        and services.module_on(org)
        and not link.setup.event.is_cancelled
    )


def link_by_token(token: str) -> ScanLink | None:
    """Gültiger Link zum Schlüssel, sonst None (auch abgelaufen oder gesperrt)."""
    if not token or len(token) > 100:
        return None
    with rls_bypass():
        link = (
            ScanLink.objects.select_related(
                "setup__organization", "setup__event", "addon", "material"
            )
            .filter(token_hash=hash_token(token))
            .first()
        )
    if link is None or not usable(link):
        return None
    return link


def kind(link: ScanLink) -> str:
    """entry | addon | material_out | material_return"""
    if link.material_id:
        return "material_return" if link.material_return else "material_out"
    return "addon" if link.addon_id else "entry"


def station(link: ScanLink) -> str:
    if link.material_id:
        return materials.station(link.material, link.material_return)
    return link.addon.name if link.addon_id else _("Einlass")


def link_data(link: ScanLink, *, with_url: bool = False) -> dict:
    data = {
        "id": link.pk,
        "label": link.label,
        "addon_id": link.addon_id,
        "material_id": link.material_id,
        "material_return": link.material_return,
        "kind": kind(link),
        "station": station(link),
        "expires_at": link.expires_at,
        "allow_search": link.allow_search,
        "revoked": link.revoked_at is not None,
        "active": usable(link),
        "created_at": link.created_at,
        "last_used_at": link.last_used_at,
        "scans": link.scans,
    }
    if with_url:
        data["url"] = url(link)
    return data


def page_data(link: ScanLink) -> dict:
    """Was die Scan-Seite oben zeigt."""
    event = link.setup.event
    return {
        "organization": link.setup.organization.name,
        "event": event.title,
        "starts_at": event.starts_at,
        "label": link.label,
        "station": station(link),
        "kind": kind(link),
        "expires_at": link.expires_at,
        "allow_search": link.allow_search,
    }


SEARCH_MIN = 3
SEARCH_MAX = 10


def search(link: ScanLink, term: str) -> list[dict]:
    """Angemeldete zum Namen (ohne Karte, nur bei ``allow_search``): höchstens zehn Treffer,
    erst ab drei Zeichen, damit niemand die ganze Liste abrufen kann. Namen sind
    verschlüsselt, daher wird in Python verglichen."""
    term = term.strip().casefold()
    if not link.allow_search or len(term) < SEARCH_MIN:
        return []
    rows = Participant.objects.filter(
        registration__setup_id=link.setup_id,
        registration__status=Registration.Status.REGISTERED,
        status=Participant.Status.ACTIVE,
    ).select_related("registration")
    hits = sorted(
        (p for p in rows if term in p.name.casefold()), key=lambda p: (p.name.casefold(), p.pk)
    )
    return [
        {
            "id": p.pk,
            "name": p.name,
            "birth_date": p.birth_date,
            "price_name": p.price_name,
            "number": p.registration.display_number,
            "checked_in_at": p.checked_in_at,
        }
        for p in hits[:SEARCH_MAX]
    ]


def _bookings(p: Participant) -> list[Booking]:
    reg = p.registration
    return [
        b
        for b in Booking.objects.filter(registration=reg)
        .select_related("choice__addon", "redemption")
        .order_by("pk")
        if b.participant_id in (None, p.pk)
    ]


def _redeemed_at(b: Booking):
    try:
        return b.redemption.at
    except Redemption.DoesNotExist:
        return None


def _card(p: Participant, now: datetime.datetime) -> dict:
    """Wer die Karte besitzt und wofür sie gilt."""
    reg = p.registration
    start = services.first_day(reg.setup)
    birth = p.birth_date
    return {
        "name": p.name,
        "birth_date": birth,
        "minor": bool(birth) and services.age_on(birth, start) < 18,
        "price_name": p.price_name,
        "number": reg.display_number,
        "paid_state": services.paid_state(reg),
        "checked_in_at": p.checked_in_at,
        "bookings": [
            {
                "id": b.pk,
                "addon_id": b.choice.addon_id,
                "name": b.name,
                "per_registration": b.participant_id is None,
                "redeemed_at": _redeemed_at(b),
            }
            for b in _bookings(p)
        ],
        "materials": materials.card_items(p),
    }


def message(result: str, link: ScanLink) -> str:
    k = kind(link)
    if result == "ok":
        return {
            "entry": _("Eingelassen."),
            "addon": _("Gültig, eingelöst."),
            "material_out": _("Ausgegeben."),
            "material_return": _("Zurückgenommen."),
        }[k]
    if result == "already":
        return {
            "entry": _("Schon eingelassen."),
            "addon": _("Schon eingelöst."),
            "material_out": _("Schon ausgegeben."),
            "material_return": _("Schon zurückgegeben."),
        }[k]
    return {
        "not_out": _("Dieses Material wurde nicht ausgegeben."),
        "unknown": _("Ungültige Karte."),
        "other": _("Diese Karte gilt für einen anderen Termin."),
        "cancelled": _("Diese Person ist abgemeldet."),
        "waiting": _("Diese Person steht auf der Warteliste."),
        "not_booked": _("Diese Leistung ist auf der Karte nicht gebucht."),
    }[result]


def scan(link: ScanLink, scanned: str = "", participant: int | None = None) -> dict:
    """Karte an der Station des Links prüfen und abhaken bzw. einlösen. Läuft im Bereich
    der Einheit (``tenant_context``) und in einer Transaktion."""
    now = timezone.now()
    ScanLink.objects.filter(pk=link.pk).update(scans=F("scans") + 1, last_used_at=now)
    # Ohne Karte nur mit Namenssuche (Ausweisabgleich durch das Personal)
    pk = participant if participant is not None and link.allow_search else None
    if pk is None:
        pk = tickets.participant_of(scanned)
    p = None
    if pk is not None:
        p = (
            Participant.objects.select_for_update(of=("self",))
            .select_related("registration__invoice", "registration__setup__event")
            .filter(pk=pk)
            .first()
        )
    if p is None:
        result, card, when = "unknown", None, None
    elif p.registration.setup_id != link.setup_id:
        result, card, when = "other", None, None
    else:
        reg = p.registration
        when = None
        if p.status != Participant.Status.ACTIVE or reg.status == Registration.Status.CANCELLED:
            result = "cancelled"
        elif reg.status == Registration.Status.WAITING:
            result = "waiting"
        elif link.material_id:
            action = "return" if link.material_return else "out"
            result, h = materials.apply(link.material, p, action, via=link.label)
            if h is not None:
                when = h.returned_at if link.material_return else h.handed_out_at
        elif not link.addon_id:
            if p.checked_in_at is not None:
                result, when = "already", p.checked_in_at
            else:
                p.checked_in_at = now
                p.checked_in_by = None
                p.checked_in_via = link.label
                p.save(update_fields=["checked_in_at", "checked_in_by", "checked_in_via"])
                result, when = "ok", now
        else:
            mine = [b for b in _bookings(p) if b.choice.addon_id == link.addon_id]
            if not mine:
                result = "not_booked"
            else:
                open_ = [b for b in mine if _redeemed_at(b) is None]
                if not open_:
                    result, when = "already", max(_redeemed_at(b) for b in mine)
                else:
                    Redemption.objects.create(booking=open_[0], participant=p, at=now, link=link)
                    result, when = "ok", now
        card = _card(p, now)
    return {
        "result": result,
        "valid": result == "ok",
        "message": message(result, link),
        "at": when,
        "card": card,
    }
