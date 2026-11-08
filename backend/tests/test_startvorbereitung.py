"""Startvorbereitung in einem Prozess (konzepte/ausfallzeiten-ausrollen.md)."""

from unittest import mock

from django.core.management import call_command


def _aufrufe(monkeypatch, loeschliste: str | None):
    if loeschliste is None:
        monkeypatch.delenv("LOESCHLISTE_PATH", raising=False)
    else:
        monkeypatch.setenv("LOESCHLISTE_PATH", loeschliste)
    with mock.patch("core.management.commands.startvorbereitung.call_command") as aufruf:
        call_command("startvorbereitung", verbosity=0)
    return [c.args[0] for c in aufruf.call_args_list]


def test_reihenfolge_mit_loeschliste(monkeypatch):
    assert _aufrufe(monkeypatch, "/app/loeschliste/loeschliste.jsonl") == [
        "migrate",
        "ensure_app_role",
        "loeschliste_anwenden",
    ]


def test_ohne_loeschliste(monkeypatch):
    assert _aufrufe(monkeypatch, None) == ["migrate", "ensure_app_role"]
