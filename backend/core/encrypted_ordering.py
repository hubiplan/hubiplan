"""SQL-Sortierung nach verschlüsselten Werten am Django-Compiler abweisen.

Feld-Hooks allein erfassen weder order_by("relation__feld") noch Meta.ordering.
Hier sind Namen, F-Ausdrücke und Annotationen bereits zu Spalten aufgelöst.
Die kleine Compiler-Erweiterung wird beim Start genau einmal installiert.
"""

from functools import wraps

from django.core.exceptions import FieldError
from django.db.models.expressions import Col
from django.db.models.sql.compiler import SQLCompiler

from .encfields import EncryptedMixin


def _encrypted_column(expression):
    if isinstance(expression, Col) and isinstance(expression.target, EncryptedMixin):
        return expression.target
    # Insbesondere skalare Unterabfragen tragen das Feld am Ergebnis, während
    # ihr inneres Query keine gewöhnliche Col-Quelle dieses Ausdrucks ist.
    if isinstance(getattr(expression, "output_field", None), EncryptedMixin):
        return expression.output_field
    for child in expression.get_source_expressions():
        if child is not None and (field := _encrypted_column(child)) is not None:
            return field
    return None


def install():
    original = SQLCompiler.get_order_by
    if getattr(original, "_encrypted_ordering_guard", False):
        return

    @wraps(original)
    def get_order_by(compiler):
        result = original(compiler)
        for expression, _ in result:
            field = _encrypted_column(expression)
            if field is not None:
                raise FieldError(
                    f"{field.model._meta.label}.{field.name} ist verschlüsselt: "
                    "Sortierung nur nach entschlüsselten Werten in Python."
                )
        return result

    get_order_by._encrypted_ordering_guard = True
    SQLCompiler.get_order_by = get_order_by
