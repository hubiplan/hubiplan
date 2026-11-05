"""Zweiter Demoverein für den Testserver: eine Musikkapelle (alles erfunden).

Gedacht für Musikvereine und Kapellen, die ihre Webseite mit HUBIplan betreiben: ein
Verein ohne Untereinheiten, Mitglieder mit Instrumenten, Vorstand und Dirigent auf der
Webseite, Ehrenmitglieder, verstorbene Mitglieder im Archiv, Termine, Stücke und ein
Auftritt, eine Webseite in Blau und Gold mit Kopfbild, Galerie und dem Menü
„Aktuelles · Kapelle (Chronik, Vorstand, Ehrenmitglieder, Ämter) · Termine · Galerie · Kontakt“.

Ist auf dem Server ein Designpaket mit dem Schlüssel ``kapelle-furth`` eingespielt, wird
es für die Webseite freigegeben und gewählt; sonst bleibt das Standarddesign.

Wiederholbar: Vorhandenes bleibt, wie es ist. Andere Organisationen fasst der Befehl nicht an.
"""

from __future__ import annotations

import datetime
import io
import random

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from access.catalog import (
    BILLING_EDIT,
    BILLING_VIEW,
    CIRCULARS_SEND,
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
from members.models import (
    ExitReason,
    Gender,
    HonoraryTitle,
    HonoraryTitleAward,
    Membership,
    MemberType,
)

from . import demo_korps
from .models import Organization

CLUB_NAME = "Musikkapelle Musterdorf 2009 e.V."
SLUG = "mk-musterdorf"
DOMAIN = f"{SLUG}.test"
WEB_DOMAIN = f"www.{DOMAIN}"
POSTAL_CODE, CITY = "12346", "Musterdorf"
DESIGN_PACKAGE = "kapelle-furth"
BLUE, GOLD = "#37447c", "#e8b441"

CLUB = {
    "short_name": "MK Musterdorf",
    "founding_year": 2009,
    "street": "Am Probenraum 1",
    "postal_code": POSTAL_CODE,
    "city": CITY,
    "contact_email": f"vorstand@{DOMAIN}",
    "primary_color": BLUE,
    "accent_color": GOLD,
    "member_portal_enabled": True,
}

CLUB_ROLES = {
    "Vorstand": None,  # alle Rechte
    "Kassierer": [MEMBERS_VIEW, EXPORT_RUN, FINANCE_VIEW, FINANCE_EDIT, BILLING_VIEW, BILLING_EDIT],
    "Schriftführer": [MEMBERS_VIEW, MEMBERS_EDIT, EVENTS_MANAGE, CIRCULARS_SEND],
}
# Ämter auf der Webseite (ohne Rechte), in dieser Reihenfolge
BOARD_POSITIONS = ["1. Vorsitzender", "2. Vorsitzender", "Dirigent", "Jugendleiterin"]

TYPES = [
    # (Name, gemeldet, aktiv, zählt für Dauer)
    ("aktiv", True, True, True),
    ("passiv", True, False, True),
    ("Ehrenmitglied", True, False, True),
]

# Instrument, Stimme, Anzahl
INSTRUMENTS = [
    ("Trompete", "1. Stimme", 3),
    ("Trompete", "2. Stimme", 2),
    ("Flügelhorn", "", 3),
    ("Tenorhorn", "", 2),
    ("Posaune", "", 3),
    ("Tuba", "", 2),
    ("Klarinette", "", 3),
    ("Saxophon", "", 2),
    ("Lyra", "", 2),
    ("Kleine Trommel", "", 2),
    ("Große Trommel", "", 1),
    ("Becken", "", 1),
]
# Titel, Komponist (erfunden), Dauer in Sekunden
PIECES = [
    ("Musterdorfer Festmarsch", "Heinrich Erfunden", 200),
    ("Gruß an die Kapelle", "Anna Beispiel", 170),
    ("Abendlied am Rhein (erfunden)", "Otto Vorlage", 240),
    ("Parade in Blau und Gold", "Heinrich Erfunden", 185),
]

USERS = [
    # (E-Mail, Vorname, Nachname, Vereinsrolle)
    (f"vorstand@{DOMAIN}", "Marta", "Vorstand", "Vorstand"),
    (f"kasse@{DOMAIN}", "Klaus", "Kassenwart", "Kassierer"),
    (f"schriftfuehrer@{DOMAIN}", "Saskia", "Schreiber", "Schriftführer"),
]

GREETING = (
    "Herzlich willkommen bei der Musikkapelle Musterdorf! Seit 2009 spielen wir auf "
    "Schützenfesten, Umzügen und Konzerten in der Region.\n\n"
    "Neue Musikerinnen und Musiker sind immer willkommen, ob Anfänger oder Wiedereinsteiger. "
    "*Alle Angaben auf dieser Testseite sind erfunden.*"
)
HISTORY = (
    "## Aus der Geschichte\n\n"
    "Die Kapelle wurde 2009 von zwölf Musikern gegründet und ist seitdem stetig gewachsen.\n\n"
    "Diese Chronik ist ein **erfundener Beispieltext** für den Testserver."
)
MEMORIAL = (
    "Wir denken an unsere verstorbenen Musikerinnen, Musiker und Mitglieder.\n\n"
    "*Alle Namen auf dieser Testseite sind erfunden.*"
)
TIMELINE = [
    ("event", 2009, None, "Gründung", "Zwölf Musiker gründen die Kapelle im Pfarrheim."),
    ("event", 2011, None, "Erstes Schützenfest", "Die Kapelle spielt zum ersten Mal beim Fest."),
    ("event", 2015, None, "Neue Uniformen", "Blaue Jacken mit goldenen Knöpfen."),
    ("event", 2019, None, "Zehn Jahre", "Jubiläumskonzert in der Stadthalle."),
    ("event", 2024, None, "Jugendorchester", "Die Jugend spielt zum ersten Mal allein."),
]
ALBUMS = [
    # (Jahr, Monat, Titel, Anzahl Bilder)
    (2025, 7, "Schützenfest 2025", 6),
    (2024, 11, "Konzert 2024", 4),
    (2023, 6, "Ausflug 2023", 3),
]


def all_emails() -> list[str]:
    return [u[0] for u in USERS]


def seed(password: str, reset: bool = False) -> dict:
    """Legt die Kapelle an. Zurück: {"club": …, "created": Anzahl neuer Zugänge}."""
    rnd = random.Random(2009)  # noqa: S311 – nur Testdaten
    club = _organization()
    _roles(club)
    types = _member_types(club)
    _members(club, types, rnd)
    created = _users(club, password, reset)
    _board(club)
    _honorary(club)
    _events(club)
    _music(club, rnd)
    _website(club)
    return {"club": club, "created": created}


def _organization() -> Organization:
    club, created = Organization.objects.get_or_create(
        type=Organization.Type.CLUB,
        name=CLUB_NAME,
        defaults={
            **CLUB,
            "parent": Organization.platform(),
            "enabled_modules": list(SWITCHABLE_MODULES),
        },
    )
    if not created and not set(SWITCHABLE_MODULES) <= set(club.enabled_modules or []):
        club.enabled_modules = sorted({*(club.enabled_modules or []), *SWITCHABLE_MODULES})
        club.save(update_fields=["enabled_modules"])
    return club


def _roles(club) -> None:
    for name, perms in CLUB_ROLES.items():
        Role.objects.get_or_create(
            organization=club,
            name=name,
            defaults={
                "permissions": codes_for("club") if perms is None else perms,
                "represents": name == "Vorstand",
            },
        )


def _member_types(club) -> list[MemberType]:
    types = []
    for order, (name, reported, active, counts) in enumerate(TYPES):
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


def _admit(club, member_type, rnd, number, entry_from=2009) -> Membership | None:
    female = rnd.random() < 0.45
    first = rnd.choice(demo_korps.FIRST_F if female else demo_korps.FIRST_M)
    last = rnd.choice(demo_korps.LAST)
    birth = datetime.date(rnd.randint(1950, 2010), rnd.randint(1, 12), rnd.randint(1, 28))
    entry = datetime.date(rnd.randint(max(entry_from, birth.year + 10), 2025), 1, 1)
    slug = last.lower().replace("ö", "oe").replace("-", "")
    try:
        return member_services.admit(
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
                "street": f"{rnd.choice(demo_korps.STREETS)} {rnd.randint(1, 80)}",
                "postal_code": POSTAL_CODE,
                "city": CITY,
                "departments": [],
            },
        )
    except Exception:  # noqa: BLE001 – Zufallsdaten: Konflikte überspringen
        return None


