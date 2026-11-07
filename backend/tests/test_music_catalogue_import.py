"""Preview is inert; signed imports are atomic, bounded and preserve existing stock."""
# ruff: noqa: F811

import csv
import io
import uuid

import pypdfium2 as pdfium
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.tenancy import tenant_context
from music.models import Arrangement, Piece, ScorePart

from .factories import give_role, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_scores import add, repertoire  # noqa: F401

pytestmark = pytest.mark.django_db


def csv_file(rows=None):
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(["title", "composer", "arrangement", "instrument", "copies", "license_note"])
    writer.writerows(
        rows or [["Musterstück", "A. Beispiel", "Konzertfassung", "Tuba", "2", "Nutzung prüfen"]]
    )
    return stream.getvalue().encode("utf-8-sig")


def upload(c, url, raw, action="preview", key=None, **extra):
    return c.post(
        url,
        {"action": action, "file": SimpleUploadedFile("noten.csv", raw), **extra},
        **({"HTTP_IDEMPOTENCY_KEY": key} if key else {}),
    )


def test_preview_import_retry_and_duplicates(c, club, music):
    base, _ = music
    url = base + "/catalogue-import/"
    raw = csv_file()
    preview = upload(c, url, raw).json()
    assert preview["valid"] and preview["counts"] == {"pieces": 1, "arrangements": 1, "parts": 1}
    with tenant_context(club.pk):
        assert not Piece.objects.filter(organization=club).exists()
    key = str(uuid.uuid4())
    args = {"digest": preview["digest"], "preview": preview["preview"]}
    result = upload(c, url, raw, "import", key, **args)
    assert result.status_code == 200, result.content
    assert upload(c, url, raw, "import", key, **args).status_code == 200
    with tenant_context(club.pk):
        assert Piece.objects.filter(organization=club).count() == 1
        assert ScorePart.objects.get(organization=club).copies == 2
    preview = upload(c, url, raw).json()
    assert preview["valid"] and preview["skipped"] == 1
    assert preview["counts"] == {"pieces": 0, "arrangements": 0, "parts": 0}


@pytest.mark.parametrize("change", ["file", "catalogue", "signature"])
def test_stale_or_forged_preview_is_rejected(c, club, music, change):
    url = music[0] + "/catalogue-import/"
    raw = csv_file()
    preview = upload(c, url, raw).json()
    if change == "file":
        raw += b"Muster Zwei;;Andere Fassung;Tuba;1;\n"
    elif change == "catalogue":
        with tenant_context(club.pk):
            Piece.objects.create(organization=club, title="Zwischenzeitlich angelegt")
    else:
        preview["preview"] += "ungueltig"
    response = upload(
        c,
        url,
        raw,
        "import",
        str(uuid.uuid4()),
        digest=preview["digest"],
        preview=preview["preview"],
    )
    assert response.status_code == 400
    with tenant_context(club.pk):
        assert not Arrangement.objects.filter(organization=club).exists()


def test_conflicting_stock_and_later_invalid_row_save_nothing(c, club, music):
    url = music[0] + "/catalogue-import/"
    raw = csv_file()
    preview = upload(c, url, raw).json()
    assert (
        upload(
            c,
            url,
            raw,
            "import",
            str(uuid.uuid4()),
            digest=preview["digest"],
            preview=preview["preview"],
        ).status_code
        == 200
    )
    changed = csv_file(
        [
            ["Musterstück", "A. Beispiel", "Konzertfassung", "Tuba", "9", "Nutzung prüfen"],
            ["Neu", "", "Neue Ausgabe", "", "", ""],
        ]
    )
    result = upload(c, url, changed).json()
    assert not result["valid"] and result["errors"]
    assert (
        upload(
            c, url, changed, "import", str(uuid.uuid4()), digest="unpassend", preview="ungueltig"
        ).status_code
        == 400
    )
    with tenant_context(club.pk):
        assert ScorePart.objects.get(organization=club).copies == 2
        assert Piece.objects.filter(organization=club).count() == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"title;arrangement\nTitel\n",
        b"falsch;arrangement\nX;Y\n",
        b"title;arrangement\n\xff;X",
        b"title;arrangement\nX;Y\x00",
        b"title;arrangement\n" + b"X;Y\n" * 1001,
    ],
)
def test_malformed_and_overlong_files(c, music, raw):
    result = upload(c, music[0] + "/catalogue-import/", raw)
    assert result.status_code == 200 and not result.json()["valid"]


def test_read_only_and_module_limits(c, api, club, music):
    url = music[0] + "/catalogue-import/"
    user = make_user("notenkatalog@example.org")
    give_role(user, club, permissions=["scores.view"], name="Notenkatalog lesen")
    assert api(user).get(url).status_code == 200
    assert upload(api(user), url, csv_file()).status_code == 403
    # Ohne Musik bleibt der Import (Modul „Notenarchiv“), ohne Notenarchiv nicht
    club.enabled_modules.remove("music")
    club.save()
    assert c.get(url).status_code == 200
    club.enabled_modules.remove("scores")
    club.save()
    assert c.get(url).status_code == 404


@pytest.mark.parametrize(
    "kind, expected", [("program", "Programmliste"), ("parts", "Stimmenliste")]
)
def test_printable_pdf_exports_keep_csv(c, club, repertoire, kind, expected):
    base, performance, arrangement = repertoire
    url = f"{base}/performances/{performance.pk}/program/"
    assert add(c, url, arrangement).status_code == 200
    response = c.get(url, {"export": kind, "filetype": "pdf"})
    assert response.status_code == 200, response.content[:100]
    assert (
        response["Content-Type"] == "application/pdf"
        and response["Cache-Control"] == "private, no-store"
    )
    with pdfium.PdfDocument(response.content) as document:
        page = document[0]
        text = page.get_textpage()
        try:
            content = text.get_text_range()
            assert expected in content and "=Musterlied" in content
        finally:
            text.close()
            page.close()
    assert c.get(url, {"export": kind})["Content-Type"].startswith("text/csv")
