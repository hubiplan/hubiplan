"""Mitgliederliste: Abfrage mit berechneten Spalten, Filter, Sortierung und Zeilen.

Ohne HTTP nutzbar: Liste, Export, Ausweise, Abrechnung je Untereinheit und offene Aufgaben
rufen dieselben Funktionen auf.
"""

from __future__ import annotations

from django.db.models import (
    Exists,
    F,
    OuterRef,
    Q,
    Subquery,
)

from organizations.models import Organization
from organizations.tree import with_descendants

from . import services
from .models import (
    ContactDetails,
    DepartmentMembership,
    Gender,
    HouseholdMember,
    Membership,
    MembershipPeriod,
    MemberTypeAssignment,
    PersonKind,
    today,
)
from .personsearch import name_ids_many, ordered


def _current_type(on):
    return MemberTypeAssignment.objects.filter(
        membership=OuterRef("pk"), valid_from__lte=on
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))


def _current_departments(on):
    return DepartmentMembership.objects.filter(
        membership=OuterRef("pk"), valid_from__lte=on
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))


def member_queryset(org: Organization):
    """Mitgliedschaften mit berechneten Spalten für Liste, Filter und Export."""
    on = today()
    open_period = MembershipPeriod.objects.filter(
        membership=OuterRef("pk"), entry_date__lte=on
    ).filter(Q(exit_date__isnull=True) | Q(exit_date__gte=on))
    current_type = _current_type(on)
    first_entry = MembershipPeriod.objects.filter(membership=OuterRef("pk")).order_by("entry_date")
    last_exit = MembershipPeriod.objects.filter(membership=OuterRef("pk")).order_by("-entry_date")
    return (
        Membership.objects.filter(organization=org)
        .select_related("person", "person__federation")
        .annotate(
            is_current=Exists(open_period),
            current_type_id=Subquery(current_type.values("member_type_id")[:1]),
            current_type_name=Subquery(current_type.values("member_type__name")[:1]),
            entry_date=Subquery(first_entry.values("entry_date")[:1]),
            exit_date=Subquery(last_exit.values("exit_date")[:1]),
        )
    )


def _email_word(word: str) -> bool:
    """Nur ganze Adressen (``name@example.org``) oder Domains ab dem @ (``@example.org``)
    suchen die E-Mail-Adressen durch (Fachfrage 8 zum Gesamtaudit 10.11.)."""
    local, at, domain = word.partition("@")
    return bool(at and domain and "@" not in domain)


def _persons_by_email(qs, words: list[str]) -> dict[str, set[int]]:
    """Entschlüsselt die sichtbaren Adressen einmal für alle Adress-Suchwörter.

    Ohne Wort mit @ wird keine Adresse entschlüsselt: Teilwörter wie „müller“ suchen
    nur in Namen und Nummern (Gesamtaudit 10.11. P01)."""
    matches = {word: set() for word in words}
    wanted = [word for word in words if _email_word(word)]
    if not wanted:
        return matches
    contacts = ContactDetails.objects.filter(person_id__in=qs.values("person_id")).values_list(
        "person_id", "email"
    )
    for pid, email in contacts.iterator():
        if email:
            email = email.strip().lower()
            for word in wanted:
                if email.endswith(word) if word.startswith("@") else email == word:
                    matches[word].add(pid)
    return matches