def _members(club, types, rnd) -> None:
    if Membership.objects.filter(organization=club).exists():
        return
    active, passive, honorary = types
    number = 100
    for _ in range(sum(n for _i, _r, n in INSTRUMENTS) + 3):
        number += 1
        _admit(club, active, rnd, number)
    for _ in range(8):
        number += 1
        _admit(club, passive, rnd, number)
    for _ in range(3):
        number += 1
        _admit(club, honorary, rnd, number, entry_from=2009)
    # Verstorbene Mitglieder (Archiv; später „In Gedenken“ auf der Webseite)
    for year in (2016, 2021, 2024):
        number += 1
        membership = _admit(club, active, rnd, number)
        if membership is None:
            continue
        period = membership.periods.first()
        died = datetime.date(year, rnd.randint(1, 12), rnd.randint(1, 28))
        if died > period.entry_date:
            period.exit_date = died
            period.exit_reason = ExitReason.DEATH
            period.save()
            membership.type_assignments.update(valid_until=died)


def _current(club, type_name: str | None = None) -> list[Membership]:
    qs = Membership.objects.filter(organization=club, purged_at__isnull=True)
    if type_name:
        qs = qs.filter(
            type_assignments__member_type__name=type_name,
            type_assignments__valid_until__isnull=True,
        )
    return [m for m in qs.select_related("person").order_by("pk").distinct() if m.current_period()]


