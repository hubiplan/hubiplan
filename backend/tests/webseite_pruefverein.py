"""Prüfverein für die Form der Webseiten-Schnittstelle: belegt im Demoverein alles, was die
öffentliche Schnittstelle liefern kann und was die Demodaten nicht zeigen (alles erfunden).

Ziel: ``webseite_form.luecken`` bleibt leer. Liefert die Schnittstelle ein neues Feld, das
kein Beispiel belegt, schlägt ``test_webseite_form.py`` an; dann hier ergänzen.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from organizations.models import InstanceAddress, Organization
from statutes.models import StatutePublication
from website import style
from website.content_models import WebsiteImage, WebsiteText
from website.models import DesignPackage, Website


def bild(website: Website, key: str, **felder) -> WebsiteImage:
    return WebsiteImage.objects.create(
        organization=website.organization,
        website=website,
        key=key,
        width=1200,
        height=800,
        caption=f"Bild {key}",
        alt_text=f"Beschreibung {key}",
        credit="Erika Beispiel",
        **felder,
    )


def _stil() -> dict:
    """Jeder Stilregler verstellt (letzte Stufe; Schalter an)."""
    wert = {k: True if stufen is bool else stufen[-1] for k, stufen in style.OPTIONS.items()}
    wert.update(dict.fromkeys(style.FONT_STACKS, ["Musterschrift", "sans-serif"]))
    return style.validate(wert)


def grunddaten(website: Website) -> None:
    club = website.organization
    verband = Organization.objects.create(
        name="Musterverband", type="federation", website="https://verband.example.org"
    )
    club.parent = verband
    club.logo = "logos/pruefverein.png"
    club.contact_phone = "+49 30 1234567"
    club.gradients = [{"from": 0, "to": 1, "direction": "to right"}]
    club.save()
    # Eigene Adresse des Vereins für HUBIplan: steht in der Vorschau unter frame_origins
    InstanceAddress.objects.create(organization=club, hostname="verein.musterstadt.example")

    website.style = _stil()
    from website import designs

    website.color_roles = {
        design: {**dict.fromkeys(designs.COMMON_ROLES, 0), "header": "g0", "line": "g0"}
        for design in designs.DESIGNS
    }
    website.block_names = {**(website.block_names or {}), "events": "Kalender"}
    heute = timezone.localdate()
    website.notice_text = "Schützenfest am Wochenende"
    website.notice_target = {"page": "events"}
    website.notice_button = "Zum Programm"
    website.notice_date = heute + datetime.timedelta(days=5)
    website.save()

    kopf = bild(website, "pruefkopf", header=True)
    bild(website, "pruefkopfschmal", header_narrow=True)
    paket = DesignPackage.objects.create(
        organization=club,
        key="pruefpaket",
        label="Prüfpaket",
        label_en="Test package",
        roles={},
        css=".pruef{}",
        content_hash="0" * 64,
    )
    paket.websites.add(website)
    # als Design gewählt: Nur dann lädt die Webseite das Paket (design/<key>/)
    website.design = paket.key
    website.save(update_fields=["design"])

    gruss = WebsiteText.objects.filter(website=website, kind=WebsiteText.Kind.GREETING).first()
    gruss.published_image = kopf
    gruss.published_gallery = [kopf.pk]
    gruss.published_show_captions = True
    gruss.save()
    for bereich in ("events", "contact"):
        WebsiteText.objects.create(
            organization=club,
            website=website,
            kind=WebsiteText.Kind.INTRO,
            slug=bereich,
            title="Einleitung",
            published_title="Einleitung",
            published_body="Ein kurzer Text vorweg, für den Musterverein.",
            published_image=kopf,
            published_at=timezone.now(),
        )
    for art in ("fee_rules", "founding_deed"):
        StatutePublication.objects.create(
            organization=club, kind=art, is_public=True, public_key=f"pruef-{art}"
        )


def personen(website: Website) -> None:
    """Alle Mitglieder mit Einwilligungen, Foto und Kontaktdaten: So liefern Vorstand,
    Würden und Listen jedes Personenfeld."""
    from members.models import ContactDetails, Membership
    from members.photo_models import MemberPhoto
    from website.models import PublicationConsent

    club = website.organization
    website.show_address = True
    website.show_titles = True
    website.show_member_since = True
    website.save()
    heute = timezone.localdate()
    mitglieder = list(Membership.objects.filter(organization=club))
    arten = [
        c for c in PublicationConsent.Category if c not in PublicationConsent.OBJECTION_CATEGORIES
    ]
    for m in mitglieder:
        for art in arten:
            PublicationConsent.objects.get_or_create(
                organization=club,
                membership=m,
                category=art,
                ended_at=None,
                defaults={"since": heute, "source": "paper"},
            )
        MemberPhoto.objects.get_or_create(
            organization=club, membership=m, status=MemberPhoto.Status.APPROVED
        )
    Membership.objects.filter(organization=club, photo_consent_at=None).update(
        photo_consent_at=timezone.now()
    )
    for kontakt in ContactDetails.objects.filter(person__in=[m.person_id for m in mitglieder]):
        kontakt.street = "Musterweg 1"
        kontakt.postal_code = "12345"
        kontakt.city = "Musterstadt"
        kontakt.phone = "+49 30 7654321"
        kontakt.save()


def einheiten(website: Website) -> None:
    from organizations.models import Department, DepartmentRole, SocialLink
    from website.public import SiteView

    club = website.organization
    kopf = WebsiteImage.objects.get(key="pruefkopf")
    erste = SiteView(website).units[0]
    Department.objects.filter(pk=erste.pk).update(
        logo="logos/einheit.png",
        website="https://zug.example.org",
        website_on_site=True,
        website_image="vorschau/einheit.png",
    )
    DepartmentRole.objects.filter(department=erste).update(contact_email="zug@example.org")
    SocialLink.objects.create(
        organization=erste, kind="instagram", url="https://instagram.example.org/zug"
    )
    Department.objects.create(
        organization=club, parent=erste, type="unit", name="Jungschützen im Zug"
    )
    text, _neu = WebsiteText.objects.get_or_create(
        organization=club,
        website=website,
        kind=WebsiteText.Kind.UNIT,
        department=erste,
        defaults={"title": erste.name},
    )
    text.published_title = erste.name
    text.published_body = "Wir sind der erste Zug."
    text.published_image = kopf
    text.published_gallery = [kopf.pk]
    text.published_show_captions = True
    text.published_at = timezone.now()
    text.save()


def wuerden(website: Website) -> None:
    """Würden mit genauem Zeitraum, Begleitung und Foto, je eine im Verein und in der ersten
    Untereinheit; dazu eine Ehrung und E-Mail-Adressen der Vorstandsrollen."""
    from access.models import Role
    from honors.models import Companion, Dignity, Reign, ReignPhoto
    from members.models import HonoraryTitle, HonoraryTitleAward, Membership
    from website.public import SiteView

    club = website.organization
    heute = timezone.localdate()
    erste = SiteView(website).units[0]
    mitglieder = list(Membership.objects.filter(organization=club).select_related("person")[:4])
    for nummer, einheit in enumerate((None, erste)):
        wuerde = Dignity.objects.create(
            organization=club,
            unit=einheit,
            name=f"Prüfkönig {nummer + 1}",
            name_plural="Prüfkönige",
            web_slug_history=[f"alter-koenig-{nummer + 1}"],
        )
        for jahr, person in ((heute.year - 1, mitglieder[0]), (heute.year, mitglieder[1])):
            zeit = Reign.objects.create(
                organization=club,
                dignity=wuerde,
                year=jahr,
                valid_from=datetime.date(jahr, 1, 1),
                valid_until=datetime.date(jahr, 12, 31),
                person=person.person,
                note="erfunden",
            )
            Companion.objects.create(
                organization=club, reign=zeit, label="Königin", person=mitglieder[2].person
            )
            ReignPhoto.objects.create(
                organization=club,
                reign=zeit,
                key=f"pruefreign{nummer}{jahr}",
                consent_confirmed=True,
            )
    ehrung = HonoraryTitle.objects.create(
        organization=club, name="Ehrenprüfer", name_plural="Ehrenprüfer", is_public=True
    )
    HonoraryTitleAward.objects.create(
        organization=club,
        person=mitglieder[3].person,
        title=ehrung,
        valid_from=datetime.date(heute.year - 2, 1, 1),
        display_title="Ehrenoberst",
    )
    Role.objects.filter(organization=club, on_website=True).update(
        contact_email="vorstand@example.org"
    )
    # Würde des Dachverbands, nach unten weitergegeben, mit einem Träger aus diesem Verein
    verbandswuerde = Dignity.objects.create(
        organization=club.parent,
        name="Verbandskönig",
        name_plural="Verbandskönige",
        share_down=True,
    )
    Reign.objects.create(
        organization=club.parent,
        dignity=verbandswuerde,
        year=heute.year,
        name="Erika Beispiel",
        origin=club,
    )
    website.include_parent_honors = True
    website.save()


def _module(club, *namen: str) -> None:
    club.enabled_modules = sorted({*(club.enabled_modules or []), *namen})
    club.save(update_fields=["enabled_modules"])


def termine(website: Website) -> None:
    """Ein Termin mit allem: Untereinheit, Anhang, Anmeldung mit Preis, eigene Seite,
    Auftrittsart; dazu ein Termin des Dachverbands, der nach unten freigegeben ist."""
    from events.models import Event, EventAttachment, EventCategory
    from music.models import Performance, PerformanceKind
    from registrations.models import PriceOption, PriceStep, RegistrationSetup
    from website.public import SiteView

    club = website.organization
    _module(club, "music", "registrations")
    website.include_unit_events = True
    website.include_parent_events = True
    website.save()
    erste = SiteView(website).units[0]
    art = EventCategory.objects.create(organization=club, name="Prüftermine", color="#336699")
    start = timezone.now() + datetime.timedelta(days=10)
    fest = Event.objects.create(
        organization=club,
        department=erste,
        title="Prüffest",
        visibility="public",
        category=art,
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=4),
        location="Festhalle",
        address="Musterweg 1, 12345 Musterstadt",
        description="Ein erfundenes Fest.",
        programme=[{"time": "18:00", "text": "Einlass"}],
    )
    EventAttachment.objects.create(
        organization=club,
        event=fest,
        kind=EventAttachment.Kind.FILE,
        file="termine/programm.pdf",
        name="programm.pdf",
        content_type="application/pdf",
        size=1000,
        on_website=True,
    )
    anmeldung = RegistrationSetup.objects.create(
        organization=club,
        event=fest,
        opens_at=timezone.now() - datetime.timedelta(days=1),
        closes_at=start - datetime.timedelta(days=1),
        capacity=100,
        public=True,
        public_key="pruefanmeldung",
        waitlist=True,
        terms="Teilnahme auf eigene Gefahr.",
    )
    preis = PriceOption.objects.create(
        organization=club, setup=anmeldung, name="Erwachsene", name_en="Adults"
    )
    PriceStep.objects.create(
        organization=club,
        price=preis,
        name="Frühbucher",
        amount="12.00",
        until_date=timezone.localdate() + datetime.timedelta(days=5),
    )
    auftritt = PerformanceKind.objects.create(organization=club, name="Konzert", on_website=True)
    Performance.objects.create(organization=club, event=fest, kind=auftritt)
    WebsiteText.objects.create(
        organization=club,
        website=website,
        kind=WebsiteText.Kind.PAGE,
        slug="prueffest",
        title="Prüffest",
        published_title="Prüffest",
        published_body="Alles zum Fest.",
        published_image=WebsiteImage.objects.get(key="pruefkopf"),
        published_at=timezone.now(),
        event=fest,
    )
    verband = club.parent
    _module(verband, "events")
    Event.objects.create(
        organization=verband,
        title="Verbandstag",
        visibility="public",
        share_down=True,
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=2),
    )


def chronik(website: Website) -> None:
    """Zeitleiste mit Zeitraum, Kapitel und Bildern."""
    _module(website.organization, "chronicle")
    kopf = WebsiteImage.objects.get(key="pruefkopf")
    seite, _neu = WebsiteText.objects.get_or_create(
        organization=website.organization,
        website=website,
        kind=WebsiteText.Kind.PAGE,
        slug="geschichte",
        defaults={"title": "Chronik", "published_title": "Chronik"},
    )
    seite.published_body = seite.published_body or "Die Geschichte des Vereins, erfunden."
    seite.published_at = seite.published_at or timezone.now()
    seite.published_timeline = [
        *seite.published_timeline,
        {"year": 1960, "kind": "chapter", "title": "Aufbruch"},
        {
            "year": 1961,
            "until": 1963,
            "title": "Neubau",
            "text": "erfunden",
            "images": [kopf.pk],
            "image_position": "left",
        },
    ]
    seite.published_image = kopf
    seite.save()


def ergebnisse(website: Website) -> None:
    """Wettbewerbe mit allem: weitere Angaben, frühere Adressen, Titel, Wanderpokal, ein
    Vogelschießen mit gefallenem Pfand und ein laufender Wettbewerb."""
    from competitions.models import AwardGrant, Competition, Prize, Series, Starter, Trophy
    from members.models import Membership

    club = website.organization
    heute = timezone.localdate()
    mitglied = Membership.objects.filter(organization=club).first()
    fertig = (
        Competition.objects.filter(organization=club, status=Competition.Status.FINAL)
        .exclude(website=Competition.Website.OFF)
        .first()
    )
    fertig.details = [{"label": "Distanz", "value": "10 m"}]
    fertig.web_slug_history = ["alter-wettbewerb"]
    fertig.save()
    pokal = Trophy.objects.create(organization=club, name="Prüfpokal", description="erfunden")
    reihe = fertig.series or Series.objects.filter(organization=club).first()
    AwardGrant.objects.create(
        organization=club,
        competition=fertig,
        series=reihe,
        year=fertig.date.year,
        title="Prüfmeister",
        membership=mitglied,
        name="Erika Beispiel",
        trophy=pokal,
    )
    if reihe is not None:
        reihe.web_slug_history = ["alte-reihe"]
        reihe.save()
    vogel = Competition.objects.create(
        organization=club,
        title="Prüfvogelschießen",
        form=Competition.Form.BIRD,
        date=heute,
        status=Competition.Status.RUNNING,
        website=Competition.Website.LIVE,
        website_depth=Competition.WebsiteDepth.ALL,
    )
    schuetze = Starter.objects.create(
        organization=club, competition=vogel, membership=mitglied, name="Erika Beispiel"
    )
    Prize.objects.create(
        organization=club,
        competition=vogel,
        name="Kopf",
        award="Orden",
        winner=schuetze,
        shot_number=12,
        fallen_at=timezone.now(),
    )
    Prize.objects.create(organization=club, competition=vogel, name="Rumpf")


def inhalte(website: Website) -> None:
    """Beiträge (eigene und aus den Kanälen), Dokumente, verschachtelte Alben, Gedenkseite
    und Repertoire."""
    from members.models import ExitReason, Membership, MembershipPeriod
    from music.models import Piece
    from website import gallery
    from website.content_models import GalleryAlbum, WebsiteDocument
    from website.news_models import NewsPost
    from website.public import SiteView
    from website.social_models import SocialComment, SocialFeed, SocialPost, SocialPostImage

    club = website.organization
    _module(club, "social", "scores")
    kopf = WebsiteImage.objects.get(key="pruefkopf")
    jetzt = timezone.now()
    heute = timezone.localdate()

    NewsPost.objects.create(
        organization=club,
        website=website,
        slug="pruefbeitrag",
        title="Prüfbeitrag",
        date=heute,
        published_title="Prüfbeitrag",
        published_date=heute,
        published_body="Erster Absatz.\n\nZweiter Absatz mit mehr Text.",
        published_images=[kopf.pk],
        published_videos=[
            {"url": "https://video.example.org/1", "title": "Film", "image": kopf.pk}
        ],
        published_at=jetzt,
    )
    NewsPost.objects.create(
        organization=club,
        website=website,
        department=SiteView(website).units[0],
        slug="pruefbeitrag-zug",
        title="Aus dem Zug",
        date=heute,
        published_title="Aus dem Zug",
        published_date=heute,
        published_body="Kurz.",
        published_at=jetzt,
    )
    kanal, _neu = SocialFeed.objects.update_or_create(
        organization=club,
        website=website,
        department=None,
        kind="instagram",
        defaults={
            "account_name": "pruefverein",
            "show_counts": True,
            "comments": "all",
            "status": "ok",
        },
    )
    beitrag = SocialPost.objects.create(
        organization=club,
        feed=kanal,
        external_id="pruef-1",
        media_type="image",
        text="Ein erfundener Beitrag",
        permalink="https://instagram.example.org/p/1",
        published_at=jetzt,
        like_count=12,
        comment_count=1,
    )
    SocialPostImage.objects.create(
        organization=club, post=beitrag, key="pruefpostbild", width=800, height=800, alt_text="Bild"
    )
    SocialComment.objects.create(
        organization=club,
        post=beitrag,
        external_id="pruef-k1",
        author="Erika Beispiel",
        text="Schön!",
        published_at=jetzt,
        state="visible",
    )

    for bereich in ("press", "documents"):
        WebsiteDocument.objects.create(
            organization=club,
            website=website,
            section=bereich,
            key=WebsiteDocument.new_key(),
            title=f"Prüfdokument {bereich}",
            source="Musterzeitung",
            date=heute,
            file="webseite/pruef.pdf",
            preview="webseite/pruef.png",
            content_type="application/pdf",
            size=120_000,
        )

    oben = GalleryAlbum.objects.create(
        organization=club,
        website=website,
        title="Prüfalbum",
        slug="pruefalbum",
        description="erfunden",
        date=heute,
        cover=kopf,
        published=True,
    )
    unten = GalleryAlbum.objects.create(
        organization=club,
        website=website,
        parent=oben,
        title="Prüfalbum, zweiter Tag",
        slug="pruefalbum-tag-2",
        date=heute,
        published=True,
    )
    gallery.set_images(oben, [kopf.pk])
    gallery.set_images(unten, [kopf.pk])

    verstorben = Membership.objects.filter(organization=club).last()
    MembershipPeriod.objects.filter(membership=verstorben).update(
        exit_date=heute - datetime.timedelta(days=400), exit_reason=ExitReason.DEATH
    )
    WebsiteText.objects.create(
        organization=club,
        website=website,
        kind=WebsiteText.Kind.PAGE,
        slug="in-gedenken",
        title="In Gedenken",
        published_title="In Gedenken",
        published_body="Wir denken an unsere Verstorbenen.",
        published_image=kopf,
        published_at=jetzt,
    )
    Piece.objects.create(
        organization=club, title="Prüfmarsch", composer="M. Mustermann", on_website=True
    )


def mitmachen(website: Website) -> None:
    """Beitrittsseite, Mitgliederlisten und Belegung."""
    from zoneinfo import ZoneInfo

    from admission.models import ApplicationForm
    from bookings.models import Booking
    from bookings.services import rebuild
    from materials.models import MaterialItem
    from members.models import MemberType

    club = website.organization
    _module(club, "infrastructure", "bookings", "billing", "admission")
    arten = list(MemberType.objects.filter(organization=club, is_archived=False))
    website.blocks = {**website.blocks, **{f"membertype:{a.pk}": True for a in arten}}
    website.save()
    antrag, _neu = ApplicationForm.objects.get_or_create(
        organization=club, defaults={"public_key": "pruefantrag"}
    )
    antrag.enabled = True
    antrag.types = [
        {"id": a.pk, "label": {"de": a.name}, "text": {"de": "erfunden"}, "organizations": True}
        for a in arten
    ]
    antrag.fields = {**antrag.fields, "unit": "optional"}
    antrag.texts = {"intro": {"de": "Schön, dass du zu uns willst."}}
    antrag.save()

    haus = MaterialItem.objects.create(
        organization=club,
        kind="facility",
        title="Prüfhalle",
        description="Vereinsheim",
        location_kind="address",
        address={
            "street": "Musterweg 1",
            "postal_code": "12345",
            "city": "Musterstadt",
            "country": "DE",
        },
        facility_type="building",
        booking_rules={"enabled": True, "website": "titles"},
    )
    tag = timezone.localdate() + datetime.timedelta(days=1)
    start = datetime.datetime.combine(tag, datetime.time(14), ZoneInfo("Europe/Berlin"))
    buchung = Booking.objects.create(
        organization=club,
        item=haus,
        title="Seniorennachmittag",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=2),
        status="confirmed",
        visibility="public",
    )
    rebuild(buchung)


def _daten_je_art(website: Website) -> dict[str, dict]:
    """Inhalt für jede Abschnittsart, mit allen Feldern."""
    from competitions.models import Competition
    from events.models import Event, EventCategory
    from places.models import Place
    from website import home

    club = website.organization
    ort = Place.objects.create(
        organization=club,
        name="Prüfhalle",
        address="Musterweg 1, 12345 Musterstadt",
        directions="Parken hinter der Halle.",
    )
    refs = home.references(website)
    bild_id = WebsiteImage.objects.get(key="pruefkopf").pk
    fest = Event.objects.get(organization=club, title="Prüffest")
    art = EventCategory.objects.get(organization=club, name="Prüftermine")
    eins = lambda name: sorted(refs[name])[0]  # noqa: E731
    punkte = [{"title": "Eins", "text": "Text eins"}, {"title": "Zwei", "text": "Text zwei"}]
    ziele = [
        {"page": "events"},
        {"unit": eins("units")},
        {"event": fest.pk},
        {"url": "https://example.org/mehr"},
    ]
    return {
        "text": {"title": "Text", "text": "Ein Absatz."},
        "text_image": {
            "title": "Text mit Bild",
            "text": "Ein Absatz.",
            "image": bild_id,
            "side": "left",
            "size": "small",
            "image_note": "Platzhalter",
        },
        "banner": {"image": bild_id, "line": "Willkommen", "height": "high"},
        "cover": {"image": bild_id},
        "buttons": {
            "title": "Knöpfe",
            "buttons": [{"label": f"Knopf {i}", "target": z} for i, z in enumerate(ziele[1:])],
            "align": "center",
        },
        "tiles": {
            "title": "Kacheln",
            "tiles": [
                {
                    "title": f"Kachel {i}",
                    "text": "Text",
                    "image": bild_id,
                    "target": z,
                    "button": "Mehr",
                }
                for i, z in enumerate(ziele)
            ],
            "columns": 2,
        },
        "event": {"title": "Nächstes Fest", "event": fest.pk},
        "album": {"title": "Album", "album": eins("albums"), "count": 4},
        "quote": {"text": "Ein Zitat.", "name": "Erika Beispiel"},
        "contacts": {"title": "Ansprechpartner", "roles": sorted(refs["roles"])[:2]},
        "faq": {"title": "Fragen", "items": [{"question": "Wie?", "answer": "So."}]},
        "partners": {
            "title": "Partner",
            "items": [{"name": "Musterfirma", "image": bild_id, "url": "https://example.org"}],
        },
        "directions": {"title": "Anfahrt", "place": ort.pk, "text": "Mit dem Bus."},
        "event_list": {"title": "Prüftermine", "category": art.pk, "count": 3},
        "document": {"title": "Antrag", "document": eins("documents"), "label": "Laden"},
        "video": {
            "title": "Film",
            "url": "https://video.example.org/1",
            "image": bild_id,
            "text": "Ein Film.",
        },
        "chronicle": {"title": "Aus der Chronik", "count": 3},
        "facts": {"title": "Zahlen", "items": [{"value": "100", "label": "Jahre"}]},
        "divider": {"style": "line", "size": "large"},
        "countdown": {
            "title": "Bald",
            "mode": "event",
            "event": fest.pk,
            "text": "bis zum Fest",
            "after": "text",
            "after_text": "Es läuft.",
        },
        "join": {"title": "Mitmachen", "text": "Komm zu uns.", "label": "Antrag"},
        "donation": {
            "title": "Spenden",
            "text": "Für die neue Fahne.",
            "holder": "Schützenverein Musterstadt",
            "iban": "DE02120300000000202051",
            "bic": "BYLADEM1001",
            "purpose": "Fahne",
            "goal": 5000,
            "raised": 1200,
            "label": "Spenden",
            "url": "https://example.org/spenden",
        },
        "hours": {
            "title": "Zeiten",
            "items": [{"day": "Montag", "time": "18 Uhr", "note": "Training"}],
            "text": "Feiertags geschlossen.",
        },
        "columns": {"title": "Spalten", "items": punkte},
        "table": {
            "title": "Tabelle",
            "head": ["Platz", "Name"],
            "rows": [["1", "Erika Beispiel"]],
            "text": "Stand heute.",
        },
        "timeline": {
            "title": "Zeitstrahl",
            "items": [{"when": "1920", "title": "Gründung", "text": "erfunden"}],
        },
        "program": {
            "title": "Programm",
            "items": [{"day": "Samstag", "time": "18:00", "text": "Einlass"}],
            "text": "Änderungen vorbehalten.",
        },
        "callout": {"title": "Hinweis", "text": "Bitte beachten.", "style": "warning"},
        "accordion": {"title": "Aufklappen", "items": punkte},
        "images": {
            "title": "Bilder",
            "items": [{"image": bild_id, "caption": "Bild", "note": "Platzhalter"}],
            "columns": 2,
        },
        "downloads": {"title": "Downloads", "documents": sorted(refs["documents"])},
        "unit_honors": {"title": "Majestäten des Zugs", "unit": eins("units")},
        "competition": {
            "title": "Ergebnisse",
            "competition": Competition.objects.get(
                organization=club, web_slug_history=["alter-wettbewerb"]
            ).pk,
            "days": None,
        },
        "albums": {"title": "Galerie", "count": 4, "days": None},
        "posts": {"title": "Neues", "count": 3, "channel": "all", "days": None},
        "app": {"title": "App", "text": "Für Mitglieder.", "qr": True, "store": True},
        "live_facts": {
            "title": "Aus HUBIplan",
            "items": [{"fact": f, "label": f"Zahl {f}"} for f in home.LIVE_FACTS],
        },
    }


def abschnitte(website: Website) -> None:
    """Jede Abschnittsart einmal: die ersten 30 auf der Startseite, der Rest auf der Seite der
    ersten Untereinheit, das Titelbild auf der Veranstaltungsseite. Dazu Titelzeilen auf dem
    Titelfoto und beide Arten von Marken."""
    from competitions.models import Competition
    from website import home
    from website.models import DEFAULT_HOME_OFF, HOME_SECTIONS
    from website.public import SiteView

    daten = _daten_je_art(website)
    assert set(daten) == set(home.ALL_KINDS), set(home.ALL_KINDS) ^ set(daten)
    bild_id = WebsiteImage.objects.get(key="pruefkopf").pk
    eigene = [
        {
            "key": f"c:p{nummer}",
            "kind": art,
            "on": True,
            "bg": ("none", "light", "p0", "g0")[nummer % 4],
            "width": home.WIDTHS[nummer % 3],
            "column": home.COLUMNS[nummer % 2],
            "data": daten[art],
        }
        for nummer, art in enumerate(home.KINDS)
    ]
    eigene[0]["mark"] = home.MARK_LOGO
    eigene[1]["mark"] = bild_id
    feste = [{"key": key, "on": True} for key in HOME_SECTIONS]
    for eintrag in feste:
        if eintrag["key"] == home.HERO_KEY:
            eintrag["title"] = "Tradition\nund Gemeinschaft"
            eintrag["kicker"] = "seit 1920"
    website.home_sections = home.validate(
        [*feste, *eigene[: home.MAX_CUSTOM]], website, HOME_SECTIONS, DEFAULT_HOME_OFF
    )
    website.save()

    erste = SiteView(website).units[0]
    zug = WebsiteText.objects.get(website=website, kind=WebsiteText.Kind.UNIT, department=erste)
    zug.published_sections = home.validate_unit(
        [*({"key": key, "on": True} for key in home.UNIT_BUILTINS), *eigene[home.MAX_CUSTOM :]],
        website,
    )
    zug.save()
    seite = WebsiteText.objects.get(website=website, slug="prueffest")
    seite.published_sections = home.validate_page(
        [
            {"key": "body", "on": True},
            {"key": "c:titel", "kind": "cover", "on": True, "data": daten["cover"]},
            eigene[0],
            {
                "key": "c:vogel",
                "kind": "competition",
                "on": True,
                "data": {
                    "title": "Vogelschießen",
                    "competition": Competition.objects.get(title="Prüfvogelschießen").pk,
                },
            },
        ],
        website,
    )
    seite.save()
    # Dieselben Arten karg belegt (ohne Bild, Ziel, Text …): zeigt, was fehlen darf
    karg = [{**e, "key": f"c:k{n}", "data": _karg(e["data"])} for n, e in enumerate(eigene)]
    for nummer in range(0, len(karg), home.MAX_CUSTOM):
        teile = home.validate_page(
            [{"key": "body", "on": True}, *karg[nummer : nummer + home.MAX_CUSTOM]], website
        )
        WebsiteText.objects.create(
            organization=website.organization,
            website=website,
            kind=WebsiteText.Kind.PAGE,
            slug=f"pruef-karg-{nummer}",
            title="Karg belegt",
            published_title="Karg belegt",
            show_in_menu=True,
            published_at=timezone.now(),
            # auch als Entwurf: die Vorschau zeigt Entwürfe und dort die Platzhalter für Bilder
            sections=teile,
            published_sections=teile,
        )


# Angaben, die ein Abschnitt weglassen kann
KANN_FEHLEN = {
    "after_text",
    "bic",
    "button",
    "caption",
    "goal",
    "holder",
    "iban",
    "image",
    "label",
    "line",
    "name",
    "purpose",
    "raised",
    "target",
    "text",
    "url",
}


def _karg(daten):
    """Derselbe Inhalt ohne alles, was fehlen kann (auch in den Einträgen von Listen)."""
    if isinstance(daten, list):
        return [_karg(eintrag) for eintrag in daten]
    if isinstance(daten, dict):
        return {k: _karg(v) for k, v in daten.items() if k not in KANN_FEHLEN}
    return daten


def menue(website: Website) -> None:
    """Menü mit allem: Link nach außen, freie Überschrift mit Seite und Link darunter,
    ein Punkt als Knopf, einer nur im Fuß."""
    from website import menu

    website.block_names = {
        **(website.block_names or {}),
        "link:1": "Shop",
        "link:2": "Verband",
        "heading:1": "Mehr",
    }
    website.menu_links = {
        "link:1": "https://shop.example.org",
        "link:2": "https://verband.example.org",
    }
    bekannt = menu.items(website)
    seite = next(k for k in bekannt if k.startswith("page:"))
    website.menu = [
        {"key": "heading:1", "children": [{"key": seite}, {"key": "link:1"}]},
        {"key": "contact", "children": []},
        {"key": "link:2", "children": []},
        {"key": "board", "children": []},
    ]
    website.menu_button = "contact"
    website.menu_places = {"board": "footer", "link:2": "both"}
    website.save()


def fuelle(website: Website) -> Website:
    grunddaten(website)
    personen(website)
    einheiten(website)
    wuerden(website)
    termine(website)
    chronik(website)
    ergebnisse(website)
    inhalte(website)
    mitmachen(website)
    abschnitte(website)
    menue(website)
    return website
