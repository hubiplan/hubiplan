"""Schlüssel je Zweck für Geheimnisse mit dem MFA-Schlüssel (Gesamtaudit 15.11., OPS-18).

Stufe 1: Die Fassung liest enc1 (bisher) und enc2 (je Zweck), schreibt aber weiter enc1, damit
der Rückweg auf die vorige Fassung offen bleibt. Erfundene Werte.
"""

import ast
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from accounts import mfa

BACKEND = Path(__file__).resolve().parent.parent
FUNCS = {"encrypt", "decrypt", "ensure_encrypted", "rotate"}


def test_stufe_1_schreibt_weiter_enc1():
    assert mfa.WRITE_PURPOSE_KEYS is False
    value = mfa.encrypt("geheim", purpose="nextcloud")
    assert value.startswith("enc1:")
    assert mfa.decrypt(value, purpose="nextcloud") == "geheim"


def test_enc2_nur_fuer_den_eigenen_zweck(monkeypatch):
    monkeypatch.setattr(mfa, "WRITE_PURPOSE_KEYS", True)
    totp = mfa.encrypt("JBSWY3DPEHPK3PXP", purpose="mfa")
    assert totp.startswith("enc2:mfa:")
    assert mfa.decrypt(totp, purpose="mfa") == "JBSWY3DPEHPK3PXP"
    with pytest.raises(ImproperlyConfigured):
        mfa.decrypt(totp, purpose="nextcloud")
    # Auch ein umetikettiertes Chiffrat hilft nicht: anderer Schlüssel
    umetikettiert = totp.replace("enc2:mfa:", "enc2:nextcloud:", 1)
    with pytest.raises(ImproperlyConfigured):
        mfa.decrypt(umetikettiert, purpose="nextcloud")
    assert mfa.rotate(totp, purpose="mfa").startswith("enc2:mfa:")


def test_unbekannter_zweck():
    with pytest.raises(ImproperlyConfigured):
        mfa.encrypt("x", purpose="irgendwas")


def _calls(tree, names, module_alias):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        target = None
        if isinstance(func, ast.Name) and func.id in names:
            target = node
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in FUNCS
            and isinstance(func.value, ast.Name)
            and func.value.id in module_alias
        ):
            target = node
        elif (
            isinstance(func, ast.Name)
            and func.id == "partial"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in names
        ):
            target = node
        if target is not None:
            yield target


def test_jeder_aufruf_nennt_genau_einen_bekannten_zweck():
    missing = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name == "mfa.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "accounts.mfa" not in text and "accounts import mfa" not in text:
            continue
        tree = ast.parse(text)
        names, alias = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "accounts.mfa":
                names |= {a.asname or a.name for a in node.names if a.name in FUNCS}
            if isinstance(node, ast.ImportFrom) and node.module == "accounts":
                alias |= {a.asname or a.name for a in node.names if a.name == "mfa"}
        for call in _calls(tree, names, alias):
            purpose = next((k.value for k in call.keywords if k.arg == "purpose"), None)
            if not isinstance(purpose, ast.Constant) or purpose.value not in mfa.PURPOSES:
                missing.append(f"{path.relative_to(BACKEND)}:{call.lineno}")
    assert missing == []
