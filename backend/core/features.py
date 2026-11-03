"""Funktionen der Schnittstellen für Webseite und App (konzepte/releases.md, R7).

Webseite und App fragen ``features`` in der Selbstauskunft ab und schalten danach frei,
statt eine bestimmte HUBIplan-Version vorauszusetzen. Innerhalb von ``v1`` kommen nur Namen
hinzu, keiner verschwindet. Wer der Schnittstelle etwas hinzufügt, das Webseite oder App
nutzen sollen, trägt hier einen Namen ein und in docs/versionen.md, seit wann es ihn gibt.
"""

# /api/app/v1/instance/
APP_FEATURES: dict[str, str] = {
    "rechte-stufen": "Rechte je Bereich als „lesen“ (….view) und „bearbeiten“ (….edit)",
    "app-verwaltung": "Verwaltung in der App (admin/)",
    "app-senden": "Senden aus der App (send/)",
    "app-sprache": "Sprache je Konto (me/language/)",
}

# /api/public/site/v1/instance/
SITE_FEATURES: dict[str, str] = {
    "designpakete": "Designpakete (<key>/design/<paket>/)",
    "chronik-zeitleiste": "Chronik als Zeitleiste (timeline, timeline_newest_first)",
    "bildunterschriften": "Bildunterschriften je Text (show_captions)",
    "ergebnisse": "Wettbewerbsergebnisse (<key>/results/)",
}


def app_features() -> list[str]:
    return sorted(APP_FEATURES)


def site_features() -> list[str]:
    return sorted(SITE_FEATURES)
