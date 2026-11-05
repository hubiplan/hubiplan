"""Inhalt der Wallet-Pässe: Felder, Farben, Logo und Texte in Deutsch und Englisch.

Apple und Google zeigen dieselben Angaben. Sie sind bewusst sparsamer als die Prüfseite:
kein Foto, keine Mitgliedsnummer, kein Datum. Gültig ist nur, was die Prüfseite nach dem
Scan zeigt; der Pass ist Anzeige.

Die Wallet wählt die Sprache nach dem Gerät. Deshalb erzeugt HUBIplan jeden festen Text in
beiden Sprachen (deutscher Text als Schlüssel, Englisch aus ``locale/en``). Namen, die die
Einheit selbst vergibt (Verein, Abteilungen, Mitgliedsarten), bleiben, wie sie sind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_noop

from core.tenancy import rls_bypass
from organizations.terms import english_label
from organizations.theme import effective_theme

from .services import current_departments

LANGUAGES = ("de", "en")

# Feste Texte des Passes (deutscher Text = Schlüssel des Übersetzungskatalogs)
TEXTS = {
    "description": gettext_noop("Mitgliedsausweis"),
    "member": gettext_noop("Mitglied"),
    "club": gettext_noop("Verein"),
    "member_type": gettext_noop("Mitgliedsart"),
    "federation": gettext_noop("Dachverband"),
    "verify": gettext_noop("Gültigkeit prüfen"),
    "verify_body": gettext_noop(
        "Bitte den QR-Code scannen. Die aktuelle Gültigkeit wird online geprüft."
    ),
    "verify_body_static": gettext_noop(
        "Bitte den QR-Code scannen. Die aktuelle Gültigkeit wird online geprüft. "
        "Dieser Pass wird nicht automatisch aktualisiert."
    ),
    "verify_page": gettext_noop("Prüfseite"),
    "invalid": gettext_noop("Ungültiger Ausweis"),
}


def texts(key: str) -> dict[str, str]:
    """Fester Text in allen Sprachen, z. B. ``{"de": "Mitglied", "en": "Member"}``."""
    result = {}
    for language in LANGUAGES:
        with translation.override(language):
            result[language] = gettext(TEXTS[key])
    return result


@dataclass
class PassContent:
    name: str
    club: str
    url: str
    member_type: str = ""
    federation: str = ""
    departments: list[str] = field(default_factory=list)
    # Bezeichnung der Abteilungen je Sprache, z. B. {"de": "Zug", "en": "Platoon"}
    department_label: dict[str, str] = field(default_factory=dict)
    # Farben als #rrggbb
    background: str = "#19375a"
    foreground: str = "#ffffff"
    logo: object = None  # ImageFieldFile der Einheit (oder darüber), sonst None
    logo_url: str = ""  # absolute https-Adresse des Logos, sonst leer


def _hex(color: str, fallback: str) -> str:
    color = (color or "").strip().lower()
    if len(color) == 7 and color.startswith("#"):
        try:
            int(color[1:], 16)
            return color
        except ValueError:
            pass
    return fallback


def rgb(color: str) -> str:
    """#rrggbb → „rgb(r, g, b)“ (Apple-Schreibweise)."""
    return "rgb({}, {}, {})".format(*(int(color[i : i + 2], 16) for i in (1, 3, 5)))


def _absolute(url: str) -> str:
    if not url:
        return ""
    absolute = urljoin(settings.FRONTEND_URL.rstrip("/") + "/", url)
    # Google lädt Bilder nur über https; Testinstanzen ohne https bekommen kein Logo
    return absolute if absolute.startswith("https://") else ""


def build(card) -> PassContent:
    """Angaben für den Pass; ruft nur, wer den Ausweis ohnehin sehen darf."""
    membership = card.membership
    club = card.organization
    person = membership.person
    on = timezone.localdate()
    with rls_bypass():
        current = membership.current_period(on)
        assignment = membership.current_type(on) if current else None
        departments = current_departments([membership.pk]).get(membership.pk, []) if current else []
    chain = club.ancestors()
    theme = effective_theme(chain)
    logo = next((item.logo for item in chain if getattr(item, "logo", None)), None)
    federation = club.parent if club.parent and club.parent.type == "federation" else None
    plural = len(departments) > 1
    en, en_plural = english_label(
        club.department_label,
        club.department_label_plural,
        club.department_label_en,
        club.department_label_plural_en,
    )
    return PassContent(
        name=f"{person.first_name} {person.last_name}".strip(),
        club=club.name,
        url=card.url,
        member_type=assignment.member_type.name if assignment else "",
        federation=federation.name if federation else "",
        departments=departments,
        department_label={
            "de": club.department_label_plural if plural else club.department_label,
            "en": en_plural if plural else en,
        },
        background=_hex(theme["primary"], "#19375a"),
        foreground=_hex(theme["on_primary"], "#ffffff"),
        logo=logo,
        logo_url=_absolute(theme["logo_url"] or ""),
    )
