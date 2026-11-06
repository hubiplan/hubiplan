"""Erscheinungsbild je Adresse (White Label W7, konzepte/white-label.md Abschnitt 11).

Eine Instanz kann unter mehreren Adressen laufen. Ist eine Adresse einer Einheit
zugeordnet, zeigen Anmeldeseite, Browser-Tab und Handy-Symbol Name, Farben, Wappen und
Symbol dieser Einheit (mit Vererbung nach oben). Unbekannte Adressen zeigen die Instanz.
Der Host-Header wird nur gegen die Liste ausgewertet, nie in Links übernommen.
"""

from __future__ import annotations

import re

from django.utils.translation import gettext

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
