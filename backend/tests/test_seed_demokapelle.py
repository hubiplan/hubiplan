"""Zweiter Demoverein: Musikkapelle mit Webseite in Blau und Gold (Testserver, alles erfunden)."""

import io

import pytest
from django.core.management import call_command

from accounts.models import User
from members.models import ContactDetails, ExitReason, HonoraryTitleAward, Membership
from music.models import Musician, Piece, Skill
from organizations import demo_kapelle, demo_korps
from organizations.models import Organization
from website import menu
from website.content_models import GalleryAlbum, WebsiteImage, WebsiteText
from website.models import DesignPackage, Website
from website.public import SiteView

pytestmark = [pytest.mark.django_db, pytest.mark.langsam]


def seed():
    out = io.StringIO()
    call_command("seed_demokapelle", password="Test-Passwort-123", stdout=out)
    return out.getvalue()


def test_kapelle_mit_musikern_vorstand_und_webseite():
    out = seed()
    club = Organization.objects.get(name=demo_kapelle.CLUB_NAME)
    assert club.type == "club" and club.parent.type == "platform"
    assert (club.primary_color, club.accent_color) == (demo_kapelle.BLUE, demo_kapelle.GOLD)
    assert Membership.objects.filter(organization=club).count() >= 40
    assert all(c.email.endswith(".test") for c in ContactDetails.objects.all())
    # Instrumente, Stücke, Ehrenmitglieder, Verstorbene im Archiv
    musicians = Musician.objects.filter(organization=club)
    assert musicians.count() >= 25
    assert Skill.objects.filter(musician__in=musicians, instrument="Tuba", primary=True).exists()
    assert Piece.objects.filter(organization=club).count() == len(demo_kapelle.PIECES)
    assert HonoraryTitleAward.objects.filter(organization=club).count() >= 2
    died = Membership.objects.filter(
        organization=club, periods__exit_reason=ExitReason.DEATH
    ).count()
    assert died >= 2
    # Webseite: Kopfbild, Galerie, Menü „Kapelle“, Vorstand mit Dirigent
    website = Website.objects.get(organization=club)
    assert WebsiteImage.objects.filter(website=website, header=True).count() == 1
    assert GalleryAlbum.objects.filter(website=website, published=True).count() == 3
    assert website.block_on("gallery") and not website.block_on("honors")
    assert website.block_names["group:history"] == "Kapelle"
    assert website.design == "classic"  # ohne eingespieltes Paket
    # Chronik ist der Bereich „Chronik“ (keine zweite Textseite), Ehrenmitglieder, Listen
    # und Gedenken unter „Mitglieder“
    assert not WebsiteText.objects.filter(website=website, slug="chronik").exists()
    nav = menu.public_nav(SiteView(website))
    kapelle = next(item for item in nav if item.get("label") == "Kapelle")
    assert [child.get("key") for child in kapelle.get("children", [])] == ["history", "offices"]
    assert [item.get("key") for item in nav if item.get("label") == "Chronik"] == []
    mitglieder = next(item for item in nav if item.get("label") == "Mitglieder")
    labels = [child.get("label") for child in mitglieder["children"]]
    assert labels[0] == "Vorstand" and labels[-3:] == ["Aktive", "Passive", "In Gedenken"]
    site = SiteView(website)
    names = " ".join(str(entry.get("name")) for entry in site.board())
    assert all(name in names for name in demo_kapelle.BOARD_POSITIONS)
    # Instrument unter dem Namen, Anschrift der Vorsitzenden, Gedenken mit Todesjahr
    holders = [h for entry in site.board() for h in entry["holders"]]
    assert any(h.get("instrument") for h in holders)
    assert sum(1 for h in holders if h.get("address")) >= 2
    assert all(m.get("died") for m in site.memorial()) and len(site.memorial()) >= 2
    assert "Passwort: Test-Passwort-123" not in out
    assert set(User.objects.values_list("email", flat=True)) == set(demo_kapelle.all_emails())


def test_wiederholbar_und_nimmt_eingespieltes_paket():
    call_command("seed_demoverein", password="Test-Passwort-123", stdout=io.StringIO())
    other = Membership.objects.filter(organization__name=demo_korps.CLUB_NAME).count()
    seed()
    club = Organization.objects.get(name=demo_kapelle.CLUB_NAME)
    count = Membership.objects.filter(organization=club).count()
    images = WebsiteImage.objects.filter(website__organization=club).count()
    DesignPackage.objects.create(key=demo_kapelle.DESIGN_PACKAGE, label="Kapelle", css="")
    seed()
    assert Membership.objects.filter(organization=club).count() == count
    assert WebsiteImage.objects.filter(website__organization=club).count() == images
    assert Membership.objects.filter(organization__name=demo_korps.CLUB_NAME).count() == other
    website = Website.objects.get(organization=club)
    assert website.design == demo_kapelle.DESIGN_PACKAGE
    assert website.design_packages.filter(key=demo_kapelle.DESIGN_PACKAGE).exists()
