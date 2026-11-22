"""``/.well-known/security.txt`` (RFC 9116): Wohin mit einer gefundenen Sicherheitslücke?

Lücken im Programm gehen vertraulich an das Projekt (SECURITY.md); der Betreiber der Instanz
kann eine eigene Stelle davor setzen (``HUBIPLAN_SECURITY_CONTACT``), etwa für Vorfälle, die nur
seinen Server betreffen. Die Datei nennt keine Personen und keine Fassung.
"""

from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

PROJECT_CONTACT = "https://github.com/hubiplan/hubiplan/security/advisories/new"
PROJECT_POLICY = "https://github.com/hubiplan/hubiplan/blob/main/SECURITY.md"
# RFC 9116 empfiehlt weniger als ein Jahr; die Datei entsteht bei jedem Abruf neu, die Frist
# läuft also nie ab, solange die Instanz läuft.
VALID_DAYS = 90


def _contact(value: str) -> str:
    """Reine E-Mail-Adressen als ``mailto:``; Adressen mit Schema bleiben, wie sie sind."""
    value = "".join(value.split())  # keine Zeilenumbrüche in die Datei tragen
    if "://" in value or value.startswith("mailto:"):
        return value
    return f"mailto:{value}"


@require_GET
@cache_control(public=True, max_age=3600)
def security_txt(request):
    contacts = [_contact(v) for v in settings.SECURITY_CONTACT if v.strip()]
    contacts.append(PROJECT_CONTACT)
    expires = (timezone.now() + timedelta(days=VALID_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    lines = [f"Contact: {c}" for c in contacts]
    lines += [
        f"Expires: {expires.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "Preferred-Languages: de, en",
        f"Policy: {PROJECT_POLICY}",
        f"Canonical: {request.build_absolute_uri('/.well-known/security.txt')}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")
