"""Zugriffslog von gunicorn ohne Geheimnisse im Pfad (Gesamtaudit 19.11., S-15).

Öffentliche Links tragen ihr Geheimnis im Pfad (Scan- und Kassen-Links, Zusagen, eigene
Anmeldung, Abmelde-Links …). Das Zugriffslog nennt deshalb nur die Route: Pfadteile, die
die Route als ``token`` führt, und unter ``/public/`` auch ``key``, erscheinen als „…“.
Nummern und feste Pfadteile bleiben lesbar. Eingebunden in ``gunicorn.conf.py``.
"""

from __future__ import annotations

from gunicorn.glogging import Logger

HIDDEN = "…"
# Unbekannte Adressen unter /public/ (vertippte oder abgelaufene Links): lange Teile kürzen
LONG = 16


def log_path(path: str | None) -> str | None:
    """Pfad fürs Zugriffslog; darf nie eine Ausnahme werfen."""
    if not path:
        return path
    try:
        return _log_path(path)
    except Exception:  # noqa: BLE001 – das Log darf keine Anfrage stören
        return _shorten(path, all_public=True)


def _log_path(path: str) -> str:
    from django.urls import Resolver404, resolve

    try:
        match = resolve(path)
    except Resolver404:
        return _shorten(path)
    public = "/public/" in path
    secrets = {
        str(value)
        for name, value in match.kwargs.items()
        if name == "token" or (public and name == "key")
    }
    if not secrets:
        return path
    return "/".join(HIDDEN if part in secrets else part for part in path.split("/"))


def _shorten(path: str, *, all_public: bool = False) -> str:
    """Ohne Route: unter /public/ lange Pfadteile kürzen (im Fehlerfall alle dahinter)."""
    head, sep, tail = path.partition("/public/")
    if not sep:
        return path
    parts = tail.split("/")
    if all_public:
        parts = [parts[0]] + [HIDDEN if part else part for part in parts[1:]]
    else:
        parts = [HIDDEN if len(part) >= LONG else part for part in parts]
    return head + sep + "/".join(parts)


class AccessLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        atoms["U"] = log_path(atoms.get("U"))
        # Die Rohzeile enthielte Pfad und Abfrage ungekürzt; sie steht in keinem Format,
        # soll aber auch mit GUNICORN_CMD_ARGS nicht versehentlich hineingeraten.
        atoms["r"] = f"{atoms.get('m')} {atoms['U']} {atoms.get('H')}"
        return atoms
