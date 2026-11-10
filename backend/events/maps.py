"""Anfahrt: Links zu OpenStreetMap und Google Maps (T5).

Nur Links, keine eingebettete Karte: Eine Karte lädt Kacheln von fremden Servern.
Mit genauem Punkt (Breite/Länge) führt der Link dorthin, sonst sucht er die Anschrift.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode


def destination(location: str, address: str) -> str:
    return ", ".join(x for x in (location.strip(), address.strip()) if x)


def links(location: str, address: str, latitude, longitude) -> dict[str, str]:
    """``{"osm": …, "google": …}``; leer, wenn es weder Punkt noch Anschrift gibt."""
    if latitude is not None and longitude is not None:
        point = f"{float(latitude):.5f},{float(longitude):.5f}"
        return {
            "osm": f"https://www.openstreetmap.org/directions?route=%3B{quote(point)}",
            "google": "https://www.google.com/maps/dir/?"
            + urlencode({"api": "1", "destination": point}),
        }
    # Ohne Anschrift sagt der Name des Orts allein meist zu wenig
    if not address.strip():
        return {}
    text = destination(location, address)
    return {
        "osm": "https://www.openstreetmap.org/search?" + urlencode({"query": address.strip()}),
        "google": "https://www.google.com/maps/dir/?"
        + urlencode({"api": "1", "destination": text}),
    }


def for_event(event) -> dict[str, str]:
    return links(event.location, event.address, event.latitude, event.longitude)


def mail_lines(event) -> list[str]:
    """Zeilen für Mails: Anfahrt und Routenlinks."""
    lines: list[str] = []
    if event.directions.strip():
        lines.append(f"Anfahrt: {event.directions.strip()}")
    found = for_event(event)
    if found:
        lines.append(f"Route (OpenStreetMap): {found['osm']}")
        lines.append(f"Route (Google Maps): {found['google']}")
    return lines