def _users(club, password: str, reset: bool) -> int:
    count = 0
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
        membership = member_services.admit(
            club,
            {
                "last_name": last,
                "first_name": first,
                "birth_date": datetime.date(1975 + len(role_name), 5, 9),
                "member_type": MemberType.objects.get(organization=club, name="aktiv"),
                "entry_date": datetime.date(2009, 5, 1),
                "email": email,
                "street": "Am Probenraum 1",
                "postal_code": POSTAL_CODE,
                "city": CITY,
                "departments": [],
            },
        )
        assignment.person = membership.person
        assignment.save()
        if role_name == "Vorstand" and club.contact_source != Organization.ContactSource.ROLE:
            club.contact_source = Organization.ContactSource.ROLE
            club.contact_role = role
            club.save()
    return count


def _board(club) -> None:
    """Ämter auf der Webseite; Kassierer und Schriftführer stehen dahinter."""
    from website.models import PublicationConsent

    if Role.objects.filter(organization=club, name=BOARD_POSITIONS[0]).exists():
        return
    taken = set(
        RoleAssignment.objects.filter(organization=club, person__isnull=False).values_list(
            "person_id", flat=True
        )
    )
    members = [m for m in _current(club, "aktiv") if m.person_id not in taken]
    for index, name in enumerate(BOARD_POSITIONS, start=1):
        role = Role.objects.create(
            organization=club,
            name=name,
            on_website=True,
            website_position=index,
            in_chronicle=index <= 2,
        )
        RoleAssignment.objects.create(
            organization=club,
            role=role,
            person=members[index].person,
            valid_from=datetime.date(2021, 3, 1),
        )
        # Der Vorstand zeigt sich auf der Webseite mit E-Mail-Adresse
        PublicationConsent.objects.get_or_create(
            organization=club,
            membership=members[index],
            category=PublicationConsent.Category.EMAIL,
            ended_at=None,
            defaults={"since": datetime.date(2021, 3, 1), "source": "paper"},
        )
    for position, name in enumerate(("Kassierer", "Schriftführer"), start=len(BOARD_POSITIONS) + 1):
        Role.objects.filter(organization=club, name=name).update(
            on_website=True, website_position=position
        )
    # Gründungsvorsitzender für die Chronik (nur Historie)
    chair = Role.objects.get(organization=club, name=BOARD_POSITIONS[0])
    RoleAssignment.objects.create(
        organization=club,
        role=chair,
        person=members[10].person,
        valid_from=datetime.date(2009, 5, 1),
        valid_until=datetime.date(2021, 2, 28),
    )


