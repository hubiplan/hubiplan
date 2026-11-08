"""PDF-Absätze: Markup aus Benutzertext wirkt nicht (Gesamtaudit 08.11.2026, GA8-01/GA8-02)."""

import ast
import io
import pathlib

import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate
from rest_framework.test import APIClient

from .test_wettbewerbe import club, url  # noqa: F401

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _pdf(text: str) -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(buf).build([Paragraph(text, getSampleStyleSheet()["Normal"])])
    return buf.getvalue()


def test_bilder_in_absaetzen_werden_ignoriert(tmp_path):
    from PIL import Image

    bild = tmp_path / "bild.png"
    Image.new("RGB", (8, 8), "red").save(bild)
    pdf = _pdf(f'Text<img src="{bild}" width="8" height="8"/>')
    assert b"/Subtype /Image" not in pdf
    pdf = _pdf('Text<img src="http://127.0.0.1:9/probe" width="1" height="1"/>')
    assert b"/Subtype /Image" not in pdf


@pytest.mark.parametrize(
    "markup",
    [
        '<a href="javascript:alert(1)">Klick</a>',
        '<link href="file:///etc/hostname">Klick</link>',
        '<a href="data:text/html,x">Klick</a>',
    ],
)
def test_nur_sichere_verweise(markup):
    assert b"/URI" not in _pdf(markup)


def test_https_und_mailto_bleiben_verweise():
    assert b"https://example.org" in _pdf('<a href="https://example.org">Seite</a>')
    assert b"mailto:info@example.org" in _pdf('<a href="mailto:info@example.org">Mail</a>')


def _join_ohne_escape(node) -> list[str]:
    """Formatierte Werte ``{', '.join(…)}`` in Absatztexten müssen maskiert sein."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.FormattedValue):
            v = n.value
            if (
                isinstance(v, ast.Call)
                and isinstance(v.func, ast.Attribute)
                and v.func.attr == "join"
            ):
                out.append(ast.unparse(v))
    return out


def test_absatztexte_maskieren_listen():
    funde = []
    for path in BACKEND.rglob("*.py"):
        if {"tests", "migrations"} & set(path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Call)
                and getattr(n.func, "id", getattr(n.func, "attr", "")) == "Paragraph"
                and n.args
            ):
                funde += [
                    f"{path.relative_to(BACKEND)}:{n.lineno}: {x}"
                    for x in _join_ohne_escape(n.args[0])
                ]
    assert not funde, "\n".join(funde)


@pytest.mark.django_db(transaction=True)
def test_gastname_mit_markup_im_stechen(club, board_a, api):  # noqa: F811
    c = api(board_a)
    resp = c.post(
        url(club),
        {"title": "Preisschießen", "date": "2027-06-14", "template": "einfach"},
        "application/json",
    )
    assert resp.status_code == 201, resp.content
    comp_id = resp.json()["id"]
    scoring = c.get(url(club, f"{comp_id}/")).json()["scorings"][0]["id"]
    token = c.post(
        url(club, f"{comp_id}/stand-access/"), {"label": "Tablet"}, "application/json"
    ).json()["token"]
    namen = [
        'Gerd<img src="/etc/hostname" width="1" height="1"/>',
        '<a href="javascript:alert(1)">Hans</a> <b>offen',
    ]
    ops = [
        {
            "op": "starter",
            "client_key": f"00000000-0000-4000-8000-00000000000{i}",
            "name": n,
            "club": "Gastverein",
        }
        for i, n in enumerate(namen, 1)
    ]
    resp = APIClient().post(f"/api/public/stand/{token}/sync/", {"ops": ops}, format="json")
    assert resp.status_code == 200, resp.content
    starters = c.get(url(club, f"{comp_id}/starters/")).json()
    starters = starters.get("results", starters) if isinstance(starters, dict) else starters
    assert len(starters) == 2
    for s in starters:
        resp = c.put(
            url(club, f"{comp_id}/scores/"),
            {"scoring": scoring, "starter": s["id"], "value": "27"},
            "application/json",
        )
        assert resp.status_code in (200, 201), resp.content
    resp = c.get(url(club, f"{comp_id}/export/") + "?als=pdf")
    assert resp.status_code == 200
    pdf = resp.content
    assert pdf.startswith(b"%PDF")
    assert b"/URI" not in pdf
    assert b"/Subtype /Image" not in pdf
