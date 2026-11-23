"""Köderdaten: erfundene Mitglieder, die niemand kennt und deren Benutzung Alarm auslöst.

Ein Köder ist ein erfundenes Mitglied im Datenbereich der Plattform selbst. Kein Verein, kein
Dachverband und keine App bekommt ihn zu sehen: Der Zeilenschutz der Datenbank gibt Mitglieder
nur an die Einheit heraus, der sie gehören, und die Plattform hat keinen Mitgliederbereich. In
der Datenbank und in jeder Sicherung steht er wie ein echtes Mitglied. Wer Daten an der
Anwendung vorbei abgreift (gestohlene Sicherung, Lücke in der Trennung der Vereine,
Durchprobieren von Nummern), nimmt ihn mit, und wer ihn benutzt, fällt auf:

- ``MAIL_IN``: Eine Mail an die Köderadresse kommt im Sammelpostfach der Verteiler an
  (``circulars.inbound``).
- ``LOGIN``: Jemand versucht, sich mit der Köderadresse anzumelden, oder fordert für sie
  einen Anmeldelink oder ein neues Passwort an.
- ``LOOKUP``: Jemand ruft die Nummer des Köder-Mitglieds über die Schnittstelle ab.
- ``MAIL_OUT``: HUBIplan selbst will der Köderadresse eine Mail schicken (sie wird nicht
  versendet). Das zeigt einen Fehler in der eigenen Abschottung.

Jede Auslösung steht unter Plattform › Sicherheit; je Art geht höchstens eine Alarm-Mail in
der Stunde hinaus (``core.alarm``). Keine Bankverbindung: Eine Lastschrift von einem fremden
Konto bemerkt HUBIplan nicht, und eine erfundene IBAN kann ein echtes Konto treffen.

Der Quelltext ist offen: Wer ihn kennt und Datenbank samt Schlüssel hat, kann Köder erkennen.
Gegen den üblichen Fall (Adressen abgreifen und benutzen) hilft es trotzdem.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import secrets

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core import alarm, ratelimit
from core.tenancy import rls_bypass

from .models import DecoyHit, Organization
from .views import IsPlatformAdmin

logger = logging.getLogger(__name__)

MAX_DECOYS = 5
MAX_ROWS = 500
SHOWN = 200
ALARM_PAUSE = 3600
CACHE_KEY = "koeder-stand"
CACHE_SECONDS = 300
_SALT = "organizations.decoys"

MAIL_IN = DecoyHit.Kind.MAIL_IN
MAIL_OUT = DecoyHit.Kind.MAIL_OUT
LOGIN = DecoyHit.Kind.LOGIN
LOOKUP = DecoyHit.Kind.LOOKUP

# Erfundene Personen: häufige Namen, damit ein Köder nicht auffällt
FIRST_NAMES = (
    ("Andrea", "f"),
    ("Bernd", "m"),
    ("Claudia", "f"),
    ("Dieter", "m"),
    ("Elke", "f"),
    ("Frank", "m"),
    ("Gisela", "f"),
    ("Holger", "m"),
    ("Ingrid", "f"),
    ("Jürgen", "m"),
    ("Karin", "f"),
    ("Lothar", "m"),
    ("Monika", "f"),
    ("Norbert", "m"),
    ("Petra", "f"),
    ("Rainer", "m"),
    ("Sabine", "f"),
    ("Uwe", "m"),
)
LAST_NAMES = (
    "Albers",
    "Brandt",
    "Dittmann",
    "Engels",
    "Franke",
    "Gerdes",
    "Hansen",
    "Jansen",
    "Kessler",
    "Lorenz",
    "Marquardt",
    "Nolte",
    "Petersen",
    "Reuter",
    "Sievers",
    "Thiele",
    "Vogt",
    "Wiese",
)
STREETS = ("Lindenweg", "Am Anger", "Birkenstraße", "Gartenweg", "Mühlenstraße", "Feldweg")
PLACES = (("12345", "Musterstadt"), ("54321", "Musterdorf"), ("23456", "Beispielhausen"))

# Aufrufe mit der Nummer einer Mitgliedschaft im Pfad und der Name dieser Nummer. Beim
# Dachverband und im Verbund steht dort eine andere Nummer (Person, Registereintrag).
MEMBER_ROUTE = re.compile(r"(?:^|/)(?<!federation/)members/<int:(pk|member_pk)>")
OTHER_NUMBERS = ("peering/",)
# Anmeldung, Anmeldelink und „Passwort vergessen“ (allauth headless)
AUTH_PATH = re.compile(r"/auth/(login|password/request|code/request)/?$")
MAX_AUTH_BODY = 4096


def _mark(address: str) -> str:
    return salted_hmac(_SALT, (address or "").strip().lower()).hexdigest()[:32]


def _platform_id() -> int | None:
    return (
        Organization.objects.filter(type=Organization.Type.PLATFORM)
        .values_list("pk", flat=True)
        .first()
    )


def _memberships():
    from members.models import Membership

    return (
        Membership.objects.filter(organization__type=Organization.Type.PLATFORM)
        .select_related("person")
        .order_by("pk")
    )


def _email_of(membership) -> str:
    contact = membership.person.contacts.order_by("pk").first()
    return (contact.email or "").strip().lower() if contact else ""


def current() -> dict:
    """Nummern und Adressmarken der Köder; kurz zwischengespeichert, ohne Klartext."""
    found = cache.get(CACHE_KEY)
    if found is not None:
        return found
    with rls_bypass():
        ids, marks = set(), {}
        for membership in _memberships():
            ids.add(membership.pk)
            email = _email_of(membership)
            if email:
                marks[_mark(email)] = membership.pk
    found = {"ids": ids, "marks": marks}
    cache.set(CACHE_KEY, found, CACHE_SECONDS)
    return found


def forget() -> None:
    cache.delete(CACHE_KEY)


def decoy_for_address(address: str) -> int | None:
    """Nummer des Köders mit dieser Adresse, sonst ``None``."""
    if not address or "@" not in address:
        return None
    return current()["marks"].get(_mark(address))


def _short(value: str, length: int = 200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:length]


LABELS = {
    MAIL_IN: "Mail an eine Köderadresse",
    MAIL_OUT: "HUBIplan wollte einer Köderadresse schreiben",
    LOGIN: "Anmeldeversuch mit einer Köderadresse",
    LOOKUP: "Abruf eines Köder-Mitglieds",
}


def hit(kind: str, membership_id: int | None, detail: str = "") -> None:
    """Auslösung vermerken und melden. Darf den eigentlichen Ablauf nie stören."""
    try:
        with rls_bypass():
            _record(kind, membership_id, _short(detail))
        if cache.add(f"koeder-alarm:{kind}", 1, ALARM_PAUSE):
            alarm.send_alert(
                f"Köderdaten: {LABELS.get(kind, kind)}",
                [
                    f"Angabe: {_short(detail) or 'keine'}",
                    "",
                    "Köderdaten kennt niemand, und HUBIplan zeigt sie keinem Verein. Wer sie",
                    "benutzt, hat sie an der Anwendung vorbei bekommen. Alle Auslösungen:",
                    "Plattform › Sicherheit. Weitere Mails dieser Art frühestens in einer Stunde.",
                ],
            )
    except Exception:  # noqa: BLE001 - ein Alarm darf nie einen Fehler 500 liefern
        logger.exception("Köder-Auslösung konnte nicht vermerkt werden")


def _record(kind: str, membership_id: int | None, detail: str) -> None:
    today = timezone.localdate()
    same = DecoyHit.objects.filter(kind=kind, membership_id=membership_id, detail=detail, day=today)
    if same.update(count=F("count") + 1, last_at=timezone.now()):
        return
    if DecoyHit.objects.count() >= MAX_ROWS:
        return
    try:
        with transaction.atomic():
            DecoyHit.objects.create(
                kind=kind, membership_id=membership_id, detail=detail, day=today
            )
    except IntegrityError:  # gleichzeitig angelegt
        same.update(count=F("count") + 1, last_at=timezone.now())


# --- Auslöser ---


def check_inbound(recipients: list[str], sender: str, subject: str) -> bool:
    """Eingegangene Mail (Sammelpostfach): True, wenn sie an einen Köder ging."""
    for address in recipients:
        found = decoy_for_address(address)
        if found is not None:
            hit(MAIL_IN, found, f"von {sender or 'unbekannt'}, Betreff: {subject}")
            return True
    return False


def check_outgoing(recipients: list[str], subject: str) -> bool:
    """Ausgehende Mail: True, wenn ein Empfänger ein Köder ist (dann nicht versenden)."""
    for address in recipients:
        found = decoy_for_address(address)
        if found is not None:
            hit(MAIL_OUT, found, f"Betreff: {subject}")
            return True
    return False


def _who(request) -> str:
    user = getattr(request, "user", None)
    name = getattr(user, "email", "") if getattr(user, "is_authenticated", False) else ""
    return f"{name or 'ohne Anmeldung'}, Adresse {ratelimit.client_ip(request) or 'unbekannt'}"


class DecoyMiddleware:
    """Stolperdrähte in Anfragen: Anmeldung mit Köderadresse, Abruf einer Köder-Nummer."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and AUTH_PATH.search(request.path):
            self._auth(request)
        return self.get_response(request)

    @staticmethod
    def _auth(request) -> None:
        try:
            if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_AUTH_BODY:
                return
            data = json.loads(request.body.decode("utf-8"))
            email = data.get("email") if isinstance(data, dict) else None
            if not isinstance(email, str):
                return
            found = decoy_for_address(email)
            if found is not None:
                hit(LOGIN, found, _who(request))
        except Exception:  # noqa: BLE001 - die Anmeldung selbst prüft ihre Eingaben
            return

    def process_view(self, request, view_func, view_args, view_kwargs):
        route = getattr(getattr(request, "resolver_match", None), "route", "") or ""
        found = MEMBER_ROUTE.search(route)
        if found is None or any(part in route for part in OTHER_NUMBERS):
            return None
        try:
            number = int(view_kwargs.get(found.group(1)))
            if number in current()["ids"]:
                path = _short(request.path, 120)
                hit(LOOKUP, number, f"{request.method} {path}, {_who(request)}")
        except Exception:  # noqa: BLE001 - nur ein Stolperdraht
            return None
        return None


