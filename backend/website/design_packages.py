"""Designpakete: ein Design als Datei weitergeben und wieder einspielen.

Ein Paket (ZIP) enthält den Steckbrief ``design.json``, die Gestaltung ``design.css`` und
ein geprüftes Standardlayout (skizze_wie/quelle). Freie HTML-/Django-Vorlagen
sind nicht erlaubt. So lässt sich ein Design samt
Anordnung exportieren und auf einer Installation als eigenes Design einspielen, z. B. das
alte „Klassisch“ als Design nur für einen Verein (Konzept konzepte/designs-import-export.md,
Ralf 2026-11-02).

Ein Paket ist Gestaltungscode. Deshalb spielen nur Plattformverwalter Pakete ein, und alles
wird streng geprüft: kein JavaScript, keine fremden Adressen, keine freien HTML-/Django-Vorlagen.
Was die Prüfung nicht besteht, wird abgelehnt, nicht „bereinigt“. Die Webseite prüft beim
Abholen noch einmal dasselbe (``hubiplan-website/seite/designpaket.py``).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field

from django.utils.translation import gettext as _

from . import designs

FORMAT = "hubiplan-designpaket"
VERSION = 1

MAX_ZIP_BYTES = 2 * 1024 * 1024
MAX_UNPACKED_BYTES = 5 * 1024 * 1024
MAX_CSS_BYTES = 64 * 1024
MAX_TEMPLATE_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 16 * 1024

KEY = re.compile(r"^[a-z][a-z0-9-]{1,30}$")

# Vorlagen, die ein Paket ersetzen darf (Name im Paket → Vorlage der Webseite)
TEMPLATES = {
    "vorlagen/kopf.html": "seite/kopf.html",
    "vorlagen/fuss.html": "seite/fuss.html",
    "vorlagen/start.html": "seite/start.html",
}
ALLOWED_FILES = {"design.json", "design.css", *TEMPLATES}

MANIFEST_FIELDS = {
    "format",
    "version",
    "key",
    "label",
    "hint",
    "roles",
    "skizze_wie",
    "nur_fuer",
    "braucht_webseite",
    "exportiert",
    "quelle",
}

# Im CSS verboten: alles, was nachlädt, Skripte ausführt oder sich tarnen lässt
FORBIDDEN_CSS = [
    (re.compile(r"@import", re.I), "@import"),
    (re.compile(r"@font-face", re.I), "@font-face"),
    (re.compile(r"url\s*\(", re.I), "url(…)"),
    (re.compile(r"image-set\s*\(", re.I), "image-set(…)"),
    (re.compile(r"expression\s*\(", re.I), "expression(…)"),
    (re.compile(r"javascript\s*:", re.I), "javascript:"),
    (re.compile(r"behavior\s*:|-moz-binding", re.I), "behavior/-moz-binding"),
    (re.compile(r"\\"), "Rückstrich (Maskierung)"),
    (re.compile(r"<"), "spitze Klammer"),
]


class PackageError(Exception):
    """Das Paket ist ungültig; ``problems`` nennt alle Gründe."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Package:
    key: str
    label: str
    label_en: str
    hint: str
    hint_en: str
    roles: dict
    sketch_like: str
    css: str
    templates: dict  # Vorlage der Webseite (seite/…) → Text
    warnings: list[str] = field(default_factory=list)
    # Standarddesign, aus dem das Paket exportiert wurde (Farbzuordnung übernehmen)
    source: str = ""

    @property
    def content_hash(self) -> str:
        return content_hash(self.css, self.templates, self.roles, self.sketch_like)


