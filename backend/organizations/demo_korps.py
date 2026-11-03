"""Zusätzlicher Demoverein für den Testserver: Schützenverein mit Korps (alles erfunden).

Aufbau: Verein → Korps → Züge (das Tambourkorps ohne Züge). Alle schaltbaren Module und
Zusatzfunktionen sind an. Angelegt werden Mitglieder, Ämter in Verein, Korps und Zügen,
Zugänge, Kasse, Beiträge, Satzung, Dokumente, Termine, Würden, Wettbewerbe, Meldungen,
Rundschreiben-Entwurf, Webseite mit Chronik, Impressum und Briefbogen.

Wiederholbar: Vorhandenes bleibt, wie es ist. Andere Organisationen (z. B. die
Pilotorganisationen aus ``seed_testdata``) fasst der Befehl nicht an.
"""

from __future__ import annotations

import datetime
import random
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from access.catalog import (
    AUDIT_VIEW,
    BILLING_EDIT,
    BILLING_VIEW,
    CIRCULARS_SEND,
    DEPT_CIRCULARS_SEND,
    DEPT_DOCS_MANAGE,
    DEPT_ENTRIES_SUBMIT,
    DEPT_EVENTS_MANAGE,
    DEPT_EXPORT,
    DEPT_INVOICES_VIEW,
    DEPT_MEMBERS_EDIT,
    DEPT_MEMBERS_VIEW,
    DOCS_MANAGE,
    DOCS_VIEW,
    EVENTS_MANAGE,
    EXPORT_RUN,
    FINANCE_EDIT,
    FINANCE_VIEW,
    MEMBERS_EDIT,
    MEMBERS_VIEW,
    SWITCHABLE_MODULES,
    codes_for,
)
from access.models import Role, RoleAssignment
from accounts.models import User
from members import services as member_services
from members.models import DepartmentRoleHolder, ExitReason, Gender, Membership, MemberType

from .models import Department, DepartmentRole, Organization, SocialLink

CLUB_NAME = "Schützenverein Musterstadt 1823 e.V."
SLUG = "sv-musterstadt"
DOMAIN = f"{SLUG}.test"
WEB_DOMAIN = f"www.{DOMAIN}"
POSTAL_CODE, CITY = "12345", "Musterstadt"

CLUB = {
    "short_name": "SV Musterstadt",
    "founding_year": 1823,
    "street": "Am Schützenplatz 3",
    "postal_code": POSTAL_CODE,
    "city": CITY,
    "contact_email": f"vorstand@{DOMAIN}",
    "primary_color": "#14365d",
    "accent_color": "#c8a13a",
    "department_label": "Korps",
    "department_label_plural": "Korps",
    "department_label_gender": "n",
    "department_label_genitive": "des Korps",
    "department_label_en": "Corps",
    "department_label_plural_en": "Corps",
    "allow_multiple_departments": False,
    # Alle Zusatzfunktionen an
    "member_portal_enabled": True,
    "department_access_enabled": True,
    "tax_areas_enabled": True,
    "cash_counts_enabled": True,
    "reserves_enabled": True,
    "datev_enabled": True,
    "datev_consultant": "1234567",
    "datev_client": "12345",
}

# Korps mit Gründungsjahr und Zügen (alle Namen erfunden); ohne Züge: Mitglieder direkt im Korps
KORPS = [
    (
        "Grenadierkorps",
        "Gren",
        1823,
        ["Grenadierzug Eichenlaub", "Grenadierzug Treue Kameraden", "Grenadierzug Frohsinn"],
    ),
    (
        "Jägerkorps",
        "Jäger",
        1850,
        [
            "Jägerzug Grünröcke",
            "Jägerzug Waldeslust",
            "Jägerzug Hörnerklang",
            "Jägerzug Edelweiß",
        ],
    ),
    ("Schützenlust", "Lust", 1902, ["Zug Fröhliche Runde", "Zug Gut Schuss"]),
    ("Artilleriekorps", "Art", 1927, ["Batterie Donnerhall", "Batterie Pulverdampf"]),
    ("Reiterkorps", "Reiter", 1955, ["Reiterzug Steigbügel", "Reiterzug Hufeisen"]),
    ("Scheibenschützen", "Scheibe", 1978, ["Zug Ins Schwarze", "Zug Zehner"]),
    ("Tambourkorps Musterstadt", "Tambour", 1888, []),
]
KORPS_ROLES = [
    # (Name, Rechte im Korps)
    (
        "Major",
        [
            DEPT_MEMBERS_VIEW,
            DEPT_MEMBERS_EDIT,
            DEPT_EXPORT,
            DEPT_INVOICES_VIEW,
            DEPT_EVENTS_MANAGE,
            DEPT_DOCS_MANAGE,
            DEPT_CIRCULARS_SEND,
            DEPT_ENTRIES_SUBMIT,
        ],
    ),
    ("Adjutant", [DEPT_MEMBERS_VIEW, DEPT_EVENTS_MANAGE, DEPT_ENTRIES_SUBMIT]),
    ("Fahnenträger", []),
]
ZUG_ROLES = ["Oberleutnant", "Leutnant", "Spieß", "Kassierer"]