def filter_members(qs, params, org: Organization, *, lazy: bool = False):
    """Filter und Sortierung der Mitgliederliste. ``lazy=True`` für Listen mit
    Seitenschnitt: liefert ``OrderedRows`` statt eines QuerySets."""
    status_filter = params.get("status", "aktiv")
    if status_filter == "aktiv":
        qs = qs.filter(is_current=True)
    elif status_filter == "ehemalig":
        qs = qs.filter(is_current=False)
    if params.get("art"):
        qs = qs.filter(current_type_id=params["art"])
    kind = params.get("typ")
    if kind == "person":
        qs = qs.filter(person__kind=PersonKind.PERSON)
    elif kind == "organisation":
        qs = qs.filter(person__kind=PersonKind.ORGANIZATION)
    gender = params.get("geschlecht")
    if gender == "ohne":
        qs = qs.filter(person__gender="", person__kind=PersonKind.PERSON)
    elif gender in Gender.values:
        qs = qs.filter(person__gender=gender)
    if params.get("abteilung"):
        on = today()
        # Mitglieder der Untereinheit und aller Einheiten darunter
        unit_id = int(params["abteilung"]) if str(params["abteilung"]).isdigit() else 0
        unit_ids = with_descendants(org.pk, [unit_id]) or {unit_id}
        qs = qs.filter(
            Exists(
                DepartmentMembership.objects.filter(
                    membership=OuterRef("pk"),
                    department_id__in=unit_ids,
                    valid_from__lte=on,
                ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
            )
        )
    title = str(params.get("ehrentitel") or "")
    if title == "mit" or title.isdigit():
        from .honorary import current_awards, visible_orgs

        awards = current_awards().filter(
            person_id=OuterRef("person_id"), organization_id__in=visible_orgs(org)
        )
        if title.isdigit():
            awards = awards.filter(title_id=int(title))
        qs = qs.filter(Exists(awards))
    household = str(params.get("haushalt") or "")
    if household in ("mit", "ohne") or household.isdigit():
        from .households import open_on

        on = today()
        links = HouseholdMember.objects.filter(membership=OuterRef("pk")).filter(open_on(on))
        if household.isdigit():
            qs = qs.filter(Exists(links.filter(household_id=int(household))))
        elif household == "mit":
            qs = qs.filter(Exists(links))
        else:
            qs = qs.filter(~Exists(links))
    search = (params.get("suche") or "").strip()
    if search:
        words = {}
        for word in search.split():
            # SQL-Nummernvergleich behält die Originalschreibweise; Namen folgen
            # der zentralen NFC-/Casefold-Regel, E-Mails wie bisher lower().
            words.setdefault(word.lower(), word)
        email_matches = _persons_by_email(qs, list(words))
        name_matches = name_ids_many(qs, words.values())
        q = Q()
        for normalized, word in words.items():
            word_q = (
                Q(pk__in=name_matches[word])
                | Q(club_number__iexact=word)
                | Q(person_id__in=email_matches[normalized])
            )
            if word.isdigit():
                word_q |= Q(person__federation__member_number=int(word))
            q &= word_q
        qs = qs.filter(q)
    sort = params.get("sortierung") or "name"
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    if key == "art":
        qs = qs.annotate(
            sort_key=Subquery(_current_type(today()).values("member_type__sort_order")[:1]),
            sort_name=F("current_type_name"),
        )
    elif key == "abteilung":
        first_dep = _current_departments(today()).order_by(
            "department__sort_order", "department__name"
        )
        qs = qs.annotate(
            sort_key=Subquery(first_dep.values("department__sort_order")[:1]),
            sort_name=Subquery(first_dep.values("department__name")[:1]),
        )
    elif key == "ehrentitel":
        from .honorary import current_awards, visible_orgs

        first_title = (
            current_awards()
            .filter(person_id=OuterRef("person_id"), organization_id__in=visible_orgs(org))
            .order_by("title__organization__type", "title__sort_order", "title__name")
        )
        qs = qs.annotate(
            sort_key=Subquery(first_title.values("title__sort_order")[:1]),
            sort_name=Subquery(first_title.values("title__name")[:1]),
        )
    if key in ("art", "abteilung", "ehrentitel"):
        # Ohne Mitgliedsart, Abteilung bzw. Ehrung stehen in beiden Richtungen am Ende.
        ordering = [
            getattr(F(f), "desc" if desc else "asc")(nulls_last=True)
            for f in ("sort_key", "sort_name")
        ] + ["person__last_name", "person__first_name"]
        return ordered(qs, *ordering, "pk", lazy=lazy)
    if key == "geburtsdatum":
        return _by_birth(qs, desc, lazy=lazy)
    ordering = {
        "name": ("person__last_name", "person__first_name"),
        "-name": ("-person__last_name", "-person__first_name"),
        "eintritt": ("entry_date", "person__last_name"),
        "-eintritt": ("-entry_date", "person__last_name"),
        "nummer": ("club_number",),
        "-nummer": ("-club_number",),
    }.get(sort, ("person__last_name", "person__first_name"))
    return ordered(qs, *ordering, "pk", lazy=lazy)


def _by_birth(qs, desc: bool, *, lazy: bool = False):
    """Unbekannte Daten stehen wie bisher in beiden Richtungen am Ende."""
    term = F("person__birth_date")
    return ordered(qs, term.desc(nulls_last=True) if desc else term.asc(nulls_last=True), lazy=lazy)


def member_rows(memberships, org: Organization, full_names: bool = False) -> list[dict]:
    """Zeilen der Mitgliederliste; Kontakt und Abteilungen nur für diese Seite laden.

    Abteilungen stehen in der Liste mit Kurznamen, in Exporten (``full_names``)
    mit vollem Namen.
    """
    on = today()
    ids = [m.pk for m in memberships]
    person_ids = [m.person_id for m in memberships]
    contacts: dict[int, ContactDetails] = {}
    shared = services.shared_contacts()
    for c in ContactDetails.objects.filter(person_id__in=person_ids):
        own = c.organization_id == org.pk
        if c.organization_id is None or own:
            prefer = own != shared  # gemeinsam: gemeinsamer Datensatz zuerst
            if c.person_id not in contacts or prefer:
                contacts[c.person_id] = c
    from .photo_models import MemberPhoto

    photos = {
        p.membership_id: int(p.updated_at.timestamp())
        for p in MemberPhoto.objects.filter(membership_id__in=ids, status="approved")
    }
    departments: dict[int, list[str]] = {}
    for dm in (
        DepartmentMembership.objects.filter(membership_id__in=ids, valid_from__lte=on)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
        .select_related("department")
        .order_by("department__sort_order", "department__name")
    ):
        departments.setdefault(dm.membership_id, []).append(
            dm.department.name if full_names else dm.department.display_name
        )
    from .honorary import titles_by_person

    titles = titles_by_person(person_ids, org, on)
    from .households import households_by_membership

    homes = households_by_membership(ids, on)
    rows = []
    for m in memberships:
        c = contacts.get(m.person_id)
        fm = getattr(m.person, "federation", None)
        rows.append(
            {
                "id": m.pk,
                "kind": m.person.kind,
                "last_name": m.person.last_name,
                "first_name": m.person.first_name,
                "name_suffix": m.person.name_suffix,
                "birth_date": m.person.birth_date,
                "birth_year_only": m.person.birth_year_only,
                "gender": m.person.gender,
                "title": m.person.title,
                "club_number": m.club_number,
                "member_number": fm.member_number if fm else None,
                "member_type": m.current_type_name,
                "status": "active" if m.is_current else "former",
                "entry_date": m.entry_date,
                "exit_date": None if m.is_current else m.exit_date,
                "departments": departments.get(m.pk, []),
                "honorary_titles": titles.get(m.person_id, []),
                # Familienhaushalt und Firma (Konzept Familien, Haushalte und Firmen, H1)
                "households": [
                    {"id": h["id"], "name": h["name"], "kind": h["kind"], "role": h["role"]}
                    for h in homes.get(m.pk, [])
                ],
                "photo_url": (
                    f"/api/orgs/{m.organization_id}/members/{m.pk}/photo/"
                    f"?size=thumb&v={photos[m.pk]}"
                    if m.pk in photos
                    else None
                ),
                "email": c.email if c else "",
                "phone": c.phone if c else "",
                "street": c.street if c else "",
                "postal_code": c.postal_code if c else "",
                "city": c.city if c else "",
            }
        )
    return rows
