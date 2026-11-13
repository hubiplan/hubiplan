"""Firmen im Mitgliederbereich (Konzept Familien, Haushalte und Firmen, H5).

Zahlt ein Organisationsmitglied (Firma) für Mitarbeiter, sehen ihre Ansprechpartner mit
Zugang im Mitgliederbereich nur die Liste der Personen, für die sie zahlt: Name, seit
wann, ob der Beitrag über die Firma läuft (Fachfrage FH-12). Keine Anschrift, kein
Geburtsdatum, keine Termine oder Ämter.

- Melden (FH-14): Name und Mail eines Mitarbeiters. Er bekommt den Link zum Online-Antrag
  mit Vermerk „Beitrag zahlt …“, ergänzt seine Daten und bestätigt selbst. Bei Annahme
  kommt er mit „Beitrag über die Firma“ zur Firma.
- Abmelden (FH-13): Die Firma zahlt ab einem Datum nicht mehr. Das ist kein Austritt: Die
  Zugehörigkeit zur Firma endet, das Mitglied zahlt danach selbst. Verein und Mitglied
  bekommen eine Mail.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from core.i18n import date_text, language_of_org
from core.names import clean_person_name
from core.ratelimit import too_many
from core.tenancy import tenant_context
from members.households import end_member
from members.models import Household, HouseholdMember, today
from organizations.addresses import base_url
from outbox import mail

from .models import HouseholdPayer

SALT = "hubiplan.firma-meldet"
INVITE_DAYS = 30


def company_households(access):
    """Firmen, für die die Organisation dieses Zugangs zahlt (nur Ansprechpartner)."""
    if access.contact_person_id is None:
        return Household.objects.none()
    ids = HouseholdPayer.objects.filter(
        organization=access.organization,
        membership_id=access.membership_id,
        kind=HouseholdPayer.Kind.ORGANIZATION,
    ).values_list("household_id", flat=True)
    return Household.objects.filter(
        organization=access.organization, kind=Household.Kind.COMPANY, pk__in=list(ids)
    )


def has_company(access) -> bool:
    if "billing" not in (access.organization.enabled_modules or []):
        return False
    return company_households(access).exists()


# Grenzen für „Mitarbeiter melden“ (Gesamtaudit 13.11. S-01, Fachfrage 7): je Tag
REPORTS_PER_COMPANY = 20
REPORTS_PER_CLUB = 100
DAY = 24 * 60 * 60
TOKEN_MAX = 1500


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"hubiplan-firma-meldet:" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def invite_token(
    household: Household, email: str, first_name: str = "", last_name: str = ""
) -> str:
    """Link der Meldung: verschlüsselt, damit Name und Mailadresse der gemeldeten Person
    nicht lesbar in Adressen und damit in Zugriffsprotokollen stehen (Gesamtaudit 13.11.
    S-01). Das Formular füllt die Angaben aus dem Token vor (``read_invite``)."""
    payload = {
        "o": household.organization_id,
        "h": household.pk,
        "e": email.strip().lower(),
        "v": first_name,
        "n": last_name,
    }
    return _fernet().encrypt(json.dumps(payload).encode()).decode()


def _payload(token: str) -> dict | None:
    if not token or len(token) > TOKEN_MAX:
        return None
    max_age = INVITE_DAYS * DAY
    try:
        data = json.loads(_fernet().decrypt(token.encode(), ttl=max_age))
    except (InvalidToken, ValueError):
        # Links aus der Zeit vor der Verschlüsselung gelten bis zu ihrem Ablauf weiter
        try:
            data = signing.loads(token, salt=SALT, max_age=max_age)
        except signing.BadSignature:
            return None
    return data if isinstance(data, dict) else None


def read_invite(org, token: str) -> tuple[Household, dict] | None:
    """Firma und gemeldete Person aus dem Link; ungültig oder abgelaufen: None."""
    data = _payload(token)
    if data is None or data.get("o") != org.pk:
        return None
    household = Household.objects.filter(
        organization=org, pk=data.get("h"), kind=Household.Kind.COMPANY
    ).first()
    if household is None:
        return None
    return household, {
        "email": str(data.get("e") or ""),
        "first_name": str(data.get("v") or ""),
        "last_name": str(data.get("n") or ""),
    }


def read_token(org, token: str) -> Household | None:
    """Firma aus dem Link der Meldung; ungültig oder abgelaufen: keine."""
    invite = read_invite(org, token)
    return invite[0] if invite else None


def _access(request, access_id: int):
    from portal.views import _portal_access

    access = _portal_access(request.user, access_id)
    if not has_company(access):
        raise NotFound()
    return access


def _rows(household: Household) -> list[dict]:
    on = today()
    rows = []
    for link in household.members.select_related("membership__person"):
        if link.valid_until is not None and link.valid_until < on - datetime.timedelta(days=365):
            continue
        person = link.membership.person
        rows.append(
            {
                "link": link.pk,
                "name": f"{person.first_name} {person.last_name}".strip(),
                "since": link.valid_from,
                "until": link.valid_until,
                "pays_via": link.pays_via,
            }
        )
    rows.sort(key=lambda r: (r["until"] is not None, r["name"].lower()))
    return rows


class EmployeeReport(serializers.Serializer):
    first_name = serializers.CharField(max_length=60)
    last_name = serializers.CharField(max_length=60)
    email = serializers.EmailField(max_length=200)

    def _name(self, value: str) -> str:
        # Namen gehen in eine Mail an eine fremde Adresse: nur, was in Namen vorkommt
        name = clean_person_name(value)
        if name is None:
            raise serializers.ValidationError(
                gettext("Bitte nur Buchstaben, Leerzeichen, Bindestrich, Punkt und Apostroph.")
            )
        return name

    def validate_first_name(self, value: str) -> str:
        return self._name(value)

    def validate_last_name(self, value: str) -> str:
        return self._name(value)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class EmployeeEnd(serializers.Serializer):
    valid_until = serializers.DateField()


@extend_schema(responses={200: OpenApiTypes.OBJECT})
class CompanyView(APIView):
    """Firmen, für die die eigene Organisation zahlt, mit ihren Mitarbeitern."""

    def get(self, request, access_id: int):
        access = _access(request, access_id)
        club = access.organization
        with tenant_context(club.pk, request.user.pk):
            from admission.models import ApplicationForm

            form = ApplicationForm.objects.filter(organization=club).first()
            return Response(
                {
                    "can_report": bool(form and form.enabled),
                    "companies": [
                        {"id": h.pk, "name": h.name, "members": _rows(h)}
                        for h in company_households(access).order_by("pk")
                    ],
                }
            )


class CompanyReportView(APIView):
    """Neuen Mitarbeiter melden: Mail mit Link zum Online-Antrag."""

    @extend_schema(request=EmployeeReport, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, access_id: int, pk: int):
        access = _access(request, access_id)
        club = access.organization
        ser = EmployeeReport(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        with tenant_context(club.pk, request.user.pk):
            from admission.models import ApplicationForm

            household = get_object_or_404(company_households(access), pk=pk)
            form = ApplicationForm.objects.filter(organization=club).first()
            if form is None or not form.enabled:
                raise serializers.ValidationError(
                    {
                        "detail": gettext(
                            "Der Verein hat keinen Online-Antrag eingeschaltet. Bitte meldet "
                            "Mitarbeiter direkt beim Verein."
                        )
                    }
                )
            # Mengengrenzen: Sonst ließe sich über die Meldung im Namen des Vereins beliebig
            # viel Post an fremde Adressen schicken (Gesamtaudit 13.11. S-01)
            address = hashlib.sha256(v["email"].encode()).hexdigest()[:32]
            if too_many(f"firma-meldung:mail:{club.pk}:{address}", 1, DAY):
                raise serializers.ValidationError(
                    {
                        "email": gettext(
                            "An diese Adresse ging heute schon eine Meldung. Bitte morgen erneut."
                        )
                    }
                )
            if too_many(
                f"firma-meldung:firma:{household.pk}", REPORTS_PER_COMPANY, DAY
            ) or too_many(f"firma-meldung:verein:{club.pk}", REPORTS_PER_CLUB, DAY):
                raise serializers.ValidationError(
                    {
                        "detail": gettext(
                            "Heute wurden schon sehr viele Mitarbeiter gemeldet. Bitte morgen "
                            "erneut oder direkt beim Verein melden."
                        )
                    }
                )
            token = invite_token(household, v["email"], v["first_name"], v["last_name"])
            from urllib.parse import quote

            url = f"{base_url(club)}/mitglied-werden/{form.public_key}?firma={quote(token)}"
            with language_of_org(club):
                subject = gettext("Mitgliedsantrag bei {club}").format(club=club.name)
                body = gettext(
                    "Guten Tag {first_name} {last_name},\n\n"
                    "{company} hat Sie bei {club} als Mitglied angemeldet und zahlt Ihren "
                    "Mitgliedsbeitrag. Bitte ergänzen Sie Ihre Angaben im Online-Antrag und "
                    "bestätigen Sie ihn per Mail:\n\n{url}\n\n"
                    "Der Link gilt {days} Tage. Möchten Sie nicht Mitglied werden, müssen Sie "
                    "nichts tun.\n\nViele Grüße\n{club}\n"
                ).format(
                    first_name=v["first_name"],
                    last_name=v["last_name"],
                    company=household.name,
                    club=club.name,
                    url=url,
                    days=INVITE_DAYS,
                )
            mail.send(v["email"], subject, body, organization=club, kind="company_report")
            record(
                club,
                request.user,
                "update",
                household,
                {"Mitarbeiter gemeldet": [None, f"{v['first_name']} {v['last_name']}"]},
            )
        return Response({"status": "sent"}, status=status.HTTP_201_CREATED)


class CompanyEndView(APIView):
    """Firma zahlt ab einem Datum nicht mehr für einen Mitarbeiter (kein Austritt)."""

    @extend_schema(request=EmployeeEnd, responses={200: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, access_id: int, pk: int, link_id: int):
        access = _access(request, access_id)
        club = access.organization
        ser = EmployeeEnd(data=request.data)
        ser.is_valid(raise_exception=True)
        until = ser.validated_data["valid_until"]
        if until < today():
            raise serializers.ValidationError(
                {"valid_until": gettext("Das Datum liegt in der Vergangenheit.")}
            )
        with tenant_context(club.pk, request.user.pk):
            household = get_object_or_404(company_households(access), pk=pk)
            link = get_object_or_404(
                HouseholdMember.objects.select_related("membership__person"),
                household=household,
                pk=link_id,
                valid_until__isnull=True,
            )
            before = snapshot(link)
            end_member(link, until)
            record(
                club,
                request.user,
                "update",
                link,
                diff(before, snapshot(link)),
                person=link.membership.person,
            )
            transaction.on_commit(lambda: _notify_end(club, household, link, until))
            return Response({"members": _rows(household)})


def _notify_end(club, household, link, until) -> None:
    """Hinweis an Verein und Mitglied: ab dem Folgetag zahlt das Mitglied selbst."""
    from members.services import contact_for

    person = link.membership.person
    with tenant_context(club.pk), language_of_org(club):
        name = f"{person.first_name} {person.last_name}".strip()
        subject = gettext("{company} zahlt nicht mehr für {name}").format(
            company=household.name, name=name
        )
        body = gettext(
            "{company} zahlt den Mitgliedsbeitrag für {name} nur noch bis {day}. Die "
            "Mitgliedschaft bleibt bestehen; danach zahlt das Mitglied selbst.\n"
        ).format(company=household.name, name=name, day=date_text(until))
        to_member = (
            body
            + "\n"
            + gettext(
                "Bitte erteilen Sie dem Verein ein Lastschriftmandat oder überweisen Sie den "
                "Beitrag künftig selbst.\n"
            )
        )
        if club.contact_email:
            mail.send(club.contact_email, subject, body, organization=club, fail_silently=True)
        contact = contact_for(person, club)
        if contact and contact.email:
            mail.send(contact.email, subject, to_member, organization=club, fail_silently=True)