def _honorary(club) -> None:
    title, created = HonoraryTitle.objects.get_or_create(
        organization=club,
        name="Ehrenmitglied",
        defaults={"name_plural": "Ehrenmitglieder", "is_public": True},
    )
    if not created:
        return
    for membership in _current(club, "Ehrenmitglied"):
        HonoraryTitleAward.objects.create(
            organization=club,
            person=membership.person,
            title=title,
            valid_from=datetime.date(2019, 5, 1),
        )


def _events(club) -> None:
    from events.seed import _at, _event, _next

    for month, day, hour, hours, title, place in (
        (1, 10, 19, 2, "Jahreshauptversammlung", "Probenraum, Am Probenraum 1"),
        (5, 3, 15, 2, "Frühlingskonzert", "Stadthalle Musterdorf"),
        (7, 12, 14, 6, "Schützenfest", "Festplatz Musterstadt"),
        (11, 15, 18, 3, "Herbstkonzert", "Pfarrkirche Musterdorf"),
        (12, 20, 16, 2, "Weihnachtsständchen", "Marktplatz Musterdorf"),
    ):
        start = _next(month, day)
        _event(
            club,
            title,
            _at(start, hour),
            _at(start, hour + hours),
            visibility="public",
            location=place,
        )


def _music(club, rnd) -> None:
    from music.models import Arrangement, Musician, Piece, Skill

    if Musician.objects.filter(organization=club).exists():
        return
    slots = [(i, r) for i, r, n in INSTRUMENTS for _ in range(n)]
    for membership, (instrument, register) in zip(_current(club, "aktiv"), slots, strict=False):
        musician = Musician.objects.create(organization=club, membership=membership)
        Skill.objects.create(
            organization=club,
            musician=musician,
            instrument=instrument,
            register=register,
            primary=True,
        )
    for title, composer, seconds in PIECES:
        piece = Piece.objects.create(organization=club, title=title, composer=composer)
        Arrangement.objects.create(
            organization=club,
            piece=piece,
            name=f"{title} (Blasorchester)",
            ensemble="Blasorchester",
            duration_seconds=seconds,
            difficulty=rnd.choice(["leicht", "mittel", "schwer"]),
        )


# --- Webseite ---


