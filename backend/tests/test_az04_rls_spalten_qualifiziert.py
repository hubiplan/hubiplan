"""Wächter: Unterabfragen über Einheiten in Zeilenschutzregeln binden Spalten eindeutig
(Gesamtaudit 15.11., AZ-04).

Die Regel für ``events_event`` (core 0020/0022) prüfte die Weitergabe nach oben mit
``SELECT 1 FROM organizations_organization o WHERE o.id = organization_id``. Seit
organizations 0014 hat die Einheit selbst eine Spalte ``organization_id``. PostgreSQL bindet
den unbenannten Namen an die innerste Tabelle, die Bedingung wurde ``o.id = o.organization_id``
und traf nie zu.

Der Wächter liest alle Regeln aus ``pg_policies`` (USING und WITH CHECK). PostgreSQL gibt
Spalten in Unterabfragen mit der Tabelle aus, an die sie gebunden sind: ``o.organization_id``
für die Einheit, ``events_event.organization_id`` für die Tabelle der Regel. Je Unterabfrage
über ``organizations_organization`` meldet er

- einen Vergleich zweier verschiedener Spalten derselben Einheit, von denen mindestens eine
  auch in der Tabelle der Regel vorkommt (``o.id = o.organization_id``): So sieht ein Name aus,
  der die Tabelle der Regel meinte und an die Einheit gebunden wurde;
- einen unbenannten Spaltennamen, den beide Tabellen haben (falls PostgreSQL einen Namen
  doch einmal ohne Tabelle ausgibt).
"""

import importlib
import re

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db

EINHEIT = "organizations_organization"

REGELN = """
    SELECT tablename, policyname, qual, with_check
    FROM pg_policies
    WHERE schemaname = 'public'
"""
SPALTEN = """
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
"""