CLUB_ROLES = {
    "Vorstand": None,  # alle Rechte
    "Kassierer": [MEMBERS_VIEW, EXPORT_RUN, FINANCE_VIEW, FINANCE_EDIT, BILLING_VIEW, BILLING_EDIT],
    "Schriftführer": [
        MEMBERS_VIEW,
        MEMBERS_EDIT,
        AUDIT_VIEW,
        EVENTS_MANAGE,
        DOCS_VIEW,
        DOCS_MANAGE,
        CIRCULARS_SEND,
    ],
}
# Ämter für Webseite und Chronik (ohne Rechte)
BOARD_POSITIONS = ["Präsident", "Vizepräsident", "Oberst", "Geschäftsführer", "Schatzmeister"]

TYPES = [
    # (Name, gemeldet, aktiv, zählt für Dauer, Jahresbeitrag)
    ("aktiv", True, True, True, "60.00"),
    ("passiv", True, False, True, "30.00"),
    ("Ehrenmitglied", True, False, True, "0.00"),
    ("Jungschütze", True, True, True, "20.00"),
]

FIRST_M = [
    "Albert", "Bruno", "Carsten", "Dennis", "Emil", "Felix", "Gregor", "Hannes", "Ingo",
    "Jakob", "Kurt", "Ludwig", "Malte", "Nils", "Oskar", "Paul", "Robert", "Sven", "Timo",
    "Ulrich", "Viktor", "Walter", "Yannick",
]  # fmt: skip
FIRST_F = [
    "Anke", "Britta", "Carla", "Dana", "Eva", "Frieda", "Greta", "Hanna", "Ida", "Julia",
    "Klara", "Luise", "Mia", "Nora", "Paula", "Rita", "Svenja", "Theresa",
]  # fmt: skip
LAST = [
    "Musterfeld", "Beispielhoff", "Probst-Erfunden", "Testermann", "Ausdenk", "Annahmer",
    "Platzhalter-Berg", "Fiktiwski", "Vorlagenberg", "Entwurfner", "Schablonenkamp",
    "Modellhaus", "Exemplarius", "Simulanski", "Musterkötter", "Probandt", "Skizzenbach",
    "Erdachtberg", "Ausgedachtler", "Pseudonymer",
]  # fmt: skip
STREETS = ["Schützenstraße", "Am Marktplatz", "Lindenallee", "Mühlenweg", "Kirchstraße", "Am Bach"]

USERS = [
    # (E-Mail, Vorname, Nachname, Vereinsrolle)
    (f"vorstand@{DOMAIN}", "Vera", "Vorstand", "Vorstand"),
    (f"kasse@{DOMAIN}", "Karl", "Kassenprüfer", "Kassierer"),
    (f"schriftfuehrer@{DOMAIN}", "Sonja", "Schreiber", "Schriftführer"),
]
# Zugänge über den Mitgliederbereich (Inhaber von Korpsämtern und ein einfaches Mitglied)
MAJOR_EMAIL = f"major.jaeger@{DOMAIN}"
MEMBER_EMAIL = f"mitglied@{DOMAIN}"


def all_emails() -> list[str]:
    return [u[0] for u in USERS] + [MAJOR_EMAIL, MEMBER_EMAIL]


def seed(password: str, reset: bool = False) -> dict:
    """Legt den Demoverein an. Zurück: {"club": …, "created": Anzahl neuer Zugänge}."""
    rnd = random.Random(1823)  # noqa: S311 – nur Testdaten
    club = _organization()
    korps = _units(club)
    _roles(club)
    types = _member_types(club)
    _members(club, korps, types, rnd)
    created = _users(club, password, reset)
    _unit_roles(club)
    _portal(club, password, reset, created)
    _fields(club, rnd)
    orgs = {"club": club}
    _finance(club)
    from finance.seed import seed_projects

    seed_projects(orgs)
    _billing(club, types)
    _statutes(club)
    _documents(club)
    _events(club)
    _honors(club)
    _competitions(club)
    _entries(club)
    _circulars(club)
    _imprint(club)
    _letterhead(club)
    _website(club)
    return {"club": club, "created": created["count"]}


# --- Aufbau ---


def _organization() -> Organization:
    platform = Organization.platform()
    club, created = Organization.objects.get_or_create(
        type=Organization.Type.CLUB,
        name=CLUB_NAME,
        defaults={**CLUB, "parent": platform, "enabled_modules": list(SWITCHABLE_MODULES)},
    )
    if not created and not set(SWITCHABLE_MODULES) <= set(club.enabled_modules or []):
        club.enabled_modules = sorted({*(club.enabled_modules or []), *SWITCHABLE_MODULES})
        club.save(update_fields=["enabled_modules"])
    return club


def _units(club) -> dict[str, Department]:
    korps = {}
    for order, (name, short, year, zuege) in enumerate(KORPS, start=1):
        unit, created = Department.objects.get_or_create(
            organization=club,
            parent=club,
            name=name,
            defaults={
                "short_name": short,
                "founding_year": year,
                "sort_order": order,
                "self_managed": True,
                "department_label": "Zug",
                "department_label_plural": "Züge",
                "department_label_gender": "m",
                "department_label_en": "Platoon",
                "department_label_plural_en": "Platoons",
            },
        )
        korps[name] = unit
        for position, (role, perms) in enumerate(KORPS_ROLES, start=1):
            DepartmentRole.objects.get_or_create(
                organization=club,
                department=unit,
                name=role,
                defaults={"position": position, "permissions": perms},
            )
        for z_order, zug_name in enumerate(zuege, start=1):
            zug, _ = Department.objects.get_or_create(
                organization=club,
                parent=unit,
                name=zug_name,
                defaults={
                    "founding_year": year + 10 * z_order,
                    "sort_order": z_order,
                    "label": "Zug",
                    "label_en": "Platoon",
                    "label_plural_en": "Platoons",
                },
            )
            for position, role in enumerate(ZUG_ROLES, start=1):
                DepartmentRole.objects.get_or_create(
                    organization=club, department=zug, name=role, defaults={"position": position}
                )
    return korps


