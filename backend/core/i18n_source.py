"""Begrenzte Quelltextprüfung sichtbarer Systemtexte, kein Datenflussnachweis."""

import ast
import re

EXCEPTIONS = {
    "ValidationError",
    "NotFound",
    "PermissionDenied",
    "ParseError",
    "NotAuthenticated",
    "AuthenticationFailed",
}


def _name(node):
    return (
        node.id
        if isinstance(node, ast.Name)
        else node.attr
        if isinstance(node, ast.Attribute)
        else ""
    )


def _texts(node):
    if isinstance(node, (ast.Constant, ast.JoinedStr)):
        if isinstance(node, ast.Constant) and (
            not isinstance(node.value, str) or not re.search("[A-Za-zÄÖÜäöüß]", node.value)
        ):
            return
        yield node
    elif isinstance(node, ast.Dict):
        for value in node.values:
            yield from _texts(value)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for value in node.elts:
            yield from _texts(value)
    elif isinstance(node, ast.IfExp):
        yield from _texts(node.body)
        yield from _texts(node.orelse)


def untranslated_ui(code: str) -> list[tuple[int, str]]:
    """API-Fehler, Antwortmeldungen, Auswahltexte und übliche Fehlerlisten prüfen.

    Technische Werte, Feldnamen, persistierte Vereinsinhalte und Betreiberbefehle
    gehören nicht in diesen Umfang. Zusammengesetzte Texte und Funktionsrückgaben
    brauchen weiterhin die Prüfung ihrer Herkunft und Laufzeittests.
    """
    found = {}

    def add(node):
        for item in _texts(node):
            found[item.lineno, item.col_offset] = ast.get_source_segment(code, item)

    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Call) and _name(node.func) in EXCEPTIONS and node.args:
            add(node.args[0])
        if isinstance(node, ast.Call) and _name(node.func) == "Response" and node.args:
            if isinstance(node.args[0], ast.Dict):
                for key, value in zip(node.args[0].keys, node.args[0].values, strict=True):
                    if isinstance(key, ast.Constant) and key.value in (
                        "detail",
                        "message",
                        "error",
                        "warning",
                    ):
                        add(value)
        if isinstance(node, ast.ClassDef) and any(
            _name(base) in ("TextChoices", "IntegerChoices") for base in node.bases
        ):
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and isinstance(item.value, ast.Tuple)
                    and len(item.value.elts) > 1
                ):
                    add(item.value.elts[-1])
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, ast.Subscript)
                and _name(target.value) in ("errors", "issues", "problems")
                for target in targets
            ):
                add(node.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and _name(node.func.value) in ("errors", "issues", "problems", "gaps", "missing")
            and node.args
        ):
            add(node.args[0])
    return [(line, text) for (line, _column), text in sorted(found.items())]