def content_hash(css: str, templates: dict, roles: dict, layout: str = "classic") -> str:
    raw = json.dumps(
        {"css": css, "templates": templates, "roles": roles, "layout": layout}, sort_keys=True
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# --- Prüfungen ---------------------------------------------------------------


def css_problems(text: str) -> list[str]:
    problems = []
    if len(text.encode()) > MAX_CSS_BYTES:
        problems.append(_("design.css ist größer als 64 KB."))
    for pattern, what in FORBIDDEN_CSS:
        if pattern.search(text):
            problems.append(
                _("design.css enthält {what}, das ist nicht erlaubt.").format(what=what)
            )
    return problems


def template_problems(name: str, text: str) -> list[str]:
    # No untrusted source reaches a template compiler, irrespective of DTL branches,
    # escaping, includes or HTML tokenizer context.
    return [
        _(
            "Eigene HTML-/Django-Vorlagen sind nicht erlaubt. "
            "Bitte ein Standardlayout mit CSS verwenden."
        )
    ]


def _text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(ch for ch in value if ch.isprintable()).strip()[:limit]


def _roles(value) -> tuple[dict, list[str]]:
    problems: list[str] = []
    if not isinstance(value, dict) or not value:
        return {}, [_("design.json: „roles“ fehlt oder ist leer.")]
    result = {}
    for role, spec in value.items():
        if role not in designs.ROLES:
            problems.append(_("design.json: unbekannte Farbrolle „{r}“.").format(r=str(role)[:30]))
            continue
        if isinstance(spec, str) and spec in designs.NEUTRAL:
            result[role] = spec
        elif (
            isinstance(spec, list)
            and 1 <= len(spec) <= 3
            and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i <= 5 for i in spec)
        ):
            result[role] = list(spec)
        else:
            problems.append(
                _("design.json: Farbrolle „{r}“ hat keinen gültigen Wert.").format(r=role)
            )
    if "header" not in result and not problems:
        problems.append(_("design.json: Farbrolle „header“ fehlt."))
    return result, problems


def _lang_pair(value, limit: int) -> tuple[str, str]:
    if isinstance(value, dict):
        return _text(value.get("de"), limit), _text(value.get("en"), limit)
    return _text(value, limit), ""