def _roles(club) -> None:
    for name, perms in CLUB_ROLES.items():
        perms = codes_for("club") if perms is None else perms
        Role.objects.get_or_create(
            organization=club,
            name=name,
            defaults={"permissions": perms, "represents": name == "Vorstand"},
        )


def _member_types(club) -> list[MemberType]:
    types = []
    for order, (name, reported, active, counts, _fee) in enumerate(TYPES):
        obj, _ = MemberType.objects.get_or_create(
            organization=club,
            name=name,
            defaults={
                "reported": reported,
                "active": active,
                "counts_for_duration": counts,
                "sort_order": order,
            },
        )
        types.append(obj)
    return types


def _leaves(club) -> list[Department]:
    """Einheiten, in die Mitglieder kommen: Züge, bei Korps ohne Züge das Korps."""
    units = list(Department.objects.filter(organization=club).order_by("pk"))
    parents = {u.parent_id for u in units}
    return [u for u in units if u.pk not in parents]


def _members(club, korps, types, rnd) -> None:
    if Membership.objects.filter(organization=club).exists():
        return
    number = 2000
    for unit in _leaves(club):
        size = (18, 30) if unit.parent_id == club.pk else (7, 14)
        for _ in range(rnd.randint(*size)):
            number += 1
            _admit(club, unit, types, rnd, number)
    for _ in range(15):
        number += 1
        _admit(club, None, types[1:3], rnd, number)


def _admit(club, unit, types, rnd, number) -> Membership | None:
    female = rnd.random() < 0.3
    first = rnd.choice(FIRST_F if female else FIRST_M)
    last = rnd.choice(LAST)
    birth = datetime.date(rnd.randint(1944, 2010), rnd.randint(1, 12), rnd.randint(1, 28))
    entry = datetime.date(rnd.randint(max(1965, birth.year + 14), 2025), rnd.randint(1, 12), 1)
    if unit is not None:
        young = birth.year >= 2005
        member_type = types[3] if young else (types[0] if rnd.random() < 0.8 else types[1])
    else:
        member_type = rnd.choice(types)
    slug = last.lower().replace("ö", "oe").replace("-", "")
    try:
        membership = member_services.admit(
            club,
            {
                "last_name": last,
                "first_name": first,
                "birth_date": birth,
                "gender": Gender.FEMALE if female else Gender.MALE,
                "member_type": member_type,
                "entry_date": entry,
                "club_number": str(number),
                "email": f"{first.lower()}.{slug}{number}@{DOMAIN}",
                "phone": f"01234 {rnd.randint(100000, 999999)}" if rnd.random() < 0.6 else "",
                "street": f"{rnd.choice(STREETS)} {rnd.randint(1, 80)}",
                "postal_code": POSTAL_CODE,
                "city": CITY,
                "departments": [unit] if unit else [],
            },
        )
    except Exception:  # noqa: BLE001 – Zufallsdaten: Konflikte überspringen
        return None
    # Etwa jedes fünfzehnte Mitglied ist schon ausgetreten (Archiv)
    if rnd.random() < 1 / 15:
        period = membership.periods.first()
        exit_date = min(
            entry + datetime.timedelta(days=rnd.randint(400, 6000)), datetime.date(2025, 12, 31)
        )
        if exit_date > period.entry_date:
            period.exit_date = exit_date
            period.exit_reason = rnd.choice([ExitReason.EXIT, ExitReason.STRIKE_OFF])
            period.save()
            membership.type_assignments.update(valid_until=exit_date)
            membership.department_memberships.update(valid_until=exit_date)
    return membership


def _current(club, unit=None) -> list[Membership]:
    qs = Membership.objects.filter(organization=club, purged_at__isnull=True)
    if unit is not None:
        units = [unit.pk, *Department.objects.filter(parent=unit).values_list("pk", flat=True)]
        qs = qs.filter(
            department_memberships__department__in=units,
            department_memberships__valid_until__isnull=True,
        )
    return [m for m in qs.select_related("person").order_by("pk").distinct() if m.current_period()]


