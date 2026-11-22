"""Bereiche (Scopes) der API für andere Programme (docs/api.md).

Ein API-Zugang bekommt nur die einzeln angekreuzten Bereiche. Jeder Bereich hängt an einem
Modul der Einheit: Ist das Modul aus, gibt es den Bereich nicht. Bereiche mit ``personal``
geben Personendaten heraus: Es gibt sie nur für Vereine und nur mit einem Empfänger aus den
Geschäftspartnern und bestätigter Rechtsgrundlage am Zugang.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext, gettext_noop


@dataclass(frozen=True)
class Scope:
    code: str
    label: str
    description: str
    # Modul, das eingeschaltet sein muss ("" = keines)
    module: str = ""
    # Auch für einen Zugang, der auf eine Untereinheit begrenzt ist
    unit_ok: bool = False
    # Setzt diesen Bereich voraus
    needs: str = ""
    # Arten von Einheiten (Organization.type), für die es den Bereich gibt
    org_types: tuple[str, ...] = ("federation", "club")
    # Gibt Personendaten heraus: nur mit Empfänger und bestätigter Rechtsgrundlage
    personal: bool = False


UNIT_READ = "einheit.lesen"
EVENTS_READ = "termine.lesen"
EVENTS_MEMBERS = "termine.mitglieder"
STATISTICS_READ = "statistik.lesen"
BOARD_READ = "vorstand.lesen"
RESULTS_READ = "ergebnisse.lesen"
NEWS_READ = "neuigkeiten.lesen"
DOCUMENTS_READ = "dokumente.lesen"
REPORT_READ = "verbandsmeldung.lesen"
MEMBERS_READ = "mitglieder.lesen"
HONORS_READ = "ehrungen.lesen"
QUALIFICATIONS_READ = "qualifikationen.lesen"

SCOPES: tuple[Scope, ...] = (
    Scope(
        UNIT_READ,
        gettext_noop("Einheit lesen"),
        gettext_noop("Name, Anschrift, Kontakt, Logo und die Untereinheiten als Baum"),
        unit_ok=True,
    ),
    Scope(
        EVENTS_READ,
        gettext_noop("Öffentliche Termine lesen"),
        gettext_noop(
            "Termine mit der Sichtbarkeit „nach außen öffentlich“, nie Zu- und Absagen "
            "oder Teilnehmende"
        ),
        module="events",
        unit_ok=True,
    ),
    Scope(
        EVENTS_MEMBERS,
        gettext_noop("Auch Termine für Mitglieder lesen"),
        gettext_noop(
            "Zusätzlich Termine mit der Sichtbarkeit „Mitglieder“; Termine „nur Vorstand“ nie"
        ),
        module="events",
        unit_ok=True,
        needs=EVENTS_READ,
    ),
    Scope(
        STATISTICS_READ,
        gettext_noop("Mitgliederzahlen lesen"),
        gettext_noop(
            "Stichtagsstatistik: Anzahlen nach Alter, Geschlecht und Untereinheit, keine Personen"
        ),
        module="members",
        unit_ok=True,
    ),
    Scope(
        BOARD_READ,
        gettext_noop("Vorstand und Ämter lesen"),
        gettext_noop(
            "Rollen mit „auf der Webseite zeigen“ und ihre Funktionsadresse; Namen nur, wenn "
            "sie auf der öffentlichen Webseite stehen"
        ),
    ),
    Scope(
        RESULTS_READ,
        gettext_noop("Wettbewerbsergebnisse lesen"),
        gettext_noop("Auf der Webseite veröffentlichte Wettbewerbe mit ihren Ranglisten"),
        module="competitions",
    ),
    Scope(
        NEWS_READ,
        gettext_noop("Beiträge lesen"),
        gettext_noop("Auf der Webseite gezeigte Beiträge aus den eigenen Kanälen"),
        module="social",
    ),
    Scope(
        DOCUMENTS_READ,
        gettext_noop("Öffentliche Dokumente lesen"),
        gettext_noop("Auf der Webseite veröffentlichte Dokumente und Presseberichte"),
        module="website",
    ),
    Scope(
        REPORT_READ,
        gettext_noop("Verbandsmeldung lesen"),
        gettext_noop(
            "Gemeldete Mitglieder zum Stichtag: Zahlen nach aktiv, passiv und Geburtsmonat; "
            "namentlich nur, wenn am Zugang so gewählt"
        ),
        module="members",
        org_types=("club",),
    ),
    Scope(
        MEMBERS_READ,
        gettext_noop("Mitglieder lesen"),
        gettext_noop(
            "Name, Geburtsdatum und Mitgliedsnummer, dazu nur die am Zugang gewählten "
            "Feldgruppen; nie Bankdaten, Bemerkungen, Fotos oder Zusatzfelder"
        ),
        module="members",
        unit_ok=True,
        org_types=("club",),
        personal=True,
    ),
    Scope(
        HONORS_READ,
        gettext_noop("Ehrungen lesen"),
        gettext_noop("Verliehene Ehrungen mit Name der Person und Zeitraum"),
        module="awards",
        unit_ok=True,
        org_types=("club",),
        personal=True,
    ),
    Scope(
        QUALIFICATIONS_READ,
        gettext_noop("Qualifikationen lesen"),
        gettext_noop(
            "Nachweise mit Name der Person, Erwerb und Gültigkeit; nie Bemerkungen und nie "
            "Nachweise, die nur eingesehen werden"
        ),
        module="qualifications",
        unit_ok=True,
        org_types=("club",),
        personal=True,
    ),
)

SCOPE_BY_CODE: dict[str, Scope] = {s.code: s for s in SCOPES}


def available(org, unit=None) -> list[Scope]:
    """Bereiche, die diese Einheit (bzw. ein auf ``unit`` begrenzter Zugang) vergeben kann."""
    from access.modules import module_on

    out = []
    for scope in SCOPES:
        if org.type not in scope.org_types:
            continue
        if unit is not None and not scope.unit_ok:
            continue
        if scope.module and not module_on(org, scope.module):
            continue
        out.append(scope)
    return out


def clean(codes, org, unit=None) -> list[str]:
    """Gültige Auswahl in fester Reihenfolge; Vorausgesetztes kommt mit."""
    allowed = {s.code: s for s in available(org, unit)}
    chosen = {c for c in codes if c in allowed}
    for code in list(chosen):
        needs = allowed[code].needs
        if needs and needs in allowed:
            chosen.add(needs)
    return [s.code for s in SCOPES if s.code in chosen]


def personal(codes, report_level: str = "a") -> bool:
    """Gibt diese Auswahl Personendaten heraus? Die Verbandsmeldung nur namentlich."""
    chosen = set(codes or [])
    if REPORT_READ in chosen and report_level == "b":
        return True
    return any(SCOPE_BY_CODE[c].personal for c in chosen if c in SCOPE_BY_CODE)


def describe(codes) -> list[dict]:
    return [
        {
            "scope": s.code,
            "label": gettext(s.label),
            "description": gettext(s.description),
        }
        for s in SCOPES
        if s.code in set(codes)
    ]
