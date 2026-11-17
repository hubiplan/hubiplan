"""Wächter: Unterabfragen in Zeilenschutzregeln binden Spalten eindeutig
(Gesamtaudit 15.11., AZ-04).

Die Regel für ``events_event`` (core 0020/0022) prüfte die Weitergabe nach oben mit
``SELECT 1 FROM organizations_organization o WHERE o.id = organization_id``. Seit
organizations 0014 hat die Einheit selbst eine Spalte ``organization_id``. PostgreSQL bindet
den unbenannten Namen an die innerste Tabelle, die Bedingung wurde ``o.id = o.organization_id``
und traf nie zu.

Der Wächter liest alle Regeln aus ``pg_policies`` (USING und WITH CHECK). PostgreSQL gibt
Spalten in Unterabfragen mit der Tabelle aus, an die sie gebunden sind: ``o.organization_id``
für die innere Tabelle, ``events_event.organization_id`` für die Tabelle der Regel. Je
Unterabfrage (``FROM``/``JOIN`` einer beliebigen Tabelle, mit oder ohne Kürzel) meldet er

- einen Vergleich zweier verschiedener Spalten derselben inneren Tabelle, von denen mindestens
  eine auch in der Tabelle der Regel vorkommt (``o.id = o.organization_id``): So sieht ein Name
  aus, der die Tabelle der Regel meinte und an die innere Tabelle gebunden wurde;
- einen unbenannten Spaltennamen, den beide Tabellen haben (falls PostgreSQL einen Namen
  doch einmal ohne Tabelle ausgibt).

Gewollte Vergleiche innerhalb einer Tabelle stehen mit Begründung in ``AUSNAHMEN``.
"""

import importlib
import re
from typing import NamedTuple

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db

# (Tabelle der Regel, Name der Regel, Fund) -> Begründung, warum der Vergleich gewollt ist
AUSNAHMEN: dict[tuple[str, str, str], str] = {}

REGELN = """
    SELECT tablename, policyname, cmd, qual, with_check
    FROM pg_policies
    WHERE schemaname = 'public'
    ORDER BY tablename, policyname
"""
SPALTEN = """
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
"""