def _users(club, password: str, reset: bool) -> dict:
    count = 0
    first_unit = Department.objects.get(organization=club, name="Grenadierzug Eichenlaub")
    for email, first, last, role_name in USERS:
        user, created = User.objects.get_or_create(
            email=email, defaults={"first_name": first, "last_name": last}
        )
        if created or reset:
            user.set_password(password)
            user.save()
            count += int(created)
        role = Role.objects.get(organization=club, name=role_name)
        assignment, _ = RoleAssignment.objects.get_or_create(
            organization=club, role=role, user=user, defaults={"valid_from": "2020-01-01"}
        )
        if assignment.person_id:
            continue
        # Zugänge des Vorstands haben auch eine Mitgliedsakte
        membership = member_services.admit(
            club,
            {
                "last_name": last,
                "first_name": first,
                "birth_date": datetime.date(1970 + len(role_name), 3, 14),
                "member_type": MemberType.objects.get(organization=club, name="aktiv"),
                "entry_date": datetime.date(1990, 5, 1),
                "email": email,
                "street": "Am Schützenplatz 3",
                "postal_code": POSTAL_CODE,
                "city": CITY,
                "departments": [first_unit],
            },
        )
        assignment.person = membership.person
        assignment.save()
        if role_name == "Vorstand" and club.contact_source != Organization.ContactSource.ROLE:
            club.contact_source = Organization.ContactSource.ROLE
            club.contact_role = role
            club.save()
    return {"count": count}


def _unit_roles(club) -> None:
    """Ämter in Korps und Zügen besetzen (wiederholbar, besetzte bleiben)."""
    on = datetime.date.today()
    taken: set[int] = set(
        DepartmentRoleHolder.objects.filter(organization=club).values_list(
            "membership_id", flat=True
        )
    )
    for index, unit in enumerate(Department.objects.filter(organization=club).order_by("pk")):
        members = [m for m in _current(club, unit) if m.pk not in taken]
        for role in DepartmentRole.objects.filter(department=unit).order_by("position"):
            if (
                role.holders.filter(valid_from__lte=on)
                .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=on))
                .exists()
            ):
                continue
            if role.name == "Kassierer" and index % 3 == 0:
                continue  # bleibt in manchen Zügen frei
            holder = next((m for m in members if m.pk not in taken), None)
            if holder is None:
                continue
            taken.add(holder.pk)
            DepartmentRoleHolder.objects.create(
                organization=club,
                membership=holder,
                role=role,
                valid_from=max(holder.current_period().entry_date, datetime.date(2016, 1, 1)),
            )
    # Majore und Oberleutnants erscheinen auf der Webseite
    DepartmentRole.objects.filter(organization=club, name__in=["Major", "Oberleutnant"]).update(
        on_website=True
    )


def _portal(club, password: str, reset: bool, created: dict) -> None:
    """Zugang für den Major des Jägerkorps und für ein einfaches Mitglied."""
    from portal.models import PortalAccess

    jaeger = Department.objects.get(organization=club, name="Jägerkorps")
    major = DepartmentRoleHolder.objects.filter(role__department=jaeger, role__name="Major").first()
    simple = next(
        (
            m
            for m in _current(
                club, Department.objects.get(organization=club, name="Zug Gut Schuss")
            )
            if not DepartmentRoleHolder.objects.filter(membership=m).exists()
        ),
        None,
    )
    for email, membership in ((MAJOR_EMAIL, major and major.membership), (MEMBER_EMAIL, simple)):
        if membership is None or PortalAccess.objects.filter(membership=membership).exists():
            continue
        if PortalAccess.objects.filter(user__email=email).exists():
            continue
        person = membership.person
        user, new = User.objects.get_or_create(
            email=email, defaults={"first_name": person.first_name, "last_name": person.last_name}
        )
        if new or reset:
            user.set_password(password)
            user.save()
            created["count"] += int(new)
        PortalAccess.objects.create(organization=club, membership=membership, user=user)


def _fields(club, rnd) -> None:
    from customfields.models import FieldDefinition, FieldValue

    awards, _ = FieldDefinition.objects.get_or_create(
        organization=club,
        key="auszeichnung",
        defaults={
            "label": "Auszeichnung",
            "repeatable": True,
            "subfields": [
                {"key": "bezeichnung", "label": "Bezeichnung", "type": "text", "choices": []},
                {"key": "datum", "label": "Datum", "type": "date", "choices": []},
            ],
        },
    )
    FieldDefinition.objects.get_or_create(
        organization=club,
        key="uniformgroesse",
        defaults={
            "label": "Uniformgröße",
            "field_type": "choice",
            "choices": ["46", "48", "50", "52", "54", "56", "58"],
        },
    )
    if FieldValue.objects.filter(definition=awards).exists():
        return
    current = _current(club)
    for m in rnd.sample(current, min(30, len(current))):
        FieldValue.objects.create(
            organization=club,
            definition=awards,
            person=m.person,
            value=[
                {
                    "bezeichnung": rnd.choice(["Verdienstorden", "Korpsorden", "Treuenadel"]),
                    "datum": f"{rnd.randint(1995, 2025)}-07-{rnd.randint(10, 28)}",
                }
            ],
        )


# --- Kasse und Beiträge ---


