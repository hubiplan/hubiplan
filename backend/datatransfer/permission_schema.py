"""Explicit interpretation of permission codes which changed meaning over time."""

from django.utils.translation import gettext

from access.catalog import DEPARTMENT_CODES, codes_for, from_legacy, normalize


def roles_in(doc):
    def walk(node, department=False):
        if not isinstance(node, dict):
            return
        for role in node.get("roles") or []:
            if isinstance(role, dict):
                yield node.get("name", ""), role, department, node.get("type") or "club"
        for role in node.get("unit_roles") or []:
            if isinstance(role, dict):
                yield node.get("name", ""), role, False, "club"
        for key, dept in (("organization", False), ("department", True)):
            if isinstance(node.get(key), dict):
                yield from walk(node[key], dept)
        for key, dept in (("clubs", False), ("departments", True)):
            for child in node.get(key) or []:
                yield from walk(child, dept)

    yield from walk(doc)


def policy(doc, options):
    marked = "permissions_schema" in doc
    ambiguous = any(
        from_legacy(role.get("permissions"), dept=dept)
        != normalize(role.get("permissions"), dept=dept)
        for _, role, dept, _ in roles_in(doc)
    )
    schema = doc.get("permissions_schema") if marked else options.get("permissions_schema")
    errors = []
    if not marked and ambiguous:
        if schema not in (1, 2):
            errors.append(
                gettext(
                    "Die Datei hat kein eindeutiges Rechteformat. "
                    "Bitte die Bedeutung der Rollenrechte ausdrücklich auswählen."
                )
            )
        elif not options.get("permissions_confirmed"):
            errors.append(
                gettext("Bitte die wirksamen Rollenrechte prüfen und ausdrücklich bestätigen.")
            )
    # Without overlapping codes both interpretations are identical.
    schema = schema if schema in (1, 2) else (2 if ambiguous else 1)
    translate = from_legacy if schema == 1 else normalize
    roles = [
        {
            "unit": unit,
            "name": str(role.get("name") or ""),
            "permissions": sorted(
                set(translate(role.get("permissions"), dept=dept))
                & (set(DEPARTMENT_CODES) if dept else set(codes_for(org_type)))
            ),
        }
        for unit, role, dept, org_type in roles_in(doc)
    ]
    return {
        "schema": schema,
        "marked": marked,
        "ambiguous": ambiguous,
        "roles": roles,
        "errors": errors,
    }
