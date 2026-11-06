"""Erscheinungsbild je Adresse (White Label W7, konzepte/white-label.md Abschnitt 11).

Eine Instanz kann unter mehreren Adressen laufen. Ist eine Adresse einer Einheit
zugeordnet, zeigen Anmeldeseite, Browser-Tab und Handy-Symbol Name, Farben, Wappen und
Symbol dieser Einheit (mit Vererbung nach oben). Unbekannte Adressen zeigen die Instanz.
Der Host-Header wird nur gegen die Liste ausgewertet, nie in Links übernommen.
"""

from __future__ import annotations

import re

from django.utils.translation import gettext
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .models import InstanceAddress, Organization

HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}$")


def normalize_host(host: str) -> str:
    """Hostname ohne Port, klein, ohne Punkt am Ende."""
    host = (host or "").strip().lower()
    if host.startswith("["):  # IPv6 mit Port
        return host
    return host.split(":", 1)[0].rstrip(".")


def clean_hostname(value: str) -> str:
    from django.core.exceptions import ValidationError

    host = normalize_host(value)
    if not HOSTNAME.match(host):
        raise ValidationError(gettext("Bitte eine Adresse wie mitglieder.example.org angeben."))
    return host


def unit_for_host(host: str) -> Organization | None:
    """Einheit, der die aufgerufene Adresse gehört (nur aktive Einheiten)."""
    host = normalize_host(host)
    if not host:
        return None
    address = InstanceAddress.objects.select_related("organization").filter(hostname=host).first()
    if address is None or not address.organization.is_active:
        return None
    return address.organization


def request_unit(request) -> Organization | None:
    try:
        host = request.get_host()
    except Exception:  # noqa: BLE001 – unerlaubter Host: wie unbekannt behandeln
        return None
    return unit_for_host(host)


def _scheme() -> str:
    from urllib.parse import urlsplit

    from django.conf import settings

    return urlsplit(settings.FRONTEND_URL).scheme or "https"


def base_url(unit: Organization | None = None, request=None) -> str:
    """Basisadresse für Links (ohne Schrägstrich am Ende, W7b).

    Mit Anfrage: deren Adresse, wenn sie eingetragen ist. Mit Einheit: Adresse der Einheit oder
    der nächsthöheren Einheit mit eigener Adresse. Sonst die Hauptadresse der Instanz.
    """
    from django.conf import settings

    main = settings.FRONTEND_URL.rstrip("/")
    if request is not None:
        found = request_unit(request)
        if found is not None:
            return f"{_scheme()}://{normalize_host(request.get_host())}"
    if unit is None:
        return main
    chain = [o for o in unit.ancestors() if o.type != Organization.Type.PLATFORM and o.is_active]
    if not chain:
        return main
    hosts: dict[int, str] = {}
    for org_id, host in (
        InstanceAddress.objects.filter(organization__in=chain)
        .order_by("hostname")
        .values_list("organization_id", "hostname")
    ):
        hosts.setdefault(org_id, host)
    for org in chain:
        if org.pk in hosts:
            return f"{_scheme()}://{hosts[org.pk]}"
    return main


def rebase(url: str, base: str) -> str:
    """Link auf die Hauptadresse auf eine andere Basisadresse umschreiben."""
    from django.conf import settings

    main = settings.FRONTEND_URL.rstrip("/")
    if url and base != main and (url == main or url.startswith(main + "/")):
        return base + url[len(main) :]
    return url


# --- Erlaubte Hosts und Zertifikate aus der Liste (W7c) ---

HOSTS_CACHE_KEY = "hubiplan:adressen"
HOSTS_CACHE_SECONDS = 60
TLS_ASK_PATH = "/api/intern/tls/"


def listed_hosts() -> frozenset[str]:
    """Eingetragene Adressen aktiver Einheiten (eine Minute zwischengespeichert)."""
    from django.core.cache import cache

    hosts = cache.get(HOSTS_CACHE_KEY)
    if hosts is None:
        hosts = list(
            InstanceAddress.objects.filter(organization__is_active=True).values_list(
                "hostname", flat=True
            )
        )
        cache.set(HOSTS_CACHE_KEY, hosts, HOSTS_CACHE_SECONDS)
    return frozenset(hosts)


def forget_hosts() -> None:
    from django.core.cache import cache

    cache.delete(HOSTS_CACHE_KEY)


def host_allowed(host: str) -> bool:
    from django.conf import settings
    from django.http.request import split_domain_port, validate_host

    domain, _port = split_domain_port(host or "")
    if not domain:
        return False
    if validate_host(domain, settings.FIXED_ALLOWED_HOSTS):
        return True
    return normalize_host(domain) in listed_hosts()


class HostMiddleware:
    """Mit HUBIPLAN_ADRESSEN_AUS_LISTE: nur feste und eingetragene Adressen zulassen.

    Django lässt dann jeden Host durch (ALLOWED_HOSTS = ["*"]); diese Prüfung ersetzt seine.
    Ausnahme ist nur die Zertifikatsabfrage von Caddy, die das Backend direkt anspricht.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        if getattr(settings, "ADDRESSES_FROM_LIST", False) and request.path != TLS_ASK_PATH:
            # Wie Django: Host ungeprüft lesen (X-Forwarded-Host nur, wenn eingeschaltet)
            if not host_allowed(request._get_raw_host()):
                from django.http import HttpResponseBadRequest

                return HttpResponseBadRequest("Unbekannte Adresse.")
        return self.get_response(request)


class TlsAskView(APIView):
    """Caddy fragt vor einem Zertifikat nach (on_demand_tls ask): 200 nur für eingetragene
    Adressen. Von außen gesperrt (deploy/caddy/site.caddy)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        parameters=[OpenApiParameter("domain", str, description="Angefragter Hostname")],
        responses={(200, "text/plain"): str, 404: None},
    )
    def get(self, request):
        from django.conf import settings
        from django.http import HttpResponse, HttpResponseNotFound

        domain = normalize_host(request.GET.get("domain", ""))
        if not getattr(settings, "ADDRESSES_FROM_LIST", False) or domain not in listed_hosts():
            return HttpResponseNotFound()
        return HttpResponse("ok", content_type="text/plain")
