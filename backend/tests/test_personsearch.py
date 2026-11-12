"""Namenssuche ohne SQL-Namensvergleich: Listen, Reihenfolge und ORM-Sperre."""

import ast
import datetime
import time
from pathlib import Path

import pytest
from django.core.exceptions import FieldError
from django.db import connection
from django.db.models import Case, Count, F, IntegerField, Subquery, Value, When
from django.db.models.functions import Lower
from django.test.utils import CaptureQueriesContext

from core.tenancy import rls_bypass
from members.federation_views import federation_queryset, filter_federation
from members.models import ContactDetails, Membership, Person
from members.personsearch import filter_names, name_ids, normalize, ordered, text_key
from members.views import filter_members, member_queryset, member_rows

from .factories import make_member

pytestmark = pytest.mark.django_db


def test_unicode_und_feste_sortierregel():
    assert normalize("Straße") == normalize("STRASSE")
    assert normalize("Mu\u0308ller") == normalize("Müller")
    names = ["Zorn", "Öster", "Müller", "Adler", "Äcker", "Acker", "Mueller"]
    assert sorted(names, key=text_key) == [
        "Acker",
        "Äcker",
        "Adler",
        "Mueller",
        "Müller",
        "Öster",
        "Zorn",
    ]


def test_suche_erhaelt_oder_mit_email_nummern_und_woertern(orgs):
    anna = make_member(orgs["a"], "Anna", "Müller", email="kontakt@example.org")
    bernd = make_member(orgs["a"], "Bernd", "Anders", email="anna@example.org")
    make_member(orgs["b"], "Anna", "Müller")
    with rls_bypass():
        anna.club_number = "ABC-17"
        anna.save(update_fields=["club_number"])
        for search in ("anna kontakt@example.org", "ABC-17", "Mu\u0308ller", "Anna Müller"):
            found = filter_members(member_queryset(orgs["a"]), {"suche": search}, orgs["a"])
            assert list(found.values_list("pk", flat=True)) == [anna.pk]
        # Ein Wort darf über E-Mail treffen, auch wenn es im Namen nicht vorkommt, aber
        # nur als ganze Adresse oder ab dem @ (Gesamtaudit 10.11., Fachfrage 8).
        found = filter_members(member_queryset(orgs["a"]), {"suche": "anna"}, orgs["a"])
        assert list(found.values_list("pk", flat=True)) == [anna.pk]
        found = filter_members(member_queryset(orgs["a"]), {"suche": "anna@example.org"}, orgs["a"])
        assert list(found.values_list("pk", flat=True)) == [bernd.pk]
        found = filter_members(member_queryset(orgs["a"]), {"suche": "@example.org"}, orgs["a"])
        assert {anna.pk, bernd.pk} <= set(found.values_list("pk", flat=True))


def test_varianten_und_limit_erst_nach_suche(orgs):
    from competitions.views import _umlaut_variants

    first = make_member(orgs["c"], "Anna", "Müller")
    make_member(orgs["c"], "Berta", "Mueller")
    with rls_bypass():
        qs = Membership.objects.filter(organization=orgs["c"])
        qs = filter_names(qs, "muel", variants=_umlaut_variants)
        assert ordered(qs).count() == 2
        assert list(ordered(filter_names(qs, "Anna"), limit=1).values_list("pk", flat=True)) == [
            first.pk
        ]


def test_zeilen_ids_und_annotationen_bleiben_erhalten(orgs):
    member = make_member(orgs["a"], "Anna", "Gleich")
    with rls_bypass():
        other = Membership.objects.create(
            organization=orgs["b"], scope=orgs["federation"], person=member.person
        )
        qs = filter_federation(federation_queryset(orgs["federation"]), {"status": "alle"})
        qs = qs.annotate(marker=Value("bleibt"))
        rows = list(ordered(qs))
        assert [row.pk for row in rows] == sorted([member.pk, other.pk])
        assert all(row.marker == "bleibt" for row in rows)
        assert name_ids(qs, "gleich") == {member.pk, other.pk}
        assert list(ordered(qs, "-person__last_name").values_list("pk", flat=True)) == sorted(
            [member.pk, other.pk]
        )


def test_neue_zeilen_ohne_sortierposition_kommen_nicht_in_die_seite(orgs):
    first = make_member(orgs["c"], "Anna", "Alt")
    with rls_bypass():
        page = ordered(Membership.objects.filter(organization=orgs["c"]))
        make_member(orgs["c"], "Berta", "Neu")
        assert list(page.values_list("pk", flat=True)) == [first.pk]