def _finance(club) -> None:
    from finance import seed as fs

    rename = {
        "Musik und Fanfaren-Corps": "Musik und Tambourkorps",
        "Notenmaterial Fanfaren-Corps": "Notenmaterial Tambourkorps",
        "Reparatur Fanfaren": "Reparatur Trommeln",
        "Zugzuschüsse": "Zuschüsse Korps und Züge",
    }
    units = {
        "Hubertus Fanfaren-Corps": "Tambourkorps Musterstadt",
        "Herolde": "Grenadierkorps",
        "Dicke Fründe": "Jägerkorps",
        "Jot drop": "Reiterkorps",
    }
    categories = [
        (rename.get(name, name), kind, area)
        for name, kind, area in fs.CLUB_CATEGORIES
        if name != "Verbandsbeitrag"
    ]
    plan = []
    for entry in fs._club_plan(random.Random(1823)):  # noqa: S311 – nur Testdaten
        if entry["text"].startswith("Verbandsbeitrag"):
            continue
        entry = {**entry}
        entry["text"] = rename.get(entry["text"], entry["text"])
        if "category" in entry:
            entry["category"] = rename.get(entry["category"], entry["category"])
        if entry.get("department"):
            dept = units.get(entry["department"], entry["department"])
            entry["text"] = entry["text"].replace(entry["department"], dept)
            entry["department"] = dept
        entry.setdefault("partner", fs.DEMO_PARTNERS.get(entry["text"], ""))
        plan.append(entry)
    fs._seed_org(
        club, fs.CLUB_ACCOUNTS, categories, plan, timezone.localdate(), "Musterbank (erfunden)"
    )


def _billing(club, types) -> None:
    from billing.models import FeeRate
    from billing.services import settings_for
    from finance.models import Account, Category

    settings = settings_for(club)
    if not settings.creditor_id:
        settings.account = Account.objects.filter(organization=club, name="Girokonto").first()
        settings.category = Category.objects.filter(
            organization=club, name="Mitgliedsbeiträge"
        ).first()
        settings.sepa_enabled = True
        # Gläubiger-ID aus den Beispielen der Bundesbank (keine echte)
        settings.creditor_id = "DE98ZZZ09999999999"
        settings.save()
    for member_type, (_n, _r, _a, _c, fee) in zip(types, TYPES, strict=True):
        FeeRate.objects.get_or_create(
            organization=club, member_type=member_type, defaults={"amount": Decimal(fee)}
        )


# --- Satzung und Dokumente ---


def _statutes(club) -> None:
    from statutes.models import Kind, StatutePublication, StatuteVersion
    from statutes.seed import demo_pdf

    if StatuteVersion.objects.filter(
        organization=club, department=None, kind=Kind.STATUTE
    ).exists():
        return
    for valid_from, note in (
        (datetime.date(2001, 3, 9), "Neufassung"),
        (datetime.date(2022, 2, 18), "Änderung § 5 (Korps und Züge)"),
    ):
        label = f"Fassung vom {valid_from:%d.%m.%Y} ({note})"
        content = demo_pdf(club.name, label)
        version = StatuteVersion(
            organization=club,
            valid_from=valid_from,
            note=note,
            name=f"Satzung-{valid_from:%Y-%m-%d}.pdf",
            size=len(content),
        )
        version.file.save(version.name, ContentFile(content), save=False)
        version.save()
    StatutePublication.objects.get_or_create(
        organization=club,
        department=None,
        kind=Kind.STATUTE,
        defaults={"is_public": True, "public_key": StatutePublication.new_key()},
    )


def _documents(club) -> None:
    from documents.models import Document, DocumentVersion, Folder
    from documents.seed import demo_pdf

    if Folder.objects.filter(organization=club).exists():
        return
    year = timezone.localdate().year
    v = Folder.Visibility
    plan = [
        (
            "Protokolle",
            v.BOARD,
            [
                ("Protokoll Generalversammlung", f"{year}-03-06"),
                ("Protokoll Sitzung der Korpsführer", f"{year}-05-12"),
            ],
        ),
        (
            "Festordnung",
            v.MEMBERS,
            [("Aufstellung Festzug", f"{year}-07-01"), ("Antreteplan Parade", f"{year}-07-01")],
        ),
        ("Aufnahme", v.PUBLIC, [("Aufnahmeantrag", "2024-01-15")]),
    ]
    for name, visibility, docs in plan:
        folder = Folder.objects.create(
            organization=club, name=name, visibility=visibility, public_key=Folder.new_key()
        )
        for title, day in docs:
            doc = Document.objects.create(
                organization=club, folder=folder, title=title, date=datetime.date.fromisoformat(day)
            )
            content = demo_pdf(title, club.name)
            version = DocumentVersion(
                organization=club,
                document=doc,
                name=f"{title.replace(' ', '-')}.pdf",
                size=len(content),
                content_type="application/pdf",
            )
            version.file.save(version.name, ContentFile(content), save=False)
            version.save()


# --- Termine ---


