"""Fachfrage 10 zum Gesamtaudit 10.11.: Entferntes ist nach höchstens 15 Minuten weg."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("path", ["website/public_views.py", "events/views.py"])
def test_oeffentliche_antworten_hoechstens_15_minuten(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    ages = [int(a) for a in re.findall(r'"public, max-age=(\d+)"', text)]
    assert ages and max(ages) <= 15 * 60
