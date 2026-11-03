"""Konservative Fristzuordnung aus Auszugsperiode und allen Buchungstagen.

Originalbytes und angezeigte Saldenstichtage bleiben unverändert. Auch ältere,
widersprüchliche Importdaten dürfen keine frühere Dateibereinigung erlauben.
"""

from django.db.models import Max, Min
from django.db.models.functions import Coalesce, Greatest, Least, TruncDate


def queryset(org):
    from .models import BankStatement

    # PostgreSQL LEAST/GREATEST ignorieren NULL, solange ein Datum vorhanden ist.
    # Keine Entschlüsselung oder Übertragung aller Umsatzzeilen für diese Grenzen.
    return BankStatement.objects.filter(organization=org).annotate(
        original_first_day=Coalesce(
            Least("date_from", "date_to", Min("lines__date")), TruncDate("created_at")
        ),
        original_last_day=Coalesce(
            Greatest("date_from", "date_to", Max("lines__date")), TruncDate("created_at")
        ),
    )


def for_year(org, start, end):
    return (
        queryset(org)
        .exclude(source="")
        .filter(original_last_day__gte=start, original_last_day__lte=end)
    )


def year_range(org, statement):
    return (
        org.fiscal_year_of(statement.original_first_day),
        org.fiscal_year_of(statement.original_last_day),
    )