_SCHLUESSELWORT = (
    r"WHERE|JOIN|ON|USING|LEFT|RIGHT|INNER|FULL|CROSS|NATURAL|LATERAL|GROUP|HAVING|ORDER|"
    r"LIMIT|OFFSET|UNION|EXCEPT|INTERSECT|WINDOW|FOR|AND|OR|NOT"
)
# Tabelle in FROM, JOIN, nach einem Komma oder in Klammern (``FROM (a o JOIN b u ON ...)``),
# mit oder ohne Kürzel; nicht ``tabelle.spalte`` und keine Funktion. Ob es eine Tabelle ist,
# entscheidet die Spaltenliste aus information_schema.
VON_TABELLE = re.compile(
    r"(?:\bFROM|\bJOIN|,|\()\s*(?:public\.)?([a-z_][a-z0-9_]*)\b(?![.(])"
    rf"(?:\s+(?:AS\s+)?(?!(?:{_SCHLUESSELWORT})\b)([a-z_][a-z0-9_]*)\b(?![.(]))?",
    re.IGNORECASE,
)
ZEICHENKETTE = re.compile(r"'(?:[^']|'')*'")
TYPUMWANDLUNG = re.compile(r"::\s*\"?[a-z_][a-z0-9_ ]*?\"?(?:\[\])?(?=[\s)\],]|$)", re.I)
# Kleingeschriebene Namen ohne Tabelle davor, nicht vor einem Punkt (Tabelle/Kürzel) und keine
# Funktion; Schlüsselwörter gibt PostgreSQL groß aus.
NAME = re.compile(r"(?<![\w.\"])([a-z_][a-z0-9_]*)\b(?!\s*[.(])")
NACH_AS = re.compile(r"\bAS\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
# Feld in ``EXTRACT(year FROM ...)``
EXTRACT_FELD = re.compile(r"\bEXTRACT\s*\(\s*([a-z_]+)\s+FROM\b", re.IGNORECASE)
# Reste von Typnamen und Literale, die klein ausgegeben werden
KEIN_NAME = {
    "true", "false", "null", "with", "without", "time", "zone", "varying", "precision",
    "double", "character", "public",
}  # fmt: skip


class Fund(NamedTuple):
    text: str  # z. B. ``o.id = o.organization_id`` oder ``unbenannt: organization_id``
    innen: str  # Tabelle der Unterabfrage
    auszug: str  # Anfang der Unterabfrage


def _klammerpaare(text: str) -> list[tuple[int, int]]:
    paare, stapel = [], []
    for i, zeichen in enumerate(text):
        if zeichen == "(":
            stapel.append(i)
        elif zeichen == ")" and stapel:
            paare.append((stapel.pop(), i))
    paare.extend((start, len(text)) for start in stapel)
    return paare


def _unterabfrage(text: str, pos: int, paare: list[tuple[int, int]]) -> str:
    """Innerste ``( SELECT ... )``, die die Stelle ``pos`` umschließt.

    Bei ``FROM (a o JOIN b u ON ...) WHERE ...`` umschließt die Klammer des JOIN die
    WHERE-Bedingung nicht; gesucht ist deshalb die Klammer, deren Inhalt mit SELECT beginnt.
    """
    umschliessend = sorted(((s, e) for s, e in paare if s < pos < e), key=lambda p: p[1] - p[0])
    for start, ende in umschliessend:
        inhalt = text[start + 1 : ende]
        if inhalt.lstrip().upper().startswith("SELECT"):
            return inhalt
    return text


def _kurz(text: str, laenge: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


def mehrdeutige_spalten(
    ausdruck: str | None, aussen: set[str], tabellen: dict[str, set[str]]
) -> list[Fund]:
    """Funde in einem Regelausdruck.

    ``aussen``: Spalten der Tabelle der Regel; ``tabellen``: Spalten aller Tabellen.
    """
    if not ausdruck:
        return []
    text = ZEICHENKETTE.sub("''", ausdruck)
    text = TYPUMWANDLUNG.sub("", text)
    paare = _klammerpaare(text)
    funde: list[Fund] = []
    gesehen: set[str] = set()
    treffer_liste = [t for t in VON_TABELLE.finditer(text) if t.group(1) in tabellen]
    kuerzel_alle = {t.group(2) or t.group(1) for t in treffer_liste}

    def melden(fund: str, innen: str, teil: str) -> None:
        if fund not in gesehen:
            gesehen.add(fund)
            funde.append(Fund(fund, innen, _kurz(teil)))

    for treffer in treffer_liste:
        innen = treffer.group(1)
        kuerzel = treffer.group(2) or innen
        teil = _unterabfrage(text, treffer.start(1), paare)
        k = re.escape(kuerzel)
        selbst = re.compile(
            rf"(?<![\w.]){k}\.([a-z_][a-z0-9_]*)\s*(=|<>|!=)\s*{k}\.([a-z_][a-z0-9_]*)\b",
            re.IGNORECASE,
        )
        for links, op, rechts in selbst.findall(teil):
            if links != rechts and (links in aussen or rechts in aussen):
                melden(f"{kuerzel}.{links} {op} {kuerzel}.{rechts}", innen, teil)
        gemeinsam = (aussen & tabellen[innen]) - {"id"}
        ausgenommen = (
            kuerzel_alle
            | {a.lower() for a in NACH_AS.findall(teil)}
            | {f.lower() for f in EXTRACT_FELD.findall(teil)}
            | KEIN_NAME
        )
        for name in NAME.findall(teil):
            if name in gemeinsam and name not in ausgenommen:
                melden(f"unbenannt: {name}", innen, teil)
    return funde


def _spalten() -> dict[str, set[str]]:
    spalten: dict[str, set[str]] = {}
    with connection.cursor() as cur:
        cur.execute(SPALTEN)
        for tabelle, spalte in cur.fetchall():
            spalten.setdefault(tabelle, set()).add(spalte)
    return spalten


def _funde_aller_regeln(nur: str | None = None) -> list[tuple[str, str, str, str, Fund]]:
    """(Tabelle, Regel, Befehl, USING/WITH CHECK, Fund) für alle Regeln."""
    spalten = _spalten()
    funde = []
    with connection.cursor() as cur:
        cur.execute(REGELN)
        for tabelle, regel, befehl, using, check in cur.fetchall():
            if nur is not None and regel != nur:
                continue
            aussen = spalten.get(tabelle, set())
            for art, ausdruck in (("USING", using), ("WITH CHECK", check)):
                for fund in mehrdeutige_spalten(ausdruck, aussen, spalten):
                    funde.append((tabelle, regel, befehl, art, fund))
    return funde


def _bericht(funde) -> str:
    return "\n".join(
        " | ".join((tabelle, regel, befehl, art, fund.text, f"FROM {fund.innen}", fund.auszug))
        for tabelle, regel, befehl, art, fund in funde
    )


@pytest.fixture(autouse=True)
def nur_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Zeilenschutz gibt es nur unter PostgreSQL")


def test_unterabfragen_binden_eindeutig():
    """Alle Funde aller Regeln auf einmal melden, außer begründeten Ausnahmen."""
    funde = _funde_aller_regeln()
    offen = [f for f in funde if (f[0], f[1], f[4].text) not in AUSNAHMEN]
    assert offen == [], f"{len(offen)} Fund(e):\n{_bericht(offen)}"


def test_ausnahmen_treffen_noch_zu():
    """Eine Ausnahme ohne passenden Fund ist veraltet und wird gestrichen."""
    gefunden = {(f[0], f[1], f[4].text) for f in _funde_aller_regeln()}
    veraltet = [schluessel for schluessel in AUSNAHMEN if schluessel not in gefunden]
    assert veraltet == [], veraltet


def _probe(name: str, using: str) -> list[tuple[str, str, str, str, Fund]]:
    """Regel nur in der Testtransaktion anlegen und prüfen (wird zurückgerollt)."""
    with connection.cursor() as cur:
        cur.execute(f"CREATE POLICY {name} ON events_event FOR SELECT USING ({using})")
    return _funde_aller_regeln(nur=name)


def test_waechter_erkennt_alte_termineregel():
    """Die Regel aus 0022 fällt auf, die berichtigte Fassung aus 0041 nicht."""
    neu = importlib.import_module("core.migrations.0041_rls_termine_nach_oben_spalten")
    alt = _probe("az04_probe_alt", neu.OLD["events_event"][0])
    assert any(f[4].text == "o.id = o.organization_id" for f in alt), _bericht(alt)
    berichtigt = _probe("az04_probe_neu", neu.POLICIES["events_event"][0])
    assert berichtigt == [], _bericht(berichtigt)


TABELLEN = {
    "events_event": {"id", "organization_id", "share_up", "visibility", "created_at"},
    "organizations_organization": {
        "id", "organization_id", "parent_id", "events_share_up", "created_at",
    },
    "members_membership": {"id", "organization_id", "person_id", "role_id", "created_at"},
    "access_role": {"id", "organization_id", "name"},
    "peering_coupling": {"id", "remote_unit_id", "local_unit_id", "direction", "state"},
}  # fmt: skip


def _texte(ausdruck: str, tabelle: str = "events_event") -> list[str]:
    return [f.text for f in mehrdeutige_spalten(ausdruck, TABELLEN[tabelle], TABELLEN)]


def test_waechter_ohne_datenbank():
    """Ausgabeform von PostgreSQL, von Hand nachgestellt."""
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
    ohne_kuerzel = kinder.replace(
        "organizations_organization.parent_id = 1",
        "organizations_organization.id = organizations_organization.organization_id",
    )
    kopplung = (
        "(EXISTS ( SELECT 1 FROM peering_coupling c WHERE ((c.remote_unit_id = "
        "events_event.organization_id) AND ((c.state)::text = 'active'::text))))"
    )
    assert _texte(alt) == ["o.id = o.organization_id"]
    assert _texte(neu) == []
    assert _texte(unbenannt) == ["unbenannt: organization_id"]
    assert _texte(kinder) == []
    assert _texte(ohne_kuerzel) == [
        "organizations_organization.id = organizations_organization.organization_id"
    ]
    assert _texte(kopplung) == []


def test_waechter_andere_tabellen_ohne_datenbank():
    """Jede Tabelle in einer Unterabfrage wird geprüft, nicht nur die Einheit."""
    mitglied = "(EXISTS ( SELECT 1 FROM members_membership m WHERE (m.id = m.organization_id)))"
    assert _texte(mitglied) == ["m.id = m.organization_id"]
    # Über JOIN: die WHERE-Bedingung steht außerhalb der Klammer des JOIN
    verbund = (
        "(EXISTS ( SELECT 1 FROM (members_membership m JOIN access_role r "
        "ON ((r.id = m.role_id))) WHERE ((m.person_id = 1) AND (r.organization_id <> r.id))))"
    )
    assert _texte(verbund) == ["r.organization_id <> r.id"]
    # Spalten, die die Tabelle der Regel nicht hat, deuten nicht auf eine falsche Bindung
    eigene = "(EXISTS ( SELECT 1 FROM members_membership m WHERE (m.person_id = m.role_id)))"
    assert _texte(eigene) == []
    # Zeichenketten, Funktionen, Typumwandlungen und EXTRACT-Felder sind keine Spalten
    falle = (
        "(EXISTS ( SELECT 1 FROM members_membership m WHERE ((m.person_id = 1) AND "
        "('m.id = m.organization_id organization_id'::text <> ''::text) AND "
        "(organization_id(m.id) IS NULL) AND (EXTRACT(created_at FROM now()) > (0)::numeric))))"
    )
    assert _texte(falle) == []