def _events(club) -> None:
    from events.models import Event
    from events.seed import _at, _cat, _event, _next
    from events.services import ensure_categories

    ensure_categories(club)
    if Event.objects.filter(organization=club).exists():
        return
    year = timezone.localdate().year
    d = datetime.date
    fest = _next(7, 11)
    _event(
        club,
        "Schützenfest",
        _at(fest),
        _at(fest + datetime.timedelta(days=3)),
        all_day=True,
        visibility="public",
        location="Festplatz Musterstadt",
        category=_cat(club, "Fest"),
        description="Schützenfest mit Parade aller Korps, Königsehrung und Festball.",
    )
    _event(
        club,
        "Generalversammlung",
        _at(_next(3, 6), 19),
        _at(_next(3, 6), 22),
        visibility="members",
        location="Schützenhaus",
        address=f"Am Schützenplatz 3, {POSTAL_CODE} {CITY}",
        category=_cat(club, "Versammlung"),
        rsvp_enabled=True,
        remind_days=2,
    )
    _event(
        club,
        "Königsschießen",
        _at(_next(6, 20), 14),
        _at(_next(6, 20), 19),
        visibility="public",
        location="Schießstand am Schützenhaus",
        category=_cat(club, "Schießen"),
        rsvp_enabled=True,
        rsvp_guests=True,
    )
    _event(
        club,
        "Sitzung der Korpsführer",
        _at(d(year, 1, 8), 19, 30),
        _at(d(year, 1, 8), 21, 30),
        visibility="board",
        repeat="monthly",
        category=_cat(club, "Versammlung"),
    )
    _event(
        club,
        "Biwak",
        _at(_next(5, 23), 11),
        _at(_next(5, 23), 18),
        visibility="public",
        location="Festwiese",
        category=_cat(club, "Geselliges"),
    )
    for i, unit in enumerate(
        Department.objects.filter(organization=club, parent=club).order_by("sort_order")
    ):
        _event(
            club,
            f"Korpsversammlung {unit.name}",
            _at(d(year, 2, 2 + i * 3), 20),
            _at(d(year, 2, 2 + i * 3), 22),
            department=unit,
            visibility="members",
            category=_cat(club, "Versammlung"),
        )
    for zug in Department.objects.filter(organization=club, name__startswith="Jägerzug")[:2]:
        _event(
            club,
            "Zugabend",
            _at(d(year, 1, 20), 20),
            _at(d(year, 1, 20), 23),
            department=zug,
            visibility="members",
            repeat="monthly",
            category=_cat(club, "Geselliges"),
        )
    _event(
        club,
        "Übungsabend Tambourkorps",
        _at(_next(1, 14), 19),
        _at(_next(1, 14), 21),
        department=Department.objects.get(organization=club, name="Tambourkorps Musterstadt"),
        visibility="members",
        repeat="weekly",
        category=_cat(club, "Geselliges"),
    )


# --- Würden ---

OLD_KINGS = [
    "Gustav Vorjahr", "Ernst Einstmals", "Alfons Damalig", "Hubert Längstvergangen",
    "Wilhelm Vormalig", "Konrad Ehedem", "Fritz Seinerzeit", "Anton Früherer",
]  # fmt: skip
QUEENS = ["Margot", "Irmgard", "Liesel", "Gisela", "Erna", "Ursula", "Hedwig", "Christa"]


def _honors(club) -> None:
    from honors.models import Companion, Dignity, Reign

    if Dignity.objects.filter(organization=club).exists():
        return
    king = Dignity.objects.create(organization=club, name="Schützenkönig", sort_order=1)
    youth = Dignity.objects.create(organization=club, name="Jungschützenkönig", sort_order=2)
    pupil = Dignity.objects.create(organization=club, name="Schülerprinz", sort_order=3)
    members = _current(club)
    year = timezone.localdate().year
    for i, name in enumerate(OLD_KINGS):
        reign = Reign.objects.create(organization=club, dignity=king, year=1970 + i * 5, name=name)
        Companion.objects.create(
            organization=club, reign=reign, label="Königin", name=f"{QUEENS[i]} {name.split()[-1]}"
        )
    for offset in range(1, 7):
        holder = members[20 + offset * 7].person
        reign = Reign.objects.create(
            organization=club,
            dignity=king,
            year=year - offset,
            person=holder,
            name=f"{holder.first_name} {holder.last_name}",
        )
        Companion.objects.create(
            organization=club,
            reign=reign,
            label="Königin",
            name=f"{QUEENS[offset]} {holder.last_name}",
        )
    young = [m for m in members if m.person.birth_date.year >= 2003]
    for offset, m in enumerate(young[:4], start=1):
        Reign.objects.create(
            organization=club,
            dignity=youth,
            year=year - offset,
            person=m.person,
            name=f"{m.person.first_name} {m.person.last_name}",
        )
    Reign.objects.create(organization=club, dignity=pupil, year=year - 1, name="Leon Kinderling")
    # Jedes Korps hat seinen eigenen König
    for i, unit in enumerate(
        Department.objects.filter(organization=club, parent=club).order_by("sort_order")
    ):
        dignity = Dignity.objects.create(
            organization=club, unit=unit, name="Korpskönig", sort_order=10 + i
        )
        unit_members = _current(club, unit)
        for offset in range(1, 3):
            if len(unit_members) <= offset * 3:
                break
            p = unit_members[offset * 3].person
            Reign.objects.create(
                organization=club,
                dignity=dignity,
                year=year - offset,
                person=p,
                name=f"{p.first_name} {p.last_name}",
            )


# --- Wettbewerbe und Meldungen ---


