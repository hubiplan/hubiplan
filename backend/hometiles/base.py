"""Gemeinsamer Rahmen der Kacheln: Aufbau einer Kachel, Auswahl der Person, Texte."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone, translation
from django.utils.translation import gettext

from accounts.home_actions import layout_of

logger = logging.getLogger(__name__)

AUTO, ON, OFF = "auto", "on", "off"
STATES = (AUTO, ON, OFF)


@dataclass
class Figure:
    label: str
    value: str
    # None | "good" | "warn" | "bad"
    tone: str | None = None

    def data(self) -> dict:
        return {"label": self.label, "value": self.value, "tone": self.tone}


@dataclass
class Row:
    title: str
    detail: str = ""
    link: str | None = None
    tone: str | None = None

    def data(self) -> dict:
        return {"title": self.title, "detail": self.detail, "link": self.link, "tone": self.tone}


@dataclass
class Content:
    """Inhalt einer Kachel. ``reason``: aktueller Anlass; dann erscheint sie auch ungefragt."""

    figures: list[Figure] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    text: str = ""
    link: str | None = None
    link_label: str = ""
    reason: str = ""

    def data(self) -> dict:
        return {
            "figures": [f.data() for f in self.figures],
            "rows": [r.data() for r in self.rows],
            "text": self.text,
            "link": self.link,
            "link_label": self.link_label,
            "reason": self.reason,
        }


@dataclass
class Tile:
    key: str
    title: Callable[[], str]
    description: Callable[[], str]
    # (Kontext) -> bool: Darf die Person die Kachel haben (Modul, Rechte)?
    available: Callable[[object], bool]
    # (Kontext) -> Content | None
    build: Callable[[object], Content | None]
    # (Kontext) -> bool: bei „bei Anlass“ auch ohne Anlass zeigen (z. B. reines Kassenbuch)
    default_on: Callable[[object], bool] | None = None


def state_of(user, scope: str, key: str) -> str:
    layout = layout_of(user).get(scope) or {}
    if key in (layout.get("shown") or []):
        return ON
    if key in (layout.get("hidden") or []):
        return OFF
    return AUTO


def set_state(user, scope: str, key: str, state: str) -> None:
    """Auswahl einer Kachel speichern, ohne die übrige Anordnung zu berühren."""
    from accounts.home_actions import _clean_layout

    data = dict(user.home_layout) if isinstance(user.home_layout, dict) else {}
    layout = _clean_layout(data.get(scope) or {}) if isinstance(data.get(scope), dict) else None
    if layout is None:
        layout = {"order": [], "hidden": [], "wide": [], "shown": [], "sizes": {}}
    shown = [k for k in layout["shown"] if k != key]
    hidden = [k for k in layout["hidden"] if k != key]
    if state == ON:
        shown.append(key)
    elif state == OFF:
        hidden.append(key)
    layout["shown"], layout["hidden"] = shown, hidden
    data[scope] = layout
    user.home_layout = data
    user.save(update_fields=["home_layout"])


def run(tiles: list[Tile], ctx, user, scope: str, keys: set[str] | None = None) -> list[dict]:
    """Alle Kacheln, die die Person haben darf, mit Auswahl und Inhalt (nicht bei „nie“).

    ``keys``: nur diese Kacheln."""
    out = []
    for tile in tiles:
        if keys is not None and tile.key not in keys:
            continue
        try:
            if not tile.available(ctx):
                continue
        except Exception:  # pragma: no cover - eine Kachel darf die Startseite nie sprengen
            logger.exception("Kachel %s: Prüfung fehlgeschlagen", tile.key)
            continue
        state = state_of(user, scope, tile.key)
        content = None
        if state != OFF:
            try:
                content = tile.build(ctx)
            except Exception:  # pragma: no cover
                logger.exception("Kachel %s: Inhalt fehlgeschlagen", tile.key)
                content = None
        reason = content.reason if content else ""
        always = False
        if tile.default_on is not None:
            try:
                always = bool(tile.default_on(ctx))
            except Exception:  # pragma: no cover
                logger.exception("Kachel %s: Vorgabe fehlgeschlagen", tile.key)
        out.append(
            {
                "key": tile.key,
                "title": tile.title(),
                "description": tile.description(),
                "state": state,
                "urgent": bool(reason),
                "default_on": always,
                "shown": state == ON or (state == AUTO and (bool(reason) or always)),
                "content": content.data() if content else None,
            }
        )
    return out


# --- Texte -----------------------------------------------------------------------------------


def today() -> datetime.date:
    return timezone.localdate()


def day_text(value: datetime.date) -> str:
    from core.i18n import date_text

    return date_text(value)


def when_text(value: datetime.datetime) -> str:
    """„Mo., 23.11. 18:00“ bzw. „Mon 23/11 18:00“ für Zeilen."""
    local = timezone.localtime(value)
    if translation.get_language() == "en":
        return f"{local:%a %d/%m %H:%M}"
    days = ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."]
    return f"{days[local.weekday()]} {local:%d.%m. %H:%M}"


def euro(value: Decimal) -> str:
    text = f"{value:,.2f}"
    if translation.get_language() != "en":
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def count(n: int) -> str:
    text = f"{n:,}"
    return text if translation.get_language() == "en" else text.replace(",", ".")


def hours(value: Decimal) -> str:
    text = f"{value.quantize(Decimal('0.01')):f}".rstrip("0").rstrip(".") or "0"
    if translation.get_language() != "en":
        text = text.replace(".", ",")
    return gettext("{h} Std.").format(h=text)
