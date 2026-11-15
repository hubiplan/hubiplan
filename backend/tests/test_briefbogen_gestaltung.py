"""Briefbogen nach eigenem Styleguide (Issue #470): Linien, Kopf, Logo, Schriften, Tabellen.

Alles erfunden; die Grundwerte müssen genau das bisherige Aussehen ergeben."""

import io
import zipfile

import pytest
from PIL import Image

from letterhead import data as service
from letterhead import docx, pdf, preview
from letterhead.models import Letterhead
from letterhead.pdf import table_colors

from .factories import give_role, make_user
from .test_briefvorlage import club, zug  # noqa: F401

JSON = "application/json"


def word_parts(data) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(docx.build(data, "docx"))) as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml")}


def letter_pdf(data) -> bytes:
    from reportlab.platypus import Paragraph

    buf = io.BytesIO()
    st = pdf.text_styles(data)
    story = pdf.LetterDocument.start(data, ["Erika Muster", "Musterweg 2"], [("Datum", "1")], True)
    story.append(Paragraph("Rechnung <b>fett</b> äöü €", st["title"]))
    pdf.LetterDocument(buf, [data]).build(story)
    return buf.getvalue()


@pytest.fixture
def colored(club):  # noqa: F811
    club.primary_color = "#1d5c3a"
    club.accent_color = "#fbc707"
    club.extra_colors = [{"color": "#8b1e2d", "name": "Weinrot"}]
    club.save()
    return club


class TestGrundwerte:
    def test_wie_bisher(self, colored):
        lh = service.ensure(colored)
        data = service.letter_data(colored)
        assert data.line_color == "#fbc707"  # Zweitfarbe wie bisher
        assert data.head_line and data.footer_line and data.show_name
        assert data.heading_font == lh.font == "Arial"
        assert data.title_color == "#000000"
        assert data.table_line_color == "#1d5c3a"
        assert data.table_stripe == "#f4f5f4"
        assert pdf.fonts(data.heading_font) == ("Helvetica", "Helvetica-Bold")
        assert docx.logo_box(data) == (55, 25)

    def test_pruefwerte_bleiben(self, colored):
        # Bestehende Vorlagen melden nicht „veraltet“, nur weil es neue Regler gibt
        data = service.letter_data(colored)
        assert len(service.section_values(data)["design"]) == 7
        before = service.checksums(data)
        lh = service.ensure(colored)
        lh.line_color = "2"
        lh.save()
        after = service.checksums(service.letter_data(colored))
        assert after["design"] != before["design"]

    def test_word_ohne_ersatzschrift(self, colored):
        xml = word_parts(service.letter_data(colored))
        assert "altName" not in xml["word/fontTable.xml"]
        assert 'w:color="FBC707"' in xml["word/header1.xml"]
        assert "majorHAnsi" not in xml["word/styles.xml"].split('w:styleId="Betreff"')[1][:400]