def _picture(width: int, height: int, background: str, text: str = "", sub: str = "") -> bytes:
    """Erfundenes Bild: Streifen, Kreis und optional Schrift (nur ASCII, Standardschrift)."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    for x in range(-height, width, 40):
        draw.line([(x, height), (x + height, 0)], fill="#303c70", width=14)
    r = int(height * 0.35)
    cx, cy = int(height * 0.55), height // 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GOLD)
    draw.ellipse([cx - r + 30, cy - r + 30, cx + r - 30, cy + r - 30], outline=BLUE, width=8)
    if text:
        draw.text((cx + r + 50, cy - 55), text, font=ImageFont.load_default(size=56), fill="white")
    if sub:
        draw.text((cx + r + 52, cy + 15), sub, font=ImageFont.load_default(size=32), fill=GOLD)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def _image(website, name: str, data: bytes, alt: str, caption: str = ""):
    from website import content

    return content.store_image(
        website, SimpleUploadedFile(name, data, "image/jpeg"), caption, alt, None
    )


def _website(club) -> None:
    from website import privacy
    from website.content_models import GalleryAlbum, GalleryItem, WebsiteImage, WebsiteText
    from website.menu import HISTORY_SLUG, MEMORIAL_SLUG
    from website.models import DesignPackage, PublicationConsent, Website, WebsiteDomain
    from website.views import set_header_image

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
    # Erste Fassung legte die Chronik als eigene Seite an; sie ist der Bereich „Chronik“
    pages = WebsiteText.objects.filter(website=website, kind=WebsiteText.Kind.PAGE)
    if not pages.filter(slug=HISTORY_SLUG).exists():
        pages.filter(slug="chronik").update(slug=HISTORY_SLUG)
    for kind, slug, title, body, position, entries in (
        (WebsiteText.Kind.GREETING, "", "Willkommen", GREETING, 0, []),
        (WebsiteText.Kind.PAGE, HISTORY_SLUG, "Chronik", HISTORY, 1, timeline),
        (WebsiteText.Kind.PAGE, MEMORIAL_SLUG, "In Gedenken", MEMORIAL, 2, []),
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
    if not WebsiteImage.objects.filter(website=website).exists():
        banner = _image(
            website,
            "kopfbild.jpg",
            _picture(1200, 300, BLUE, "Musikkapelle Musterdorf", "2009 e.V. - erfundenes Kopfbild"),
            CLUB_NAME,
        )
        set_header_image(website, banner.pk)
        for position, (year, month, title, count) in enumerate(ALBUMS):
            album = GalleryAlbum.objects.create(
                organization=club,
                website=website,
                title=title,
                slug=str(year),
                date=datetime.date(year, month, 1),
                position=position,
                published=True,
            )
            for n in range(count):
                image = _image(
                    website,
                    f"album-{year}-{n + 1}.jpg",
                    _picture(1200, 800, ("#37447c", "#4b5a96", "#2b3768")[n % 3]),
                    f"Erfundenes Foto {n + 1}",
                    f"{title}, Bild {n + 1} (erfunden)",
                )
                GalleryItem.objects.create(organization=club, album=album, image=image, position=n)
                if n == 0:
                    album.cover = image
                    album.save(update_fields=["cover"])
    # Bereiche, Namen und Menü wie bei einer Kapellen-Webseite: „Kapelle“ mit der Chronik,
    # „Mitglieder“ mit Vorstand, Ehrenmitgliedern, Aktiven, Passiven und Gedenken
    types = {mt.name: mt.pk for mt in MemberType.objects.filter(organization=club)}
    lists = [f"membertype:{types[name]}" for name in ("aktiv", "passiv") if name in types]
    blocks = dict(website.blocks or {})
    blocks.update({"gallery": True, "honors": False, "results": False, "units": False})
    blocks.update({"members": True, "memorial": True, "search": True})
    blocks.update({key: True for key in lists})
    website.blocks = blocks
    website.block_names = {
        **(website.block_names or {}),
        "group:history": "Kapelle",
        **dict(zip(lists, ("Aktive", "Passive"), strict=False)),
    }
    website.menu = [
        {"key": "posts", "children": []},
        {"key": "group:history", "children": [{"key": "history"}, {"key": "offices"}]},
        {
            "key": "members",
            "children": [
                {"key": "board"},
                {"key": "honorary"},
                *({"key": key} for key in lists),
                {"key": "memorial"},
            ],
        },
        {"key": "events", "children": []},
        {"key": "gallery", "children": []},
        {"key": "contact", "children": []},
    ]
    website.show_instrument = True
    website.show_address = True
    fields = ["blocks", "block_names", "menu", "show_instrument", "show_address"]
    # Die beiden Vorsitzenden zeigen auf der Webseite auch ihre Anschrift (erfunden)
    for name in BOARD_POSITIONS[:2]:
        for a in RoleAssignment.objects.filter(
            organization=club, role__name=name, valid_until__isnull=True
        ):
            membership = Membership.objects.filter(organization=club, person=a.person).first()
            if membership is not None:
                PublicationConsent.objects.get_or_create(
                    organization=club,
                    membership=membership,
                    category=PublicationConsent.Category.ADDRESS,
                    ended_at=None,
                    defaults={"since": datetime.date(2021, 3, 1), "source": "paper"},
                )
    package = DesignPackage.objects.filter(key=DESIGN_PACKAGE).first()
    if package is not None:
        package.websites.add(website)
        website.design = package.key
        fields.append("design")
    if not website.privacy_text:
        privacy.generate(website)
        website.privacy_published_text = website.privacy_text
        website.privacy_published_at = now
        fields += [
            "privacy_text",
            "privacy_facts",
            "privacy_generated_at",
            "privacy_published_text",
            "privacy_published_at",
        ]
    website.save(update_fields=fields)