_SCHLUESSELWORT = (
    r"WHERE|JOIN|ON|LEFT|RIGHT|INNER|FULL|CROSS|GROUP|ORDER|LIMIT|UNION|EXCEPT|INTERSECT"
)
# Tabelle in FROM, JOIN, nach einem Komma oder in Klammern (``FROM (a o JOIN b u ON ...)``),
# mit oder ohne Kürzel; nicht ``organizations_organization.spalte``
VON_EINHEIT = re.compile(
    rf"(?:\bFROM|\bJOIN|,|\()\s*(?:public\.)?{EINHEIT}\b(?!\.)"
    rf"(?:\s+(?:AS\s+)?(?!(?:{_SCHLUESSELWORT})\b)([a-z_][a-z0-9_]*))?",
    re.IGNORECASE,
)
ZEICHENKETTE = re.compile(r"'(?:[^']|'')*'")
TYPUMWANDLUNG = re.compile(r"::\s*\"?[a-z_][a-z0-9_ ]*?\"?(?:\[\])?(?=[\s)\],]|$)", re.I)
NAME = re.compile(r"(?<![\w.\"])([a-z_][a-z0-9_]*)\b(?!\s*[.(])")
NACH_AS = re.compile(r"\bAS\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)


def _unterabfrage(text: str, pos: int) -> str:
    """Text innerhalb der Klammer, die die Stelle ``pos`` umschließt."""
    tiefe = 0
    start = -1
    for i in range(pos - 1, -1, -1):
        if text[i] == ")":
            tiefe += 1
        elif text[i] == "(":
            if tiefe == 0:
                start = i
                break
            tiefe -= 1
    tiefe = 0
    for j in range(start + 1, len(text)):
        if text[j] == "(":
            tiefe += 1
        elif text[j] == ")":
            if tiefe == 0:
                return text[start + 1 : j]
            tiefe -= 1
    return text[start + 1 :]


def mehrdeutige_spalten(ausdruck: str, gemeinsam: set[str]) -> list[str]:
    """Funde in einem Regelausdruck; ``gemeinsam``: Spalten der Regeltabelle und der Einheit."""
    if not ausdruck:
        return []
    text = ZEICHENKETTE.sub("''", ausdruck)
    text = TYPUMWANDLUNG.sub("", text)
    funde = []
    for treffer in VON_EINHEIT.finditer(text):
        kuerzel = treffer.group(1) or EINHEIT
        teil = _unterabfrage(text, treffer.start())
        k = re.escape(kuerzel)
        selbst = re.compile(
            rf"(?<![\w.]){k}\.([a-z_][a-z0-9_]*)\s*(?:=|<>|!=)\s*{k}\.([a-z_][a-z0-9_]*)\b",
            re.IGNORECASE,
        )
        for links, rechts in selbst.findall(teil):
            if links != rechts and (links in gemeinsam or rechts in gemeinsam):
                funde.append(f"{kuerzel}.{links} = {kuerzel}.{rechts}")
        aliase = {a.lower() for a in NACH_AS.findall(teil)}
        for name in NAME.findall(teil):
            if name in gemeinsam and name != "id" and name not in aliase:
                funde.append(f"unbenannt: {name}")
    return funde


def _spalten() -> dict[str, set[str]]:
    spalten: dict[str, set[str]] = {}
    with connection.cursor() as cur:
        cur.execute(SPALTEN)
        for tabelle, spalte in cur.fetchall():
            spalten.setdefault(tabelle, set()).add(spalte)
    return spalten


def _funde_aller_regeln(nur: str | None = None) -> list[str]:
    spalten = _spalten()
    einheit = spalten[EINHEIT]
    funde = []
    with connection.cursor() as cur:
        cur.execute(REGELN)
        for tabelle, regel, using, check in cur.fetchall():
            if nur is not None and regel != nur:
                continue
            gemeinsam = (spalten.get(tabelle, set()) & einheit) - {"id"}
            for art, ausdruck in (("USING", using), ("WITH CHECK", check)):
                for fund in mehrdeutige_spalten(ausdruck, gemeinsam):
                    funde.append(f"{tabelle}.{regel} {art}: {fund}")
    return funde


@pytest.fixture(autouse=True)
def nur_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Zeilenschutz gibt es nur unter PostgreSQL")


def test_unterabfragen_ueber_einheiten_binden_eindeutig():
    funde = _funde_aller_regeln()
    assert funde == [], funde


def _probe(name: str, using: str) -> list[str]:
    """Regel nur in der Testtransaktion anlegen und prüfen (wird zurückgerollt)."""
    with connection.cursor() as cur:
        cur.execute(f"CREATE POLICY {name} ON events_event FOR SELECT USING ({using})")
    return _funde_aller_regeln(nur=name)


def test_waechter_erkennt_alte_termineregel():
    """Der Teil aus 0022 fällt auf, die berichtigte Fassung aus 0041 nicht."""
    neu = importlib.import_module("core.migrations.0041_rls_termine_nach_oben_spalten")
    alt = _probe("az04_probe_alt", neu.CHILD_SHARED_UP_0022)
    assert any("o.id = o.organization_id" in f for f in alt), alt
    assert _probe("az04_probe_neu", neu.CHILD_SHARED_UP) == []


def test_waechter_ohne_datenbank():
    """Ausgabeform von PostgreSQL, von Hand nachgestellt."""
    gemeinsam = {"organization_id", "created_at"}
    alt = (
        "((visibility)::text <> 'board'::text) AND (department_id IS NULL) AND (EXISTS ( "
        "SELECT 1 FROM organizations_organization o WHERE ((o.id = o.organization_id) AND "
        "(o.parent_id = (NULLIF(current_setting('app.org_id'::text, true), ''::text))::bigint) "
        "AND COALESCE(events_event.share_up, o.events_share_up))))"
    )
    neu = alt.replace("o.id = o.organization_id", "o.id = events_event.organization_id")
    unbenannt = alt.replace("o.id = o.organization_id", "o.id = organization_id")
    kinder = (
        "organization_id IN ( SELECT organizations_organization.id FROM "
        "organizations_organization WHERE (organizations_organization.parent_id = 1))"
    )
    assert mehrdeutige_spalten(alt, gemeinsam) == ["o.id = o.organization_id"]
    assert mehrdeutige_spalten(neu, gemeinsam) == []
    assert mehrdeutige_spalten(unbenannt, gemeinsam) == ["unbenannt: organization_id"]
    assert mehrdeutige_spalten(kinder, gemeinsam) == []