def test_gemischte_sortierung_nulls_und_geburtsdatum(orgs):
    old = make_member(orgs["c"], "Anna", "Adler", birth_date=datetime.date(1960, 1, 1))
    young = make_member(orgs["c"], "Berta", "Berg", birth_date=datetime.date(2000, 1, 1))
    with rls_bypass():
        qs = Membership.objects.filter(organization=orgs["c"])
        assert list(ordered(qs, "-person__birth_date").values_list("pk", flat=True)) == [
            young.pk,
            old.pk,
        ]
        qs = qs.annotate(marker=F("club_number"))
        # „old“ ohne Nummer (die Aufnahme vergibt sonst automatisch eine)
        Membership.objects.filter(pk=old.pk).update(club_number="")
        Membership.objects.filter(pk=young.pk).update(club_number="1")
        assert list(ordered(qs, "-marker", "person__last_name").values_list("pk", flat=True)) == [
            young.pk,
            old.pk,
        ]
        qs = qs.annotate(
            group=Case(
                When(pk=young.pk, then=Value(None)), default=Value(1), output_field=IntegerField()
            )
        )
        assert list(ordered(qs, F("group").desc(nulls_last=True)).values_list("pk", flat=True)) == [
            old.pk,
            young.pk,
        ]
        assert list(ordered(qs, F("group").asc(nulls_first=True)).values_list("pk", flat=True)) == [
            young.pk,
            old.pk,
        ]
        # FK in einem bestehenden QuerySet kann leer sein, etwa bei Mandaten an Vereine.
        from billing.models import Mandate

        empty = Mandate.objects.filter(organization=orgs["c"])
        assert name_ids(empty, "Anna", fields=("membership__person__last_name",)) == set()


def test_pagination_stabil_und_objekte_nur_fuer_seite(orgs):
    with rls_bypass():
        people = Person.objects.bulk_create(
            [
                Person(
                    scope=orgs["c"],
                    last_name="Gleich",
                    first_name="Anna",
                    birth_date=datetime.date(1980, 1, 1),
                )
                for _ in range(61)
            ]
        )
        Membership.objects.bulk_create(
            [Membership(organization=orgs["c"], scope=orgs["c"], person=p) for p in people]
        )
        with CaptureQueriesContext(connection) as queries:
            qs = ordered(Membership.objects.filter(organization=orgs["c"]).select_related("person"))
            page1 = list(qs[:50])
            page2 = list(qs[50:])
        ids = [row.pk for row in page1 + page2]
        assert len(page1) == 50 and len(page2) == 11
        assert ids == sorted(ids) and len(set(ids)) == 61
        assert len(queries) == 3  # Sortierspalten, dann zwei Objektseiten.
        assert "LIMIT 50" in queries[1]["sql"]
        assert "OFFSET 50" in queries[2]["sql"]
        assert 'ORDER BY "members_person"."last_name"' not in str(qs.query)
        with pytest.raises(ValueError, match="Seitenschnitt"):
            ordered(qs[:10])


@pytest.mark.parametrize(
    "query",
    [
        lambda: Person.objects.order_by("last_name"),
        lambda: Membership.objects.order_by("person__first_name"),
        lambda: Person.objects.order_by(Lower("last_name")),
        lambda: Person.objects.order_by("birth_date"),
        lambda: Membership.objects.order_by("person__birth_date"),
        lambda: Person.objects.order_by(F("birth_date").desc()),
        lambda: Person.objects.annotate(alias=F("birth_date")).order_by("alias"),
        lambda: Person.objects.annotate(
            alias=Subquery(Person.objects.order_by("pk").values("birth_date")[:1])
        ).order_by("alias"),
        lambda: ContactDetails.objects.order_by(Lower("email")),
        lambda: Person.objects.values("birth_date").order_by("birth_date"),
        lambda: (
            Person.objects.values("birth_date")
            .union(Person.objects.values("birth_date"))
            .order_by("birth_date")
        ),
    ],
)
def test_sql_sortierung_verschluesselter_felder_scheitert(query):
    with pytest.raises(FieldError, match="verschlüsselt"):
        str(query().query)


def test_sortierung_nach_normalen_aggregaten_bleibt_moeglich():
    # Das Sternchen in COUNT(*) hat selbst keinen output_field.
    query = Person.objects.annotate(total=Count("*")).order_by("total")
    assert "COUNT(*)" in str(query.query)