def _competitions(club) -> None:
    from competitions.models import Competition, Score, Scoring, Series, Starter

    if Competition.objects.filter(organization=club).exists():
        return
    rnd = random.Random(4711)  # noqa: S311 – nur Testdaten
    year = timezone.localdate().year
    series = Series.objects.create(organization=club, name="Korpspokal")
    for title_year, status in ((year - 1, "endgueltig"), (year, "endgueltig")):
        comp = Competition.objects.create(
            organization=club,
            title=f"Korpspokalschießen {title_year}",
            date=datetime.date(title_year, 5, 16),
            discipline="Luftgewehr",
            location="Schießstand am Schützenhaus",
            status=status,
            website="abschluss",
            website_depth="alle",
            series=series,
        )
        single = Scoring.objects.create(
            organization=club,
            competition=comp,
            name="Einzelwertung",
            shots=10,
            unit_label="Ringe",
        )
        Scoring.objects.create(
            organization=club,
            competition=comp,
            name="Korpswertung",
            kind="einheit",
            source=single,
            team_size=3,
            sort_order=1,
        )
        for unit in Department.objects.filter(organization=club, parent=club).order_by(
            "sort_order"
        ):
            for m in rnd.sample(_current(club, unit), 4):
                starter = Starter.objects.create(
                    organization=club,
                    competition=comp,
                    membership=m,
                    name=f"{m.person.first_name} {m.person.last_name}",
                    unit=unit,
                )
                Score.objects.create(
                    organization=club,
                    scoring=single,
                    starter=starter,
                    value=Decimal(rnd.randint(68, 99)),
                )
    # Ein Wettbewerb in Vorbereitung
    Competition.objects.create(
        organization=club,
        title=f"Vereinsmeisterschaft {year + 1}",
        date=datetime.date(year + 1, 4, 18),
        discipline="Luftgewehr",
        location="Schießstand am Schützenhaus",
    )


def _entries(club) -> None:
    from entries import services as es
    from entries.models import Call, CallBlock, Entry, EntryAnswer, EntryVersion

    if Call.objects.filter(organization=club).exists():
        return
    year = timezone.localdate().year
    korps = list(Department.objects.filter(organization=club, parent=club).order_by("sort_order"))
    call = Call.objects.create(
        organization=club,
        title=f"Meldung zum Schützenfest {year + 1}",
        organizer=club.name,
        description="Bitte meldet, mit wie vielen Schützen und welcher Musik ihr antretet.",
        date=datetime.date(year + 1, 7, 11),
        location="Festplatz Musterstadt",
        deadline=datetime.date(year + 1, 6, 1),
        internal=True,
    )
    count = CallBlock.objects.create(
        organization=club,
        call=call,
        kind=CallBlock.Kind.NUMBER,
        label="Schützen im Festzug",
        required=True,
        settings={"min": 0, "max": 500},
    )
    music = CallBlock.objects.create(
        organization=club,
        call=call,
        kind=CallBlock.Kind.CHOICE,
        label="Musik",
        settings={"options": ["eigene Musik", "Musik vom Verein", "ohne Musik"], "multiple": False},
        sort_order=1,
    )
    rnd = random.Random(1888)  # noqa: S311 – nur Testdaten
    for i, unit in enumerate(korps[:4]):
        entry = Entry.objects.create(organization=club, call=call, department=unit)
        EntryAnswer.objects.create(
            organization=club, entry=entry, block=count, value=rnd.randint(25, 80)
        )
        EntryAnswer.objects.create(
            organization=club, entry=entry, block=music, value=rnd.choice(music.settings["options"])
        )
        if i < 3:
            es.record_version(entry, None, EntryVersion.Channel.HUBIPLAN)
        if i == 0:
            Entry.objects.filter(pk=entry.pk).update(
                status=Entry.Status.CONFIRMED, confirmed_note="Danke, so eingeplant."
            )


def _circulars(club) -> None:
    from circulars.models import Circular, CircularTemplate

    if Circular.objects.filter(organization=club).exists():
        return
    author = User.objects.filter(email=f"schriftfuehrer@{DOMAIN}").first()
    CircularTemplate.objects.create(
        organization=club,
        name="Einladung Generalversammlung",
        subject="Einladung zur Generalversammlung",
        body="Liebe Schützenschwestern und Schützenbrüder,\n\nwir laden herzlich ein …",
    )
    Circular.objects.create(
        organization=club,
        kind=Circular.Kind.NOTICE,
        audience=Circular.Audience.MEMBERS,
        subject="Antreten zum Schützenfest",
        body=(
            "Liebe Schützenschwestern und Schützenbrüder,\n\n"
            "die Korps treten am Samstag um 14 Uhr am Marktplatz an. "
            "Die Aufstellung findet ihr im Dokument „Aufstellung Festzug“.\n\n"
            "Der Vorstand (erfundener Beispieltext)"
        ),
        created_by=author,
    )


# --- Impressum, Briefbogen, Webseite ---


def _imprint(club) -> None:
    from .imprint import ensure
    from .imprint_generator import privacy_for
    from .imprint_seed import _untouched
    from .models import Imprint

    imprint = ensure(club)
    if not _untouched(imprint):
        return
    imprint.legal_form = "eingetragener Verein"
    imprint.phone = "01234 000003"
    imprint.registered = True
    imprint.register_court = "Amtsgericht Musterstadt (erfunden)"
    imprint.register_number = "VR 0003"
    imprint.mode = Imprint.Mode.OWN
    imprint.save()
    imprint.privacy_text = privacy_for(club)
    imprint.privacy_published_text = imprint.privacy_text
    imprint.privacy_published_at = timezone.now()
    imprint.save(
        update_fields=[
            "privacy_text",
            "privacy_published_text",
            "privacy_published_at",
            "updated_at",
        ]
    )


