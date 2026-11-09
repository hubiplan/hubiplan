"""Notendateien: MusicXML/MEI/ABC/MIDI prüfen, eigene Stimme ausliefern, PDF und MIDI setzen."""
# ruff: noqa: F811

import io
import zipfile

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from core.tenancy import tenant_context
from documents import notation
from documents.models import Document, DocumentVersion, Folder
from documents.services import check_upload
from music.models import ScoreDocument, ScorePart

from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_score_folders import setup  # noqa: F401

pytestmark = pytest.mark.django_db

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <work><work-title>Mustermarsch</work-title></work>
  <identification><creator type="composer">Max Muster</creator></identification>
  <part-list>
    <score-part id="P1"><part-name>Tenorhorn</part-name></score-part>
    <score-part id="P2"><part-name>Flöte</part-name></score-part>
  </part-list>
  <part id="P1"><measure number="1"><attributes><divisions>1</divisions>
    <time><beats>2</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>
    </attributes><note><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch>
    <duration>2</duration><type>half</type></note></measure></part>
  <part id="P2"><measure number="1"><attributes><divisions>1</divisions>
    <time><beats>2</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>
    </attributes><note><pitch><step>F</step><octave>5</octave></pitch>
    <duration>2</duration><type>half</type></note></measure></part>
</score-partwise>
"""
MIDI = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"


def _mxl(xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>',
        )
        z.writestr("score.xml", xml)
    return buf.getvalue()


def test_check_notation_files():
    assert check_upload(SimpleUploadedFile("marsch.musicxml", XML.encode()), notation=True) == (
        notation.MUSICXML
    )
    assert check_upload(SimpleUploadedFile("marsch.mxl", _mxl(XML)), notation=True) == notation.MXL
    assert check_upload(SimpleUploadedFile("marsch.mid", MIDI), notation=True) == notation.MIDI
    abc = b"X:1\nT:Muster\nK:C\nCDEF|\n"
    assert check_upload(SimpleUploadedFile("lied.abc", abc), notation=True) == notation.ABC
    with pytest.raises(ValidationError):
        check_upload(SimpleUploadedFile("marsch.musicxml", XML.encode()))  # nur in der Ablage
    with pytest.raises(ValidationError):
        check_upload(SimpleUploadedFile("anderes.xml", b"<html/>"), notation=True)
    with pytest.raises(ValidationError):
        check_upload(SimpleUploadedFile("marsch.mid", b"RIFFxxxx"), notation=True)
    bomb = '<!DOCTYPE x [<!ENTITY a "aaaa">]><score-partwise>&a;</score-partwise>'
    with pytest.raises(ValidationError):
        check_upload(SimpleUploadedFile("marsch.musicxml", bomb.encode()), notation=True)


def test_extract_and_guess_part():
    info = notation.musicxml_info(XML)
    assert info["title"] == "Mustermarsch" and info["composer"] == "Max Muster"
    assert [p["name"] for p in info["parts"]] == ["Tenorhorn", "Flöte"]
    assert notation.guess_part(info["parts"], "tenorhorn", "") == "P1"
    assert notation.find_part(info["parts"], "FLÖTE") == "P2"
    single = notation.extract_part(XML, "P1")
    assert [p["id"] for p in notation.musicxml_info(single)["parts"]] == ["P1"]
    assert "<step>F</step>" not in single


@pytest.fixture
def partitur(club, setup):
    """Eine MusicXML-Partitur, dem Tenorhorn zugeordnet (Stimme wird geraten)."""
    with tenant_context(club.pk):
        folder = Folder.objects.get(organization=club, name="Noten")
        document = Document.objects.create(organization=club, folder=folder, title="Partitur")
        version = DocumentVersion.objects.create(
            organization=club,
            document=document,
            name="mustermarsch.musicxml",
            size=len(XML),
            content_type=notation.MUSICXML,
            file=ContentFile(XML.encode(), name="mustermarsch.musicxml"),
        )
        part = ScorePart.objects.get(arrangement=setup["alte"], instrument="Tenorhorn")
        link = ScoreDocument.objects.create(
            organization=club, arrangement=setup["alte"], part=part, document=document
        )
    return link, version


def test_musician_gets_only_own_part_pdf_and_midi(api, club, setup, partitur):
    link, version = partitur
    client = api(setup["user"])
    url = f"/api/portal/{setup['access'].pk}/music/files/{link.pk}/"
    response = client.get(url)
    assert response.status_code == 200
    body = response.content.decode()
    assert "Tenorhorn" in body and "Flöte" not in body
    pdf = client.get(url + "?format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert pdf["ETag"] == f'"v{version.pk}-pdf"'
    assert client.get(url + "?format=pdf&transpose=-m3").status_code == 200
    assert client.get(url + "?format=pdf&transpose=x").status_code == 400
    midi = client.get(url + "?format=midi")
    assert midi.status_code == 200 and midi.content.startswith(b"MThd")
    folders = client.get(f"/api/portal/{setup['access'].pk}/music/folders/").json()
    row = next(s for i in folders["folders"][0]["items"] for s in i["scores"] if s["id"] == link.pk)
    assert row["notation"] == "musicxml" and row["formats"] == ["musicxml", "pdf", "midi"]
    practice = client.get(f"/api/portal/{setup['access'].pk}/music/practice/").json()
    assert any(s["url"] == url + "?format=pdf" for s in practice["scores"])


def test_unknown_part_gives_nothing(api, club, setup, partitur):
    link, _ = partitur
    with tenant_context(club.pk):
        link.part.instrument = "Tuba"
        link.part.save()
        # Der Musiker spielt auch Tuba, die Partitur hat aber keine Tubastimme
        setup["musician"].skills.create(organization=club, instrument="Tuba")
    url = f"/api/portal/{setup['access'].pk}/music/files/{link.pk}/"
    assert api(setup["user"]).get(url).status_code == 404


def test_choose_part_by_name(c, club, setup, partitur):
    link, _ = partitur
    base = f"/api/orgs/{club.pk}/music/score-documents/"
    info = c.get(base + f"notation/?document={link.document_id}").json()
    assert [p["name"] for p in info["parts"]] == ["Tenorhorn", "Flöte"]
    wrong = c.patch(f"{base}{link.pk}/", {"notation_part": "Posaune"}, content_type=JSON)
    assert wrong.status_code == 400 and "Flöte" in wrong.content.decode()
    ok = c.patch(f"{base}{link.pk}/", {"notation_part": "flöte"}, content_type=JSON)
    assert ok.status_code == 200, ok.content
    whole = c.get(f"{base}{link.pk}/download/")
    assert whole.status_code == 200 and "Tenorhorn" not in whole.content.decode()


def test_midi_is_audio_only(api, club, setup):
    with tenant_context(club.pk):
        folder = Folder.objects.get(organization=club, name="Noten")
        document = Document.objects.create(organization=club, folder=folder, title="Hörbeispiel")
        DocumentVersion.objects.create(
            organization=club,
            document=document,
            name="hoerbeispiel.mid",
            size=len(MIDI),
            content_type=notation.MIDI,
            file=ContentFile(MIDI, name="hoerbeispiel.mid"),
        )
        link = ScoreDocument.objects.create(
            organization=club, arrangement=setup["alte"], document=document
        )
    client = api(setup["user"])
    url = f"/api/portal/{setup['access'].pk}/music/files/{link.pk}/"
    assert client.get(url).content.startswith(b"MThd")
    assert client.get(url + "?format=pdf").status_code == 404
