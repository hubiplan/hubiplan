"""Name im Briefkopf: eigener Umbruch und kein verwaistes Wort (Issue #487). Alles erfunden."""

from __future__ import annotations

import pytest
from reportlab.pdfbase.pdfmetrics import stringWidth

from letterhead import data as service
from letterhead.headname import MIN_ONE_LINE, head_lines
from letterhead.models import Letterhead

from .test_briefbogen_gestaltung import letter_pdf, word_parts
from .test_briefvorlage import club  # noqa: F401

pytestmark = pytest.mark.django_db

JSON = "application/json"
LONG = "Musterschützen-Bruderschaft Musterstadt-Beispielhausen von 1920"
# zu lang für die ganze Textbreite ohne Logo
LONGER = "Musterschützen-Bruderschaft Musterstadt-Beispielhausen-Nord und Umgebung von 1920 e. V."
# Platz neben einem mittleren Logo: 170 mm Textbreite − 55 mm Logo − 6 mm Abstand
BESIDE_LOGO = 109


class TestUmbruch:
    def test_kurzer_name_wie_bisher(self):
        (line,) = head_lines("TV Beispielhausen", "", "Arial", BESIDE_LOGO)
        assert (line.text, line.size) == ("TV Beispielhausen", 16)

    def test_langer_name_erst_kleiner(self):
        name = "Schützenbruderschaft Musterstadt 1920 e. V."
        (line,) = head_lines(name, "", "Arial", BESIDE_LOGO)
        assert MIN_ONE_LINE <= line.size <= 16

    def test_ausgewogen_ohne_verwaistes_wort(self):
        lines = head_lines(LONG, "", "Arial", BESIDE_LOGO)
        assert len(lines) == 2
        assert " ".join(line.text for line in lines) == LONG
        assert lines[1].text != "1920" and len(lines[1].text.split()) > 1
        assert lines[0].size == lines[1].size
        widths = [stringWidth(line.text, "Helvetica-Bold", line.size) for line in lines]
        assert max(widths) <= BESIDE_LOGO / 25.4 * 72
        assert min(widths) / max(widths) > 0.6

    def test_ein_einzelnes_langes_wort_bleibt_eine_zeile(self):
        (line,) = head_lines("A" * 60, "", "Arial", BESIDE_LOGO)
        assert line.size < MIN_ONE_LINE

    def test_eigene_zeilen(self):
        own = "  Musterschützen-Bruderschaft \n\n Musterstadt-Beispielhausen von 1920 "
        lines = head_lines(LONG, own, "Georgia", BESIDE_LOGO)
        assert [line.text for line in lines] == [
            "Musterschützen-Bruderschaft",
            "Musterstadt-Beispielhausen von 1920",
        ]
        assert lines[0].size == lines[1].size
        small = head_lines(LONG, own, "Georgia", BESIDE_LOGO, small_second=True)
        assert small[1].size < small[0].size

    def test_webschrift(self):
        lines = head_lines(LONG, "", "Crimson Pro", BESIDE_LOGO)
        assert " ".join(line.text for line in lines) == LONG


class TestBrief:
    def test_word_und_pdf_gleich(self, club):  # noqa: F811
        club.name = LONGER
        club.save()
        data = service.letter_data(club)
        header = word_parts(data)["word/header1.xml"]
        lines = data.head_lines(170, reserve=0.95)
        assert len(lines) == 2
        for line in lines:
            assert f">{line.text}</w:t>" in header
        assert f'<w:sz w:val="{round(lines[0].size * 2)}"/>' in header
        assert letter_pdf(data).startswith(b"%PDF")
        # Folgeseiten behalten den vollen Namen
        assert f">{LONGER}</w:t>" in word_parts(data)["word/header2.xml"]

    def test_eigener_name(self, club):  # noqa: F811
        lh = service.ensure(club)
        lh.head_name = "TV Beispielhausen\nvon 1900"
        lh.head_name_small = True
        lh.save()
        data = service.letter_data(club)
        header = word_parts(data)["word/header1.xml"]
        assert ">TV Beispielhausen</w:t>" in header and ">von 1900</w:t>" in header
        assert letter_pdf(data).startswith(b"%PDF")

    def test_pruefwerte_bleiben_ohne_eigenen_namen(self, club):  # noqa: F811
        data = service.letter_data(club)
        before = service.checksums(data)
        assert service.checksums(service.letter_data(club)) == before
        lh = service.ensure(club)
        lh.head_name = "TV\nBeispielhausen"
        lh.save()
        assert service.checksums(service.letter_data(club))["design"] != before["design"]