# --- Anlegen und Löschen (Plattformverwaltung) ---


def _local(first: str, last: str) -> str:
    from circulars.inbound import plain_local

    return re.sub(r"[^a-z0-9.]", "", plain_local(f"{first}.{last}"))


def _free_address(first: str, last: str) -> str:
    """Adresse an der Verteiler-Domain, die kein Verteiler und kein Konto benutzt."""
    from django.contrib.auth import get_user_model

    from circulars import inbound

    domain = _domain()
    if not domain:
        return ""
    local = _local(first, last)
    for suffix in ("", *(str(secrets.randbelow(90) + 10) for _ in range(5))):
        address = f"{local}{suffix}@{domain}"
        taken = (
            inbound.lists_with(f"{local}{suffix}").exists()
            or get_user_model().objects.filter(email__iexact=address).exists()
            or decoy_for_address(address) is not None
        )
        if not taken:
            return address
    return ""


def _check_address(value: str) -> str:
    from django.contrib.auth import get_user_model

    address = (value or "").strip().lower()
    try:
        validate_email(address)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(
            {"email": gettext("Bitte eine gültige E-Mail-Adresse angeben.")}
        ) from exc
    if (
        get_user_model().objects.filter(email__iexact=address).exists()
        or address in [a.lower() for a in alarm.recipients()]
        or decoy_for_address(address) is not None
    ):
        raise serializers.ValidationError(
            {
                "email": gettext(
                    "Diese Adresse wird schon benutzt. Ein Köder braucht eine Adresse, an die "
                    "sonst niemand schreibt."
                )
            }
        )
    return address