def read(
    data: bytes,
    *,
    key: str | None = None,
    label: str | None = None,
    label_en: str | None = None,
) -> Package:
    """ZIP prüfen und lesen. ``key``/``label`` ersetzen die Angaben des Steckbriefs
    (so wird aus dem exportierten „Klassisch“ ein eigenes Design „Hubertus“)."""
    if len(data) > MAX_ZIP_BYTES:
        raise PackageError([_("Das Paket ist größer als 2 MB.")])
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, ValueError, OSError):
        raise PackageError([_("Die Datei ist kein ZIP-Paket.")]) from None
    problems: list[str] = []
    warnings: list[str] = []
    files: dict[str, str] = {}
    total = 0
    for info in infos:
        name = info.filename
        if info.is_dir():
            if name not in ("vorlagen/",):
                problems.append(_("Ordner „{n}“ ist im Paket nicht erlaubt.").format(n=name[:60]))
            continue
        if name not in ALLOWED_FILES:
            problems.append(_("Datei „{n}“ ist im Paket nicht erlaubt.").format(n=name[:60]))
            continue
        if name in files:
            problems.append(_("Datei „{n}“ kommt doppelt vor.").format(n=name))
            continue
        total += info.file_size
        if info.file_size > MAX_UNPACKED_BYTES or total > MAX_UNPACKED_BYTES:
            raise PackageError([_("Das Paket ist entpackt größer als 5 MB.")])
        try:
            with archive.open(info) as fh:
                raw = fh.read(MAX_UNPACKED_BYTES + 1)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError):
            problems.append(_("Datei „{n}“ lässt sich nicht entpacken.").format(n=name))
            continue
        if len(raw) > info.file_size:
            raise PackageError([_("Das Paket ist entpackt größer als 5 MB.")])
        try:
            files[name] = raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(_("Datei „{n}“ ist kein UTF-8-Text.").format(n=name))
    if "design.json" not in files:
        problems.append(_("design.json fehlt."))
    if "design.css" not in files:
        problems.append(_("design.css fehlt."))
    if problems:
        raise PackageError(problems)

    if len(files["design.json"].encode()) > MAX_MANIFEST_BYTES:
        raise PackageError([_("design.json ist größer als 16 KB.")])
    try:
        manifest = json.loads(files["design.json"])
    except ValueError:
        raise PackageError([_("design.json ist kein gültiges JSON.")]) from None
    if not isinstance(manifest, dict):
        raise PackageError([_("design.json ist kein gültiges JSON.")])
    if manifest.get("format") != FORMAT:
        problems.append(_("design.json: Das ist kein HUBIplan-Designpaket."))
    version = manifest.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        problems.append(_("design.json: Version fehlt."))
    elif version > VERSION:
        problems.append(
            _("Das Paket hat Version {v}; diese HUBIplan-Fassung kennt nur Version {k}.").format(
                v=version, k=VERSION
            )
        )
    unknown = sorted(set(manifest) - MANIFEST_FIELDS)
    if unknown:
        warnings.append(
            _("Unbekannte Angaben werden nicht übernommen: {f}").format(
                f=", ".join(str(u)[:30] for u in unknown[:10])
            )
        )

    final_key = (key or "").strip() or _text(manifest.get("key"), 40)
    if not KEY.match(final_key):
        problems.append(
            _("Kürzel „{k}“ ist ungültig (2–31 Zeichen: a–z, 0–9, Bindestrich).").format(
                k=final_key[:40]
            )
        )
    elif final_key in designs.DESIGNS:
        problems.append(
            _(
                "Kürzel „{k}“ gehört zu einem Standarddesign. Bitte ein eigenes Kürzel wählen."
            ).format(k=final_key)
        )
    m_label, m_label_en = _lang_pair(manifest.get("label"), 60)
    final_label = _text(label, 60) if label else m_label
    final_label_en = _text(label_en, 60) if label_en else (m_label_en if not label else "")
    if not final_label:
        problems.append(_("Name des Designs fehlt."))
    hint, hint_en = _lang_pair(manifest.get("hint"), 300)
    roles, role_problems = _roles(manifest.get("roles"))
    problems += role_problems
    sketch = _text(manifest.get("skizze_wie"), 20)
    if sketch not in designs.DESIGNS:
        sketch = designs.DEFAULT_DESIGN

    source = _text(manifest.get("quelle"), 20)
    if source in designs.DESIGNS:
        sketch = source
    css = files["design.css"]
    problems += css_problems(css)
    templates = {}
    for name, target in TEMPLATES.items():
        if name in files:
            problems += template_problems(name, files[name])
            templates[target] = files[name]
    if problems:
        raise PackageError(list(dict.fromkeys(problems)))
    return Package(
        key=final_key,
        label=final_label,
        label_en=final_label_en,
        hint=hint,
        hint_en=hint_en,
        roles=roles,
        sketch_like=sketch,
        css=css,
        templates=templates,
        warnings=warnings,
        source=source if source in designs.DESIGNS else "",
    )


# --- Export ------------------------------------------------------------------


def build_zip(
    *,
    key: str,
    label: str,
    label_en: str,
    hint: str,
    hint_en: str,
    roles: dict,
    sketch_like: str,
    css: str,
    templates: dict,
    exported: str,
    source: str = "",
) -> bytes:
    """Paket als ZIP (gleiches Format wie der Export der Webseite für Standarddesigns)."""
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "key": key,
        "label": {"de": label, "en": label_en or label},
        "hint": {"de": hint, "en": hint_en or hint},
        "roles": roles,
        "skizze_wie": sketch_like,
        "exportiert": exported,
    }
    if source:
        manifest["quelle"] = source
    if templates:
        raise PackageError(template_problems("", ""))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("design.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        archive.writestr("design.css", css)
    return buf.getvalue()
