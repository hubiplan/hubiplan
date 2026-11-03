"""Suchmarken wiederholbar nachfüllen oder vollständig gegen die Quelldaten prüfen."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.tenancy import rls_bypass
from members.models import Person
from members.personmarks import values, write


class Command(BaseCommand):
    help = "Personensuchmarken nachfüllen; --pruefen schreibt nichts und prüft alle Werte."

    def add_arguments(self, parser):
        parser.add_argument("--pruefen", action="store_true")
        parser.add_argument("--scope", type=int)

    def handle(self, *args, pruefen=False, scope=None, **options):
        checked = changed = broken = 0
        last = 0
        with rls_bypass():
            qs = Person.objects.order_by("pk")
            if scope is not None:
                qs = qs.filter(scope_id=scope)
            while ids := list(qs.filter(pk__gt=last).values_list("pk", flat=True)[:500]):
                last = ids[-1]
                for pk in ids:
                    # Neu lesen NACH der Sperre, damit kein überholter Wert zurückgeschrieben
                    # wird. Ein Abbruch lässt abgeschlossene Zeilen nutzbar; Wiederholung sicher.
                    with transaction.atomic():
                        person = qs.select_for_update().filter(pk=pk).first()
                        if person is None:
                            continue
                        checked += 1
                        try:
                            expected = values(person)
                        except ValueError:
                            broken += 1
                            continue
                        if any(
                            getattr(person, field) != value for field, value in expected.items()
                        ):
                            changed += 1
                            if not pruefen:
                                write(person)
            self.stdout.write(f"Geprüft: {checked}; Abweichungen: {changed}; unlesbar: {broken}.")
            if broken or (pruefen and changed):
                raise CommandError("Personensuchmarken nicht vollständig und korrekt.")
