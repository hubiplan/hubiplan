"""Härtung für ReportLab-Absätze (Paragraph-Markup).

Absatztexte in PDFs sind Markup. Wird dort einmal Benutzertext ohne ``escape()`` eingesetzt,
könnten ``<img src="…">`` lokale Dateien einbetten oder Adressen abrufen, und ``<a href="…">``
setzt beliebige Verweise (auch ``javascript:``). HUBIplan braucht im Absatz-Markup weder Bilder
(Logos und Unterschriften sind eigene Flowables) noch andere Verweise als http, https und mailto.

``install()`` schaltet beides deshalb zentral ab, unabhängig von der Maskierung im Einzelfall:

- ``<img>`` in Absätzen wird ignoriert (kein Dateizugriff, kein Abruf),
- Verweise mit anderem Ziel als http(s) oder mailto bleiben Text ohne Verweis,
- ReportLab ruft keine Adressen ab (``trustedSchemes`` leer).
"""

from __future__ import annotations

ERLAUBTE_VERWEISE = ("http://", "https://", "mailto:")


def verweis_erlaubt(ziel: str) -> bool:
    return ziel.strip().lower().startswith(ERLAUBTE_VERWEISE)


def install() -> None:
    from reportlab import rl_config
    from reportlab.platypus import paraparser

    rl_config.trustedHosts = None
    rl_config.trustedSchemes = []

    parser = paraparser.ParaParser
    if getattr(parser, "_hubiplan_gehaertet", False):
        return
    original_link = parser._handle_link

    def _handle_link(self, tag, attributes):
        original_link(self, tag, attributes)
        frag = self._stack[-1]
        if frag.link and not verweis_erlaubt(frag.link[-1][1]):
            frag.link = frag.link[:-1]

    def end_img(self):
        frag = self._stack[-1]
        if hasattr(frag, "_selfClosingTag"):
            del frag._selfClosingTag
        self._pop("img")

    parser._handle_link = _handle_link
    parser.end_img = end_img
    parser._hubiplan_gehaertet = True
