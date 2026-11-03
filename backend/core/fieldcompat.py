"""Rückweg anhand der Felddeklarationen der Zielfassung, ohne ihren Code auszuführen.

Nur eindeutig erkannte gewöhnliche Django-Felder dürfen entschlüsselt werden.
Unbekannte Deklarationen brechen ab, statt vorsorglich alle Daten offenzulegen.
"""

import ast
import inspect
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

PLAIN_FIELDS = {"CharField", "TextField", "EmailField", "DateField", "JSONField"}
ENCRYPTED_FIELDS = {
    "EncryptedCharField",
    "EncryptedTextField",
    "EncryptedEmailField",
    "EncryptedDateField",
    "EncryptedJSONField",
}


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def rollback_fields(model, fields, target):
    relative = Path(inspect.getfile(model)).resolve().relative_to(Path(settings.BASE_DIR).resolve())
    source = target / relative
    if not source.is_file():
        raise CommandError(f"Zielquelltext für {model._meta.label} fehlt; Rückweg nicht eindeutig.")
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    imports = {"models": "django.db.models"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for name in node.names:
                imports[name.asname or name.name] = f"{node.module}.{name.name}"
        elif isinstance(node, ast.Import):
            for name in node.names:
                imports[name.asname or name.name.split(".")[0]] = (
                    name.name if name.asname else name.name.split(".")[0]
                )
    cls = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == model.__name__), None
    )
    if cls is None:
        raise CommandError(f"Zielfelddeklaration für {model._meta.label} nicht eindeutig.")
    declarations = {}
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name):
                    declarations[name.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declarations[node.target.id] = node.value
    selected = []
    for field in fields:
        value = declarations.get(field.name)
        if value is None:
            raise CommandError(f"Zielfeld {model._meta.label}.{field.name} nicht eindeutig.")
        name = _dotted(value.func) if isinstance(value, ast.Call) else ""
        head, _, tail = name.partition(".")
        resolved = imports.get(head, head) + (f".{tail}" if tail else "")
        if resolved in {f"core.encfields.{name}" for name in ENCRYPTED_FIELDS}:
            continue
        if resolved not in {f"django.db.models.{name}" for name in PLAIN_FIELDS}:
            raise CommandError(f"Unbekanntes Zielfeld {model._meta.label}.{field.name}.")
        selected.append(field)
    return selected