@transaction.atomic
def create(email: str = "") -> int:
    """Legt einen Köder an und gibt seine Nummer zurück."""
    from members.models import (
        ContactDetails,
        Membership,
        MembershipPeriod,
        MemberType,
        MemberTypeAssignment,
        Person,
    )

    platform = Organization.platform()
    forget()
    with rls_bypass():
        if _memberships().count() >= MAX_DECOYS:
            raise serializers.ValidationError(
                {"detail": gettext("Mehr als fünf Köder sind nicht vorgesehen.")}
            )
        first, gender = secrets.choice(FIRST_NAMES)
        last = secrets.choice(LAST_NAMES)
        address = _check_address(email) if email.strip() else _free_address(first, last)
        if not address:
            raise serializers.ValidationError(
                {
                    "email": gettext(
                        "Ohne Verteiler-Domain bitte eine eigene Adresse angeben, deren "
                        "Postfach du liest."
                    )
                }
            )
        today = timezone.localdate()
        entry = today - datetime.timedelta(days=400 + secrets.randbelow(4000))
        birth = datetime.date(1950 + secrets.randbelow(45), 1 + secrets.randbelow(12), 1)
        birth += datetime.timedelta(days=secrets.randbelow(27))
        person = Person.objects.create(
            scope=platform, last_name=last, first_name=first, birth_date=birth, gender=gender
        )
        postal_code, city = secrets.choice(PLACES)
        ContactDetails.objects.create(
            scope=platform,
            person=person,
            organization=None,
            email=address,
            street=f"{secrets.choice(STREETS)} {1 + secrets.randbelow(60)}",
            postal_code=postal_code,
            city=city,
        )
        member_type, _ = MemberType.objects.get_or_create(organization=platform, name="Mitglied")
        membership = Membership.objects.create(
            organization=platform,
            scope=platform,
            person=person,
            club_number=str(100 + secrets.randbelow(900)),
        )
        MembershipPeriod.objects.create(
            organization=platform, membership=membership, entry_date=entry
        )
        MemberTypeAssignment.objects.create(
            organization=platform, membership=membership, member_type=member_type, valid_from=entry
        )
    forget()
    # nach dem Festschreiben noch einmal: Eine Anfrage dazwischen hätte den alten Stand gemerkt
    transaction.on_commit(forget)
    return membership.pk