def test_implizite_sortierung_und_python_sortierung(orgs, monkeypatch):
    member = make_member(orgs["c"], "Anna", "Muster")
    monkeypatch.setattr(ContactDetails._meta, "ordering", ["email"])
    with rls_bypass():
        qs = ContactDetails.objects.filter(person=member.person)
        with pytest.raises(FieldError, match="verschlüsselt"):
            list(qs)
        with pytest.raises(FieldError, match="verschlüsselt"):
            str(Person.objects.order_by("contacts").query)
        assert list(ordered(qs, "email").values_list("email", flat=True)) == ["anna@example.org"]


def test_keine_direkten_sql_namenssuchen_oder_sortierungen_in_listen():
    root = Path(__file__).parents[1]
    files = [
        "members/views.py",
        "members/federation_views.py",
        "billing/views.py",
        "billing/services.py",
        "billing/units.py",
        "cards/views.py",
        "circulars/recipients.py",
        "competitions/views.py",
        "competitions/event_views.py",
        "entries/views.py",
        "entries/event_views.py",
        "honors/views.py",
        "events/rsvp.py",
        "portal/views.py",
        "peering/spinoff.py",
    ]
    for path in files:
        for node in ast.walk(ast.parse((root / path).read_text())):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                assert not kw.arg or not kw.arg.endswith(
                    ("person__last_name__icontains", "person__first_name__icontains")
                ), path
            if isinstance(node.func, ast.Attribute) and node.func.attr == "order_by":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        assert not arg.value.endswith(
                            ("person__last_name", "person__first_name")
                        ), path


@pytest.mark.langsam
@pytest.mark.django_db(transaction=True)
def test_leistungsmessung_5000_mitgliedschaften(orgs):
    with rls_bypass():
        people = Person.objects.bulk_create(
            [
                Person(
                    scope=orgs["c"],
                    last_name=f"Müller {i:05}",
                    first_name="Anna",
                    birth_date=datetime.date(1980, 1, 1),
                )
                for i in range(5000)
            ]
        )
        Membership.objects.bulk_create(
            [Membership(organization=orgs["c"], scope=orgs["c"], person=p) for p in people]
        )
        started = time.perf_counter()
        qs = filter_members(member_queryset(orgs["c"]), {"status": "alle"}, orgs["c"])
        page = list(qs[:50])
        rows = member_rows(page, orgs["c"])
        elapsed = (time.perf_counter() - started) * 1000
        print(f"Mitgliederliste 5000 / Seite 50: {elapsed:.1f} ms")
        assert len(rows) == 50
        assert rows[0]["last_name"] == "Müller 00000"
        ContactDetails.objects.bulk_create(
            [
                ContactDetails(
                    organization=orgs["c"],
                    scope=orgs["c"],
                    person=p,
                    email=f"person{i:05}@example.org",
                    street=f"Musterweg {i}",
                    postal_code="12345",
                    city="Musterstadt",
                )
                for i, p in enumerate(people)
            ]
        )
        started = time.perf_counter()
        contacts = ordered(ContactDetails.objects.filter(organization=orgs["c"]), "email", "street")
        assert len(list(contacts[:50])) == 50
        elapsed = (time.perf_counter() - started) * 1000
        print(f"Sortierung 5000 / zwei tatsächlich verschlüsselte Spalten: {elapsed:.1f} ms")
        # Kein harter Zeitgrenzwert: geteilte Testplätze liefern keine stabile Last.


def test_seitenschnitt_vor_der_positionsliste(api, orgs, board_c, monkeypatch):
    """Gesamtaudit 10.11. P01: gleiche Treffer, Zahl und Reihenfolge; nur die Seite geht
    mit ihrer Position an Postgres."""
    from members import personsearch

    for first, last in [("Ida", "Zorn"), ("Ute", "Äcker"), ("Max", "Adler"), ("Eva", "Berg")]:
        make_member(orgs["c"], first, last)
    base = f"/api/orgs/{orgs['c'].pk}/members/"
    full = api(board_c).get(base).json()
    names = [row["last_name"] for row in full["results"]]
    assert full["count"] >= 4
    sizes = []
    original = personsearch._by_position

    def spy(qs, ids):
        sizes.append(len(ids))
        return original(qs, ids)

    monkeypatch.setattr(personsearch, "_by_position", spy)
    page = api(board_c).get(base + "?page_size=2&page=2").json()
    assert page["count"] == full["count"]
    assert [row["last_name"] for row in page["results"]] == names[2:4]
    assert sizes == [2]
