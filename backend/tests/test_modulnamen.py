"""Jede im Code abgefragte Modulkennung muss es im Katalog geben.

Fragt eine Stelle ein Modul ab, das die Plattform gar nicht freischalten kann (z. B. früher
„documents“, „docs“ oder „todos“), läuft die Funktion im Betrieb nie. Konzept:
konzepte/module-neustruktur.md, Schritt M0.
"""

import re
from pathlib import Path

from access.catalog import SWITCHABLE_MODULES

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"

# "x" in (org.enabled_modules …), "x" not in org.enabled_modules
PY_SINGLE = re.compile(r"""["']([a-z_]+)["']\s+(?:not\s+)?in\s+\(?[\w.]*enabled_modules""")
# {"a", "b"} <= set(org.enabled_modules)
PY_SET = re.compile(r"""\{([^{}]*)\}\s*<=\s*set\(\s*[\w.]*enabled_modules""")
# MODULE = "x" in Modulen, die sich darüber freischalten
PY_CONST = re.compile(r"""^MODULE\s*=\s*["']([a-z_]+)["']""", re.M)
# org.modules.includes('x')
TS_INCLUDES = re.compile(r"""modules\.includes\(\s*['"]([a-z_]+)['"]\s*\)""")


def _files(root: Path, suffixes: tuple[str, ...]):
    for path in root.rglob("*"):
        if path.suffix not in suffixes or not path.is_file():
            continue
        parts = set(path.parts)
        if parts & {"tests", "test", "migrations", "node_modules", "__pycache__"}:
            continue
        yield path


def _used_modules() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}

    def add(name: str, path: Path) -> None:
        found.setdefault(name, set()).add(str(path.relative_to(BACKEND.parent)))

    for path in _files(BACKEND, (".py",)):
        text = path.read_text(encoding="utf-8")
        for name in PY_SINGLE.findall(text) + PY_CONST.findall(text):
            add(name, path)
        for group in PY_SET.findall(text):
            for name in re.findall(r"""["']([a-z_]+)["']""", group):
                add(name, path)
    if FRONTEND.is_dir():
        for path in _files(FRONTEND, (".ts", ".tsx")):
            for name in TS_INCLUDES.findall(path.read_text(encoding="utf-8")):
                add(name, path)
    return found


def test_abgefragte_module_gibt_es():
    used = _used_modules()
    assert used, "Suchmuster finden keine Modulabfragen mehr"
    unknown = {n: sorted(p) for n, p in used.items() if n not in SWITCHABLE_MODULES}
    assert not unknown, f"Module, die es nicht gibt: {unknown}"
