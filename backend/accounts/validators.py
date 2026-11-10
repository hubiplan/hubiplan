"""Zusätzliche Passwortregeln (Audit 29.10. G08).

- Naheliegende Wörter: HUBIplan, Schützen, Verein und Name, Kurzname und Ort der
  Organisationen, in denen der Benutzer eine Rolle oder einen Zugang hat. Ein
  Passwort, das nach Abzug dieser Wörter, Ziffern und Satzzeichen kaum noch etwas
  enthält, wird abgelehnt.
- Häufige und geleakte Passwörter prüft Djangos eigener CommonPasswordValidator (Liste
  aus Django, BSD-Lizenz). Die frühere NCSC-Liste ist entfernt, weil die Rechte an der
  ursprünglichen Sammlung nicht belegt sind (Lizenzaudit 10.11.2026, L05).
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

FIXED_WORDS = (
    "hubiplan",
    "schuetzen",
    "schützen",
    "schuetze",
    "schütze",
    "verein",
    "bruderschaft",
    "passwort",
    "kennwort",
)
MIN_REST = 6


def _plain(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return text


def _org_words(user) -> set[str]:
    if user is None or not getattr(user, "pk", None):
        return set()
    from access.models import RoleAssignment
    from core.tenancy import rls_bypass
    from portal.models import PortalAccess

    with rls_bypass():
        orgs = [a.organization for a in RoleAssignment.objects.filter(user=user)]
        orgs += [
            a.membership.organization
            for a in PortalAccess.objects.filter(user=user).select_related(
                "membership__organization"
            )
        ]
    words: set[str] = set()
    for org in orgs:
        for value in (org.name, org.short_name, org.city):
            # Einzelne Bestandteile, z. B. „Hubertus“ und „Grimlinghausen“
            words.update(w for w in re.split(r"[\W_]+", _plain(value or "")) if len(w) >= 4)
    return words


class ContextWordValidator:
    """Passwort darf nicht nur aus naheliegenden Wörtern und Ziffern bestehen."""

    def validate(self, password: str, user=None) -> None:
        plain = _plain(password)
        rest = plain
        words = {_plain(w) for w in FIXED_WORDS} | _org_words(user)
        for word in sorted(words, key=len, reverse=True):
            rest = rest.replace(word, "")
        # Nur wenn ein naheliegendes Wort drinsteckt; zufällige Passwörter mit wenigen
        # Buchstaben bleiben erlaubt
        if rest == plain:
            return
        rest = re.sub(r"[\W\d_]+", "", rest)
        if len(rest) < MIN_REST:
            raise ValidationError(
                gettext(
                    "Das Passwort ist zu leicht zu erraten: Es besteht fast nur aus "
                    "naheliegenden Wörtern (z. B. Vereinsname, Ort, „Schützen“) und Ziffern."
                ),
                code="password_context",
            )

    def get_help_text(self) -> str:
        return "Das Passwort darf nicht nur aus Vereinsname, Ort oder ähnlichen Wörtern bestehen."
