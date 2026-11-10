"""Lizenzaudit 31.10.2026: Lizenzbeilagen und keine fremden Browserdateien ohne Hinweis."""

from pathlib import Path

from django.conf import settings
from rest_framework.settings import api_settings

BACKEND = Path(settings.BASE_DIR)


def test_api_antwortet_nur_mit_json():
    """L06: Ohne Browsable API gehen Bootstrap, jQuery und Font Awesome nicht an den Browser."""
    renderers = [r.__module__ + "." + r.__name__ for r in api_settings.DEFAULT_RENDERER_CLASSES]
    assert renderers == ["rest_framework.renderers.JSONRenderer"]


def test_dockerfile_sammelt_drf_dateien_nicht_ein():
    dockerfile = (BACKEND / "Dockerfile").read_text()
    assert "collectstatic" in dockerfile
    assert "--ignore rest_framework" in dockerfile


def test_keine_fremde_passwortliste_mehr():
    """L04 (31.10.) / L05 (10.11.): Die NCSC-Liste aus SecLists ist entfernt, weil die Rechte an
    der ursprünglichen Sammlung nicht belegt waren; es gilt Djangos eigene Liste."""
    assert not (BACKEND / "accounts" / "data").exists()
    names = [v["NAME"] for v in settings.AUTH_PASSWORD_VALIDATORS]
    assert "django.contrib.auth.password_validation.CommonPasswordValidator" in names
