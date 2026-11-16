"""Zeigt, wann jeder Job aus dem Zeitplan von "beat" zuletzt lief (Gesamtaudit 15.11., PF-01).

``manage.py jobs_status``           Tabelle aller Jobs
``manage.py jobs_status --pruefen`` nur überfällige Jobs; Rückgabewert 1, wenn es welche gibt
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core import joblauf


def _when(value) -> str:
    return f"{timezone.localtime(value):%d.%m.%Y %H:%M}" if value else "noch nie"


class Command(BaseCommand):
    help = "Zeigt, wann die Hintergrundjobs zuletzt liefen, und meldet überfällige."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pruefen", action="store_true", help="nur überfällige Jobs, Rückgabewert 1 bei Fund"
        )

    def handle(self, *args, **options):
        rows = joblauf.status()
        if options["pruefen"]:
            lines = joblauf.overdue_lines(rows)
            for line in lines:
                self.stdout.write(line)
            if lines:
                raise CommandError(f"{len(lines)} Job(s) überfällig")
            self.stdout.write("Alle Jobs liefen im erwarteten Abstand.")
            return
        width = max(len(r.name) for r in rows)
        self.stdout.write(f"{'Job':<{width}}  zuletzt erfolgreich  letzter Fehler      Stand")
        for r in rows:
            state = "ÜBERFÄLLIG" if r.overdue else "ok"
            self.stdout.write(
                f"{r.name:<{width}}  {_when(r.last_success_at):<19}  "
                f"{_when(r.last_failure_at):<18}  {state}"
            )