def _letterhead(club) -> None:
    from letterhead.data import ensure
    from letterhead.seed import ROLE_MAILS

    letterhead = ensure(club)
    if not letterhead.show_social:
        letterhead.show_social = True
        letterhead.save(update_fields=["show_social", "updated_at"])
    for role in Role.objects.filter(organization=club, name__in=ROLE_MAILS):
        if not role.contact_email:
            role.contact_email = ROLE_MAILS[role.name].format(slug=SLUG)
            role.save(update_fields=["contact_email"])
    Role.objects.filter(organization=club, name="Schriftführer").update(on_letterhead=True)
    if not club.social_links.exists():
        for position, kind in enumerate(
            [SocialLink.Kind.INSTAGRAM, SocialLink.Kind.FACEBOOK, SocialLink.Kind.TIKTOK]
        ):
            SocialLink.objects.create(
                organization=club,
                kind=kind,
                url=f"https://{kind}.example.test/{SLUG}",
                position=position,
            )


GREETING = (
    "Herzlich willkommen beim Schützenverein Musterstadt! Sieben Korps mit ihren Zügen "
    "tragen unser Schützenfest, vom Grenadierkorps bis zum Tambourkorps.\n\n"
    "Hier findet ihr Termine, Vorstand, Korps und Züge, unsere Majestäten und die "
    "Ergebnisse des Korpspokals. *Alle Angaben auf dieser Testseite sind erfunden.*"
)
HISTORY = (
    "## Aus der Geschichte\n\n"
    "Der Verein wurde 1823 gegründet. Nach und nach entstanden die heutigen Korps.\n\n"
    "Diese Chronik ist ein **erfundener Beispieltext** für den Testserver."
)
TIMELINE = [
    ("chapter", 1823, 1887, "Die ersten Jahrzehnte", ""),
    ("event", 1823, None, "Gründung", "Bürger der Stadt gründen den Schützenverein."),
    ("event", 1850, None, "Jägerkorps", "Zu den Grenadieren kommt das Jägerkorps hinzu."),
    ("chapter", 1888, 1949, "Wachsen und Bewahren", ""),
    ("event", 1888, None, "Eigene Musik", "Das Tambourkorps spielt zum ersten Mal beim Fest."),
    ("event", 1927, None, "Artilleriekorps", "Ein neues Korps mit eigener Kanone aus Holz."),
    ("chapter", 1950, None, "Bis heute", ""),
    ("event", 1955, None, "Reiterkorps", "Zum ersten Mal reiten Schützen in der Parade mit."),
    ("event", 1978, None, "Scheibenschützen", "Die Sportschützen bilden ein eigenes Korps."),
    ("event", 2023, None, "200 Jahre", "Großes Jubiläumsfest mit allen Korps."),
]


def _website(club) -> None:
    from website import privacy
    from website.content_models import WebsiteText
    from website.models import Website, WebsiteDomain
    from website.seed import _social_posts

    website = Website.objects.filter(organization=club).first()
    if website is None:
        website = Website.objects.create(organization=club, public_key=Website.new_key())
    if not WebsiteDomain.objects.filter(hostname=WEB_DOMAIN).exists():
        WebsiteDomain.objects.create(
            organization=club, website=website, hostname=WEB_DOMAIN, is_primary=True
        )
    now = timezone.now()
    timeline = [
        {
            "kind": kind,
            "year": year,
            "until": until,
            "title": title,
            "text": text,
            "images": [],
            "image_position": "auto",
        }
        for kind, year, until, title, text in TIMELINE
    ]
    for kind, slug, title, body, position, entries in (
        (WebsiteText.Kind.GREETING, "", "Willkommen", GREETING, 0, []),
        (WebsiteText.Kind.PAGE, "chronik", "Chronik", HISTORY, 1, timeline),
    ):
        if WebsiteText.objects.filter(website=website, kind=kind, slug=slug).exists():
            continue
        WebsiteText.objects.create(
            organization=club,
            website=website,
            kind=kind,
            slug=slug,
            menu_position=position,
            title=title,
            body=body,
            published_title=title,
            published_body=body,
            published_at=now,
            timeline=entries,
            published_timeline=entries,
        )
    _social_posts(website)
    _board(club)
    if not website.privacy_text:
        privacy.generate(website)
        website.privacy_published_text = website.privacy_text
        website.privacy_published_at = now
        website.save()


def _board(club) -> None:
    if Role.objects.filter(organization=club, name=BOARD_POSITIONS[0]).exists():
        return
    members = [
        m for m in _current(club) if not DepartmentRoleHolder.objects.filter(membership=m).exists()
    ]
    for index, name in enumerate(BOARD_POSITIONS, start=1):
        role = Role.objects.create(
            organization=club,
            name=name,
            on_website=True,
            website_position=index,
            in_chronicle=index <= 3,
        )
        RoleAssignment.objects.create(
            organization=club,
            role=role,
            person=members[index].person,
            valid_from=datetime.date(2019, 3, 1),
        )
    # Frühere Präsidenten für die Chronik (nur Historie, ohne Zugang)
    chair = Role.objects.get(organization=club, name=BOARD_POSITIONS[0])
    for i, (start, end) in enumerate(((2003, 2011), (2011, 2019)), start=10):
        RoleAssignment.objects.create(
            organization=club,
            role=chair,
            person=members[i].person,
            valid_from=datetime.date(start, 3, 1),
            valid_until=datetime.date(end, 2, 28),
        )