@transaction.atomic
def delete(pk: int) -> None:
    from members.models import ContactDetails

    with rls_bypass():
        membership = _memberships().filter(pk=pk).first()
        if membership is None:
            return
        person = membership.person
        membership.delete()
        if not person.memberships.exists():
            ContactDetails.objects.filter(person=person).delete()
            person.delete()
    forget()
    transaction.on_commit(forget)


def state() -> dict:
    with rls_bypass():
        decoys = []
        names = {}
        for membership in _memberships():
            person = membership.person
            contact = person.contacts.order_by("pk").first()
            name = f"{person.first_name} {person.last_name}".strip()
            names[membership.pk] = name
            decoys.append(
                {
                    "id": membership.pk,
                    "name": name,
                    "email": contact.email if contact else "",
                    "place": f"{contact.postal_code} {contact.city}" if contact else "",
                    "created": membership.created_at.date().isoformat(),
                }
            )
        hits = [
            {
                "id": h.pk,
                "kind": h.kind,
                "decoy": names.get(h.membership_id, ""),
                "detail": h.detail,
                "count": h.count,
                "last_at": h.last_at.isoformat(),
            }
            for h in DecoyHit.objects.order_by("-last_at", "-id")[:SHOWN]
        ]
        return {"decoys": decoys, "limit": MAX_DECOYS, "domain": _domain(), "hits": hits}


def _domain() -> str:
    """Verteiler-Domain, deren Sammelpostfach HUBIplan abholt (ohne die Simulation)."""
    from django.conf import settings

    found = list(settings.INBOUND_DOMAINS)
    return found[0] if found else ""


class _CreateSerializer(serializers.Serializer):
    email = serializers.CharField(required=False, allow_blank=True, max_length=254)


@extend_schema(request=_CreateSerializer, responses=dict)
class PlatformDecoysView(APIView):
    """GET: Köder und Auslösungen. POST: Köder anlegen."""

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response(state())

    def post(self, request):
        data = _CreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        create(data.validated_data.get("email", ""))
        return Response(state(), status=201)


@extend_schema(request=None, responses=dict)
class PlatformDecoyView(APIView):
    """DELETE: einen Köder entfernen."""

    permission_classes = [IsPlatformAdmin]

    def delete(self, request, pk: int):
        delete(pk)
        return Response(state())


@extend_schema(request=None, responses=dict)
class PlatformDecoyHitsView(APIView):
    """DELETE: alle Auslösungen entfernen (geklärt)."""

    permission_classes = [IsPlatformAdmin]

    def delete(self, request):
        with rls_bypass():
            DecoyHit.objects.all().delete()
        return Response(state())