class TestGestaltung:
    def test_linien_und_farben(self, colored):
        lh = service.ensure(colored)
        lh.line_color, lh.title_color = "2", "primary"
        lh.table_line_color, lh.table_stripe = "2", "0"
        lh.save()
        data = service.letter_data(colored)
        assert data.line_color == "#8b1e2d"
        assert data.title_color == "#1d5c3a"
        line, stripes = table_colors(data)
        assert line.hexval().lower() == "0x8b1e2d"
        assert len(stripes) == 2 and stripes[1].hexval().lower() != "0xf4f5f4"
        xml = word_parts(data)
        assert 'w:color="8B1E2D"' in xml["word/header1.xml"]
        assert 'w:color="8B1E2D"' in xml["word/footer1.xml"]
        assert (
            '<w:color w:val="1D5C3A"/>'
            in xml["word/styles.xml"].split('w:styleId="Betreff"')[1][:400]
        )

    def test_fehlender_platz_faellt_zurueck(self, colored):
        lh = service.ensure(colored)
        lh.line_color, lh.table_stripe = "5", "none"
        lh.save()
        data = service.letter_data(colored)
        assert data.line_color == "#fbc707"
        assert data.table_stripe is None
        assert len(table_colors(data)[1]) == 1

    def test_ohne_linien(self, colored):
        lh = service.ensure(colored)
        lh.head_line = lh.footer_line = False
        lh.save()
        xml = word_parts(service.letter_data(colored))
        assert "FBC707" not in xml["word/header1.xml"]
        assert "FBC707" not in xml["word/header2.xml"]
        assert "FBC707" not in xml["word/footer1.xml"]

    def test_name_neben_logo_aus(self, colored, tmp_path, settings):
        logo = tmp_path / "wappen.png"
        Image.new("RGB", (30, 40), (20, 90, 60)).save(logo)
        lh = service.ensure(colored)
        lh.show_name, lh.logo_size = False, "large"
        lh.save()
        data = service.letter_data(colored)
        assert data.show_name is True  # ohne Logo bleibt der Name
        data.logo = str(logo)
        assert data.show_name is False
        assert docx.logo_box(data) == (75, 33)
        xml = word_parts(data)
        assert colored.name not in xml["word/header1.xml"]
        assert colored.name in xml["word/header2.xml"]  # Folgeseiten nennen den Namen
        assert letter_pdf(data).startswith(b"%PDF")

    def test_webschriften(self, colored):
        lh = service.ensure(colored)
        lh.font, lh.heading_font = "Source Sans 3", "Crimson Pro"
        lh.font_fallback, lh.heading_font_fallback = "Verdana", "Cambria"
        lh.save()
        data = service.letter_data(colored)
        content = letter_pdf(data)
        assert b"CrimsonPro" in content and b"SourceSans3" in content
        assert preview.render(data).startswith(b"%PDF")
        xml = word_parts(data)
        fonts = xml["word/fontTable.xml"]
        assert 'w:name="Source Sans 3"><w:altName w:val="Verdana"/>' in fonts
        assert 'w:name="Crimson Pro"><w:altName w:val="Cambria"/>' in fonts
        assert '<a:majorFont><a:latin typeface="Crimson Pro"/>' in xml["word/theme/theme1.xml"]
        assert '<a:minorFont><a:latin typeface="Source Sans 3"/>' in xml["word/theme/theme1.xml"]

    def test_fraktur_ohne_fetten_schnitt(self, colored):
        lh = service.ensure(colored)
        lh.heading_font = "UnifrakturMaguntia"
        lh.save()
        data = service.letter_data(colored)
        regular, bold = pdf.fonts("UnifrakturMaguntia")
        assert regular == bold
        assert b"UnifrakturMaguntia" in letter_pdf(data)


class TestSchnittstelle:
    def test_pflege_und_hinweise(self, api, colored, board_a):
        c = api(board_a)
        url = f"/api/orgs/{colored.pk}/letterhead/"
        state = c.get(url).json()
        assert [p["slot"] for p in state["palette"]] == [0, 1, 2]
        # Gelb auf Weiß: Hinweis zum Kontrast
        assert any("Linienfarbe" in h for h in state["hints"])
        resp = c.patch(
            url,
            {
                "line_color": "0",
                "logo_size": "small",
                "show_name": False,
                "heading_font": "Oswald",
                "title_color": "primary",
                "table_stripe": "none",
            },
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        assert not any("Linienfarbe" in h for h in resp.json()["hints"])
        lh = Letterhead.objects.get(organization=colored)
        assert (lh.line_color, lh.logo_size, lh.show_name, lh.heading_font) == (
            "0",
            "small",
            False,
            "Oswald",
        )
        for bad in ({"line_color": "9"}, {"heading_font": "Comic Sans"}, {"table_stripe": "x"}):
            assert c.patch(url, bad, content_type=JSON).status_code == 400

    def test_untereinheit_eigene_einstellung(self, api, colored, zug, board_a):  # noqa: F811
        zug.own_workspace = True
        zug.save()
        c = api(board_a)
        url = f"/api/orgs/{colored.pk}/letterhead/units/{zug.pk}/"
        resp = c.patch(url, {"mode": "own", "line_color": "2"}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert service.letter_data(zug).line_color == "#8b1e2d"
        assert service.letter_data(colored).line_color == "#fbc707"

    def test_ohne_schreibrecht(self, api, colored):
        user = make_user("leser-bogen@example.org")
        give_role(user, colored, permissions=["settings.view"], name="Leser")
        resp = api(user).patch(
            f"/api/orgs/{colored.pk}/letterhead/", {"line_color": "0"}, content_type=JSON
        )
        assert resp.status_code == 403
