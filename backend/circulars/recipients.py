"""Empfänger eines Rundschreibens aus der Auswahl berechnen.

Auswahl (``Circular.filters``), alle Angaben optional und mit UND verknüpft,
mehrere Werte in einer Angabe mit ODER:

Verein bzw. Abteilung (aktuelle Mitglieder):

- ``member_types``  Mitgliedsarten (Nummern)
- ``departments``   Abteilungen (Nummern; im Abteilungsbereich fest die eigene)
- ``roles``         Inhaber dieser Abteilungsrollen
- ``board``         nur Mitglieder mit einer Vorstandsrolle des Vereins
- ``age_min``/``age_max``  Alter heute
- ``organizations_any_age``  Organisationsmitglieder (ohne Alter) bleiben trotz Altersfilter
  (Einladung zur Versammlung, J4)
- ``jubilee_year``  Jubilare dieses Jahres (Verein oder Dachverband)
- ``honorary_titles``  Inhaber dieser Ehrungen (des Vereins oder des Dachverbands)
- ``households_merge``  Briefe (und Mails an dieselbe Adresse) an einen Familienhaushalt
  zusammenfassen; fehlt die Angabe, gilt „ja“ (Konzept Familien, Haushalte und Firmen, H1)
- ``event_responses``  nur bei einem Rundschreiben zu einem Termin (``Circular.event``):
  Eingeladene mit dieser Rückmeldung (``open`` = noch keine, ``yes``, ``no``, ``maybe``)

Rundschreiben zu einem Termin gehen nur an die Eingeladenen des Termins
(``events.rsvp.invited``); die übrigen Angaben schränken weiter ein.

Verein mit ``audience`` = ``departments``: Inhaber von Abteilungsrollen,
eingeschränkt mit ``departments`` und ``role_names`` (Rollennamen, z. B. alle
„Oberleutnant“).

Dachverband: ``audience`` des Rundschreibens = ``boards`` (Vorstände der
Vereine) oder ``members`` (nur mit Mitgliederzugriff); dazu ``clubs`` und
``reported`` (nur an den Dachverband gemeldete) und ``honorary_titles``
(Ehrungen des Dachverbands).

Immer: ``include`` (zusätzlich, Schlüssel wie ``m12``) und ``exclude``
(abgewählt). Abgewählte bleiben in der Vorschau sichtbar, damit man sie wieder
aufnehmen kann.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from django.db.models import Exists, OuterRef, Q

from access.models import RoleAssignment
from core.tenancy import rls_bypass
from members.duration import Duration, club_ranges, jubilees_between
from members.households import address_key, and_join, family_last_name, letter_name
from members.models import (
    DepartmentMembership,
    DepartmentRoleHolder,
    Gender,
    Membership,
    today,
    with_title,
)
from members.personsearch import ordered
from organizations.models import Organization
from organizations.tree import subtree_ids, with_descendants

from .models import Circular

MAX_RECIPIENTS = 20000
NOTE_OPT_OUT = "hat Informationen per E-Mail abbestellt"
NOTE_LETTER = "keine E-Mail-Adresse: Brief"
NOTE_APP = "per App"
NOTE_APP_MAIL = "per App und E-Mail"
NOTE_PORTAL = "weder App noch E-Mail: nur im Mitgliederbereich"
NOTE_MERGED = "im gemeinsamen Schreiben an den Haushalt"


@dataclass
class Candidate:
    key: str
    club: Organization
    first_name: str
    last_name: str
    email: str = ""
    gender: str = ""
    # Titel vor dem Nachnamen in der förmlichen Anrede („Sehr geehrter Herr Dr. Muster“)
    title: str = ""
    address: str = ""
    membership_id: int | None = None
    user_id: int | None = None
    departments: list[str] = field(default_factory=list)
    opted_out: bool = False
    excluded: bool = False
    included: bool = False  # einzeln hinzugefügt
    # Zugang zum Mitgliederbereich mit App und Push (sonst None)
    app_access: int | None = None
    # App-Nutzer bekommen zusätzlich die Mail
    also_mail: bool = False
    # Kurzmitteilung: nie als Brief
    short: bool = False
    values: dict[str, str] = field(default_factory=dict)
    # für Platzhalter, nur bei Bedarf geladen
    membership: Membership | None = None
    # Organisationsmitglied: Name der Organisation; ohne Ansprechpartner keine Person
    organization_name: str = ""
    without_person: bool = False
    # weiterer Ansprechpartner derselben Organisation (kein eigener App-Zugang)
    extra_contact: bool = False
    # Familienhaushalt (H1): Nummer, Name, Rolle und Vergleichsschlüssel der Anschrift
    household_id: int | None = None
    household_name: str = ""
    household_role: str = ""
    address_key: str = ""
    # zusammengefasst in das Schreiben an diesen Empfänger (Schlüssel)
    merged_into: str = ""
    # im gemeinsamen Schreiben: alle Personen (Titel, Vorname, Name, Geschlecht)
    household_people: list[tuple[str, str, str, str]] = field(default_factory=list)

    @property
    def channel(self) -> str | None:
        if self.excluded or self.opted_out or self.merged_into:
            return None
        if self.app_access:
            return "app"
        if self.email:
            return "mail"
        return "portal" if self.short else "letter"

    @property
    def note(self) -> str:
        if self.opted_out:
            return NOTE_OPT_OUT
        if self.merged_into:
            return NOTE_MERGED
        if self.app_access:
            return NOTE_APP_MAIL if self.also_mail and self.email else NOTE_APP
        if not self.email:
            return NOTE_PORTAL if self.short else NOTE_LETTER
        return ""


def as_ints(value) -> list[int]:
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def as_int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def years_ago(on: datetime.date, years: int) -> datetime.date:
    try:
        return on.replace(year=on.year - years)
    except ValueError:  # 29. Februar
        return on.replace(year=on.year - years, day=28)


def address_of(first: str, last: str, row: dict, title: str = "") -> str:
    lines = [with_title(title, first, last), row.get("street", "")]
    lines.append(f"{row.get('postal_code', '')} {row.get('city', '')}".strip())
    country = row.get("country", "")
    if country and country.lower() not in ("deutschland", "germany", "de"):
        lines.append(country)
    return "\n".join(line for line in lines if line)


# --- Verein und Abteilung ---


def _current(model, **kwargs):
    on = today()
    return model.objects.filter(valid_from__lte=on, **kwargs).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=on)
    )


def club_base(club: Organization, department=None):
    from members.views import member_queryset

    qs = member_queryset(club).filter(is_current=True, purged_at__isnull=True)
    if department is not None:
        qs = qs.filter(
            Exists(
                _current(
                    DepartmentMembership,
                    membership=OuterRef("pk"),
                    department_id__in=subtree_ids(department),
                )
            )
        )
    return qs


def nobody_selected(filters: dict) -> bool:
    """„Nur ausgewählte“ ohne Auswahl heißt niemand, nie still alle (UI-Audit NMF-06).

    Zählt nur Listen, die in der Auswahl vorkommen; im Abteilungsbereich entfernte
    Angaben (feste eigene Einheit) spielen keine Rolle."""
    selected = filters.get("selected") or []
    if not isinstance(selected, list):
        return False
    return any(isinstance(key, str) and key in filters and not filters.get(key) for key in selected)


def _holders(org: Organization, title_ids: list[int]):
    """Aktuelle Verleihungen dieser Ehrungen an die Person der Mitgliedschaft."""
    from members.honorary import current_awards, visible_orgs

    return current_awards().filter(
        person_id=OuterRef("person_id"),
        title_id__in=title_ids,
        organization_id__in=visible_orgs(org),
    )


def club_filtered(club: Organization, qs, filters: dict):
    """Gefilterte Mitgliedschaften und die Jubiläumsjahre (Mitglied → Jahre)."""
    jubilees: dict[int, int] = {}
    if nobody_selected(filters):
        return qs.none(), jubilees
    types = as_ints(filters.get("member_types"))
    if types:
        qs = qs.filter(current_type_id__in=types)
    depts = as_ints(filters.get("departments"))
    if depts:
        # Mitglieder der gewählten Einheiten und aller Einheiten darunter
        depts = list(with_descendants(club.pk, depts) or depts)
        qs = qs.filter(
            Exists(
                _current(DepartmentMembership, membership=OuterRef("pk"), department_id__in=depts)
            )
        )
    titles = as_ints(filters.get("honorary_titles"))
    if titles:
        qs = qs.filter(Exists(_holders(club, titles)))
    roles = as_ints(filters.get("roles"))
    if roles:
        qs = qs.filter(
            Exists(_current(DepartmentRoleHolder, membership=OuterRef("pk"), role_id__in=roles))
        )
    if filters.get("board"):
        on = today()
        with rls_bypass():
            persons = list(
                RoleAssignment.objects.active(on)
                .filter(organization=club, person__isnull=False, role__is_board=True)
                .values_list("person_id", flat=True)
            )
        qs = qs.filter(person_id__in=persons)
    on = today()
    age_min, age_max = as_int(filters.get("age_min")), as_int(filters.get("age_max"))
    if age_min is not None or age_max is not None:
        # Geburtsdatum verschlüsselt: Alter in Python prüfen
        oldest = years_ago(on, age_max + 1) if age_max is not None else None
        youngest = years_ago(on, age_min) if age_min is not None else None
        any_age = bool(filters.get("organizations_any_age"))
        keep = [
            pk
            for pk, birth, kind in qs.values_list("pk", "person__birth_date", "person__kind")
            if (any_age and kind == "organization")
            or (
                birth is not None
                and (youngest is None or birth <= youngest)
                and (oldest is None or birth > oldest)
            )
        ]
        qs = qs.filter(pk__in=keep)
    year = as_int(filters.get("jubilee_year"))
    if year is not None and 1900 <= year <= 2200:
        rows = jubilees_between(club, datetime.date(year, 1, 1), datetime.date(year, 12, 31))
        for row in rows:
            # Vereinsjubiläum geht vor, sonst das des Dachverbands
            if row["member_id"] not in jubilees or row["kind"] == "club":
                jubilees[row["member_id"]] = row["years"]
        qs = qs.filter(pk__in=list(jubilees))
    return qs, jubilees


def _organization_candidates(m, row: dict, club) -> list[Candidate]:
    """Organisationsmitglied: eine Mail je Ansprechpartner mit „erhält Rundschreiben“;
    ohne solche Adressen ein Empfänger für die Organisation (Mail an ihre Adresse oder
    Brief mit „z. Hd.“ des Hauptansprechpartners). Konzept juristische Personen, J3."""
    from members.models import ContactPerson
    from members.services import contact_for

    person = m.person
    name = person.display_name
    contacts = list(
        ContactPerson.objects.filter(membership=m)
        .select_related("person")
        .order_by("-is_primary", "pk")
    )

    def details(c: ContactPerson) -> tuple[str, str, str, str, str]:
        if c.person_id is not None:
            linked = contact_for(c.person, club)
            email = linked.email if linked else ""
            p = c.person
            return p.first_name, p.last_name, p.gender, p.title, email
        return c.first_name, c.last_name, c.gender, c.title, c.email

    result = []
    for c in contacts:
        if not c.receives_mail:
            continue
        first, last, gender, title, email = details(c)
        if not email.strip():
            continue
        result.append(
            Candidate(
                key=f"m{m.pk}" if not result else f"m{m.pk}-{c.pk}",
                club=club,
                first_name=first,
                last_name=last,
                gender=gender,
                title=title,
                email=email.strip(),
                membership_id=m.pk,
                departments=row.get("departments", []),
                membership=m,
                organization_name=name,
                extra_contact=bool(result),
            )
        )
    if result:
        return result
    primary = next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)
    first, last, gender, title = ("", "", "", "")
    if primary is not None:
        first, last, gender, title, _ = details(primary)
    lines = [name]
    if primary is not None:
        lines.append(f"z. Hd. {with_title(title, first, last)}".strip())
    address = address_of("", "", row)
    return [
        Candidate(
            key=f"m{m.pk}",
            club=club,
            first_name=first,
            last_name=last or name,
            gender=gender,
            title=title,
            email=(row.get("email") or "").strip(),
            address="\n".join([*lines, address]) if address else "\n".join(lines),
            membership_id=m.pk,
            departments=row.get("departments", []),
            membership=m,
            organization_name=name,
            without_person=primary is None,
        )
    ]


def _guardians_by_membership(memberships) -> dict[int, list]:
    """Erziehungsberechtigte mit „erhält Rundschreiben“ der minderjährigen Personen (H4)."""
    from members.guardians import is_minor
    from members.models import ContactPerson

    minors = [m.pk for m in memberships if is_minor(m.person)]
    result: dict[int, list] = {}
    if not minors:
        return result
    for c in (
        ContactPerson.objects.filter(membership_id__in=minors, is_guardian=True, receives_mail=True)
        .select_related("person")
        .order_by("-is_primary", "pk")
    ):
        result.setdefault(c.membership_id, []).append(c)
    return result


def _guardian_candidates(m, row: dict, club, own_email: str, contacts) -> list[Candidate]:
    """Zusätzlich eine Mail an jeden Erziehungsberechtigten mit eigener Adresse."""
    from members.services import contact_for

    result = []
    seen = {own_email.lower()} if own_email else set()
    for c in contacts:
        if c.person_id is not None:
            linked = contact_for(c.person, club)
            first, last = c.person.first_name, c.person.last_name
            gender, title = c.person.gender, c.person.title
            email = (linked.email if linked else "").strip()
        else:
            first, last, gender, title = c.first_name, c.last_name, c.gender, c.title
            email = (c.email or "").strip()
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        result.append(
            Candidate(
                key=f"m{m.pk}-{c.pk}",
                club=club,
                first_name=first,
                last_name=last,
                gender=gender,
                title=title,
                email=email,
                membership_id=m.pk,
                departments=row.get("departments", []),
                membership=m,
                extra_contact=True,
            )
        )
    return result


def _member_candidates(memberships, rows: dict[int, dict], club_of) -> list[Candidate]:
    result = []
    guardians = _guardians_by_membership(memberships)
    for m in memberships:
        row = rows.get(m.pk, {})
        person = m.person
        if person.is_organization:
            result.extend(_organization_candidates(m, row, club_of(m)))
            continue
        home = next((h for h in row.get("households", []) if h["kind"] == "family"), None)
        result.append(
            Candidate(
                key=f"m{m.pk}",
                club=club_of(m),
                first_name=person.first_name,
                last_name=person.last_name,
                gender=person.gender,
                title=person.title,
                email=(row.get("email") or "").strip(),
                address=address_of(person.first_name, person.last_name, row, person.title),
                membership_id=m.pk,
                departments=row.get("departments", []),
                membership=m,
                household_id=home["id"] if home else None,
                household_name=home["name"] if home else "",
                household_role=home["role"] if home else "",
                address_key=address_key(
                    row.get("street", ""), row.get("postal_code", ""), row.get("city", "")
                ),
            )
        )
        if m.pk in guardians:
            result.extend(
                _guardian_candidates(
                    m, row, club_of(m), (row.get("email") or "").strip(), guardians[m.pk]
                )
            )
    return result


EVENT_RESPONSES = ("open", "yes", "no", "maybe")


def event_base(circular: Circular, base, filters: dict):
    """Nur die Eingeladenen des Termins, auf Wunsch nach ihrer Rückmeldung."""
    from events.models import EventResponse
    from events.rsvp import invited

    event = circular.event
    qs = base.filter(pk__in=invited(event, sort=False).values("pk"))
    wanted = [r for r in filters.get("event_responses") or [] if r in EVENT_RESPONSES]
    if wanted:
        answered = EventResponse.objects.filter(event=event, membership=OuterRef("pk"))
        q = Q()
        if "open" in wanted:
            q |= ~Exists(answered)
        statuses = [r for r in wanted if r != "open"]
        if statuses:
            q |= Exists(answered.filter(status__in=statuses))
        qs = qs.filter(q)
    return qs


def club_candidates(circular: Circular) -> tuple[list[Candidate], dict[int, int]]:
    from members.views import member_rows

    club = circular.organization
    filters = dict(circular.filters or {})
    if circular.department_id:
        filters.pop("departments", None)  # im Abteilungsbereich fest die eigene
    base = club_base(club, circular.department)
    if circular.event_id:
        base = event_base(circular, base, filters)
    matched, jubilees = club_filtered(club, base, filters)
    include = {k for k in filters.get("include") or [] if isinstance(k, str)}
    include_ids = [int(k[1:]) for k in include if k.startswith("m") and k[1:].isdigit()]
    qs = base.filter(Q(pk__in=matched.values("pk")) | Q(pk__in=include_ids))
    memberships = list(ordered(qs, limit=MAX_RECIPIENTS))
    rows = {r["id"]: r for r in member_rows(memberships, club, full_names=True)}
    candidates = _member_candidates(memberships, rows, lambda m: club)
    matched_ids = set(
        matched.filter(pk__in=[m.pk for m in memberships]).values_list("pk", flat=True)
    )
    for c in candidates:
        c.included = c.membership_id not in matched_ids
    return candidates, jubilees


def department_role_candidates(circular: Circular) -> list[Candidate]:
    """Verein an die Abteilungen: aktuelle Inhaber von Abteilungsrollen."""
    from members.views import member_rows

    club = circular.organization
    filters = circular.filters or {}
    holders = _current(DepartmentRoleHolder, organization=club).select_related(
        "role", "role__department"
    )
    if nobody_selected(filters):
        holders = holders.none()
    depts = as_ints(filters.get("departments"))
    if depts:
        holders = holders.filter(role__department_id__in=depts)
    names = [n for n in filters.get("role_names") or [] if isinstance(n, str)]
    if names:
        holders = holders.filter(role__name__in=names)
    roles: dict[int, list[str]] = {}
    for h in holders.order_by("role__department__sort_order", "role__department__name"):
        label = f"{h.role.name} ({h.role.department.display_name})"
        roles.setdefault(h.membership_id, []).append(label)
    base = club_base(club)
    memberships = list(ordered(base.filter(pk__in=list(roles))))
    rows = {r["id"]: r for r in member_rows(memberships, club, full_names=True)}
    candidates = _member_candidates(memberships, rows, lambda m: club)
    for c in candidates:
        c.departments = roles.get(c.membership_id, [])
    return candidates


def club_role_candidates(circular: Circular) -> list[Candidate]:
    """Verein an die Inhaber seiner eigenen Rollen (ohne Rollen der Untereinheiten).

    Inhaber sind Benutzerkonten, oft mit Mitgliedsakte: Mit Akte zählt die Akte
    (Brief, Mitgliederbereich); fehlt dort die Mail, geht sie an die Adresse des Kontos.
    """
    from members.views import member_rows

    club = circular.organization
    filters = circular.filters or {}
    if nobody_selected(filters):
        return []
    assignments = (
        RoleAssignment.objects.active(today())
        .filter(organization=club, role__department__isnull=True)
        .select_related("role", "user")
        .order_by("role__position", "role__name")
    )
    wanted = as_ints(filters.get("club_roles"))
    if wanted:
        assignments = assignments.filter(role_id__in=wanted)
    assignments = list(assignments)
    base = club_base(club)
    member_of = dict(
        base.filter(person_id__in={a.person_id for a in assignments if a.person_id}).values_list(
            "person_id", "pk"
        )
    )
    roles: dict[int, list[str]] = {}
    login: dict[int, tuple[int, str]] = {}
    users: dict[int, tuple] = {}
    for a in assignments:
        user = a.user if a.user_id and a.user.is_active else None
        membership_id = member_of.get(a.person_id)
        if membership_id:
            labels = roles.setdefault(membership_id, [])
            if a.role.name not in labels:
                labels.append(a.role.name)
            if user:
                login.setdefault(membership_id, (user.pk, user.email))
        elif user:
            labels = users.setdefault(user.pk, (user, []))[1]
            if a.role.name not in labels:
                labels.append(a.role.name)
    memberships = list(base.filter(pk__in=list(roles)))
    rows = {r["id"]: r for r in member_rows(memberships, club, full_names=True)}
    candidates = _member_candidates(memberships, rows, lambda m: club)
    for c in candidates:
        c.departments = roles.get(c.membership_id, [])
        if c.membership_id in login:
            c.user_id, address = login[c.membership_id]
            c.email = c.email or address
    seen = {c.user_id for c in candidates if c.user_id}
    for user, labels in users.values():
        if user.pk in seen:
            continue
        candidates.append(
            Candidate(
                key=f"u{user.pk}",
                club=club,
                first_name=user.first_name,
                last_name=user.last_name or user.email,
                email=user.email,
                user_id=user.pk,
                departments=labels,
            )
        )
    candidates.sort(key=lambda c: (c.last_name.lower(), c.first_name.lower(), c.key))
    return candidates


# --- Dachverband ---


def federation_member_candidates(circular: Circular) -> list[Candidate]:
    from members.federation_views import federation_queryset, federation_rows

    federation = circular.organization
    filters = circular.filters or {}
    # Vereine auf anderen Instanzen verschicken selbst (Verbund, P10)
    base = (
        federation_queryset(federation)
        .filter(is_current=True, purged_at__isnull=True)
        .exclude(organization__is_remote=True)
    )
    matched = base.none() if nobody_selected(filters) else base
    clubs = as_ints(filters.get("clubs"))
    if clubs:
        matched = matched.filter(organization_id__in=clubs)
    if filters.get("reported"):
        matched = matched.filter(current_type_reported=True)
    titles = as_ints(filters.get("honorary_titles"))
    if titles:
        matched = matched.filter(Exists(_holders(federation, titles)))
    include = [k for k in filters.get("include") or [] if isinstance(k, str)]
    include_ids = [int(k[1:]) for k in include if k.startswith("m") and k[1:].isdigit()]
    qs = base.filter(Q(pk__in=matched.values("pk")) | Q(pk__in=include_ids))
    memberships = list(ordered(qs, limit=MAX_RECIPIENTS))
    rows = {r["id"]: r for r in federation_rows(memberships, full_names=True)}
    candidates = _member_candidates(memberships, rows, lambda m: m.organization)
    matched_ids = set(
        matched.filter(pk__in=[m.pk for m in memberships]).values_list("pk", flat=True)
    )
    for c in candidates:
        c.included = c.membership_id not in matched_ids
    return candidates


def federation_board_candidates(circular: Circular) -> list[Candidate]:
    """Vorstände der Vereine: Inhaber von Vorstandsrollen mit Konto, sonst die
    Kontaktadresse des Vereins."""
    federation = circular.organization
    filters = circular.filters or {}
    clubs = federation.children.filter(type=Organization.Type.CLUB, is_active=True).order_by("name")
    wanted = as_ints(filters.get("clubs"))
    if wanted:
        clubs = clubs.filter(pk__in=wanted)
    if nobody_selected(filters):
        clubs = clubs.none()
    result: list[Candidate] = []
    on = today()
    with rls_bypass():
        for club in clubs:
            seen: set[int] = set()
            assignments = (
                RoleAssignment.objects.active(on)
                .filter(organization=club, role__is_board=True, user__isnull=False)
                .select_related("user")
                .order_by("user__last_name", "user__first_name")
            )
            for a in assignments:
                if a.user_id in seen or not a.user.is_active:
                    continue
                seen.add(a.user_id)
                result.append(
                    Candidate(
                        key=f"u{a.user_id}-c{club.pk}",
                        club=club,
                        first_name=a.user.first_name,
                        last_name=a.user.last_name or a.user.email,
                        email=a.user.email,
                        user_id=a.user_id,
                    )
                )
            if not seen:
                lines = [
                    club.name,
                    club.address_extra,
                    club.street,
                    f"{club.postal_code} {club.city}".strip(),
                ]
                result.append(
                    Candidate(
                        key=f"c{club.pk}",
                        club=club,
                        first_name="",
                        last_name=club.name,
                        email=club.contact_email,
                        address="\n".join(line for line in lines if line),
                    )
                )
    return result


# --- Gesamt ---


@dataclass
class Selection:
    candidates: list[Candidate]
    jubilees: dict[int, int] = field(default_factory=dict)

    @property
    def chosen(self) -> list[Candidate]:
        return [c for c in self.candidates if c.channel]

    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.candidates),
            "app": sum(1 for c in self.candidates if c.channel == "app"),
            "mail": sum(1 for c in self.candidates if c.channel == "mail"),
            "letter": sum(1 for c in self.candidates if c.channel == "letter"),
            "portal": sum(1 for c in self.candidates if c.channel == "portal"),
            "opted_out": sum(1 for c in self.candidates if c.opted_out and not c.excluded),
            "excluded": sum(1 for c in self.candidates if c.excluded),
            # in ein gemeinsames Schreiben an den Haushalt aufgenommen (H1)
            "merged": sum(
                1 for c in self.candidates if c.merged_into and not c.excluded and not c.opted_out
            ),
        }


def select(circular: Circular) -> Selection:
    org = circular.organization
    jubilees: dict[int, int] = {}
    if org.type == Organization.Type.FEDERATION:
        if circular.audience == Circular.Audience.BOARDS:
            candidates = federation_board_candidates(circular)
        else:
            candidates = federation_member_candidates(circular)
    elif circular.audience == Circular.Audience.DEPARTMENTS:
        candidates = department_role_candidates(circular)
    elif circular.audience == Circular.Audience.ROLES:
        candidates = club_role_candidates(circular)
    else:
        candidates, jubilees = club_candidates(circular)
    exclude = {k for k in (circular.filters or {}).get("exclude") or [] if isinstance(k, str)}
    # Abmelden können sich Mitglieder nur von Informationen an die Mitglieder,
    # nicht von Post an Vorstände und Rolleninhaber
    info = circular.kind == Circular.Kind.INFO and circular.audience == Circular.Audience.MEMBERS
    opted = set()
    if info:
        ids = [c.membership_id for c in candidates if c.membership_id]
        with rls_bypass():
            opted = set(
                Membership.objects.filter(pk__in=ids, info_opt_out_at__isnull=False).values_list(
                    "pk", flat=True
                )
            )
    for c in candidates:
        c.excluded = c.key in exclude
        # Abgemeldet: keine Mail und auch kein Brief für Informationen
        c.opted_out = info and c.membership_id in opted
        c.short = circular.kind == Circular.Kind.SHORT
    if circular.via_app:
        from devices.push import app_accesses

        accesses = app_accesses({c.membership_id for c in candidates if c.membership_id})
        for c in candidates:
            c.app_access = (
                accesses.get(c.membership_id) if c.membership_id and not c.extra_contact else None
            )
            c.also_mail = circular.also_mail
    if merging_households(circular):
        merge_households(candidates)
    return Selection(candidates, jubilees)


# Platzhalter mit Werten je Person: Schreiben dann nicht zusammenfassen
PERSONAL_PLACEHOLDERS = {"Mitgliedsjahre", "Jubiläumsjahre"}


def merging_households(circular: Circular) -> bool:
    """Schreiben je Familienhaushalt zusammenfassen? Nur an Mitglieder eines Vereins,
    nicht zu einem Termin (Rückmeldelinks je Person) und nicht mit Platzhaltern, die
    je Person verschieden sind."""
    from .services import used_placeholders

    if circular.organization.type != Organization.Type.CLUB:
        return False
    if circular.audience != Circular.Audience.MEMBERS or circular.event_id:
        return False
    if (circular.filters or {}).get("households_merge") is False:
        return False
    return not (used_placeholders(circular) & PERSONAL_PLACEHOLDERS)


ROLE_ORDER = {"adult": 0, "": 1, "child": 2}


def merge_households(candidates: list[Candidate]) -> None:
    """Briefe an denselben Familienhaushalt mit gleicher Anschrift und Mails an dieselbe
    Adresse im selben Haushalt werden ein Schreiben an den ersten Erwachsenen. Wer anders
    wohnt oder eine eigene Adresse hat, bekommt sein eigenes."""
    groups: dict[tuple, list[Candidate]] = {}
    for c in candidates:
        if not c.household_id or c.organization_name or c.extra_contact:
            continue
        channel = c.channel
        if channel == "letter" and c.address_key:
            key = (c.household_id, "letter", c.address_key)
        elif channel == "mail" and c.email:
            key = (c.household_id, "mail", c.email.lower())
        else:
            continue
        groups.setdefault(key, []).append(c)
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda c: ROLE_ORDER.get(c.household_role, 1))
        lead = members[0]
        lead.household_people = [(c.title, c.first_name, c.last_name, c.gender) for c in members]
        if key[1] == "letter":
            lines = lead.address.split("\n")
            lead.address = "\n".join([letter_name(lead.household_people), *lines[1:]])
        for c in members[1:]:
            c.merged_into = lead.key


def formal_salutation(c: Candidate) -> str:
    """„Sehr geehrter Herr Dr. Muster“; ohne Geschlecht „Guten Tag Dr. Max Muster“."""
    if c.household_people:
        return f"Sehr geehrte Familie {family_last_name(c.household_people)}"
    if c.without_person:
        return "Sehr geehrte Damen und Herren"
    if c.gender == Gender.MALE:
        return f"Sehr geehrter Herr {with_title(c.title, '', c.last_name)}"
    if c.gender == Gender.FEMALE:
        return f"Sehr geehrte Frau {with_title(c.title, '', c.last_name)}"
    return f"Guten Tag {with_title(c.title, c.first_name, c.last_name)}"


def informal_salutation(c: Candidate) -> str:
    """„Lieber Max“ / „Liebe Maria“; ohne Angabe „Hallo Max“."""
    if c.household_people:
        return f"Liebe Familie {family_last_name(c.household_people)}"
    if c.without_person:
        return "Hallo zusammen"
    name = c.first_name or c.last_name
    if c.gender == Gender.MALE:
        return f"Lieber {name}"
    if c.gender == Gender.FEMALE:
        return f"Liebe {name}"
    return f"Hallo {name}"


def fill_values(circular: Circular, selection: Selection, used: set[str]) -> None:
    """Werte der Platzhalter je Empfänger (aufwendige nur, wenn sie vorkommen)."""
    on = today()
    years: dict[int, int] = {}
    if "Mitgliedsjahre" in used:
        ids = [c.membership_id for c in selection.chosen if c.membership_id]
        with rls_bypass():
            for m in (
                Membership.objects.filter(pk__in=ids)
                .select_related("organization")
                .prefetch_related("periods", "type_assignments__member_type")
            ):
                years[m.pk] = Duration.of(club_ranges(m), on, m.organization.date_precision).years
    dept_name = circular.department.name if circular.department_id else ""
    for c in selection.candidates:
        c.values = {
            "Vorname": (
                and_join([p[1] for p in c.household_people if p[1]])
                if c.household_people
                else c.first_name
            ),
            "Nachname": c.last_name,
            "Anrede": formal_salutation(c),
            "Anrede Du": informal_salutation(c),
            "Abteilung": dept_name or ", ".join(c.departments),
            "Verein": c.club.name,
            "Organisation": c.organization_name,
            "Haushalt": c.household_name,
            "Mitgliedsjahre": str(years[c.membership_id]) if c.membership_id in years else "",
            "Jubiläumsjahre": (
                str(selection.jubilees[c.membership_id])
                if c.membership_id in selection.jubilees
                else ""
            ),
        }