class TestSchnittstelle:
    def test_speichern_und_pruefen(self, api, club, board_a):  # noqa: F811
        c = api(board_a)
        url = f"/api/orgs/{club.pk}/letterhead/"
        resp = c.patch(url, {"head_name": "  Eins \n\n Zwei  "}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["letterhead"]["head_name"] == "Eins\nZwei"
        assert Letterhead.objects.get(organization=club).head_name == "Eins\nZwei"
        resp = c.patch(url, {"head_name": "Eins\nZwei\nDrei"}, content_type=JSON)
        assert resp.status_code == 400


def png(size=(500, 100), color=(18, 62, 122, 255)):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return SimpleUploadedFile("marke.png", buf.getvalue(), content_type="image/png")


class TestEigenesLogo:
    """Eigenes Logo nur für den Briefbogen (Issue #488)."""

    @pytest.fixture(autouse=True)
    def media(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path / "media"

    def test_hochladen_und_entfernen(self, api, club, board_a):  # noqa: F811
        from django.core.files.base import ContentFile

        from letterhead.data import logo_path

        club.logo.save("wappen.png", ContentFile(png((100, 120)).read()), save=True)
        c = api(board_a)
        url = f"/api/orgs/{club.pk}/letterhead/logo/"
        resp = c.post(url, {"logo": png()})
        assert resp.status_code == 200, resp.json()
        assert resp.json()["logo_url"]
        lh = Letterhead.objects.get(organization=club)
        assert service.letter_data(club).logo == lh.logo.path
        # Erscheinungsbild und Urkunden behalten das Wappen
        assert logo_path(club) == club.logo.path
        old = lh.logo.path
        assert c.post(url, {"logo": png()}).status_code == 200
        import os

        assert not os.path.exists(old)
        resp = c.delete(url)
        assert resp.status_code == 200 and resp.json()["logo_url"] is None
        assert service.letter_data(club).logo == club.logo.path

    def test_untereinheiten(self, api, club, board_a):  # noqa: F811
        from core.tenancy import tenant_context
        from organizations.models import Department

        with tenant_context(club.pk):
            zug = Department.objects.create(organization=club, name="Jägerzug", own_workspace=True)
        c = api(board_a)
        assert c.post(f"/api/orgs/{club.pk}/letterhead/logo/", {"logo": png()}).status_code == 200
        club_logo = Letterhead.objects.get(organization=club).logo.path
        # Übernimmt den Briefbogen: erbt das Logo, kein eigenes
        assert service.letter_data(zug).logo == club_logo
        url = f"/api/orgs/{club.pk}/letterhead/units/{zug.pk}/logo/"
        assert c.post(url, {"logo": png()}).status_code == 400
        c.patch(
            f"/api/orgs/{club.pk}/letterhead/units/{zug.pk}/",
            {"mode": "own"},
            content_type=JSON,
        )
        assert c.post(url, {"logo": png()}).status_code == 200
        assert service.letter_data(zug).logo == Letterhead.objects.get(organization=zug).logo.path
        assert service.letter_data(club).logo == club_logo

    def test_ohne_schreibrecht(self, api, club):  # noqa: F811
        from .factories import give_role, make_user

        user = make_user("leser-logo@example.org")
        give_role(user, club, permissions=["settings.view"], name="Leser")
        resp = api(user).post(f"/api/orgs/{club.pk}/letterhead/logo/", {"logo": png()})
        assert resp.status_code == 403
