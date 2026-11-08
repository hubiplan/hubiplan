#!/usr/bin/env bash
# Bildschirmfotos der Hilfe neu erzeugen (docs/hilfe.md).
#
#   scripts/hilfe-bilder.sh [Bildname …]
#
# Startet in Wegwerf-Containern PostgreSQL, Redis, das Backend mit den erfundenen
# Demodaten (seed_testdata) und die Oberfläche aus dem Arbeitsstand, fotografiert jede
# Stelle aus frontend/src/help/bilder.json mit Playwright auf Deutsch und Englisch und
# legt die Bilder unter frontend/public/hilfe-bilder/<sprache>/ ab. Danach die Bilder
# ansehen und einchecken.
#
# Läuft nur lokal (nie auf einem Server) und belegt dafür einen Testplatz
# (scripts/testplatz.sh).
set -euo pipefail

if [ -z "${TESTPLATZ:-}" ]; then
    exec "$(dirname "$0")/testplatz.sh" "$0" "$@"
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CPUS="--cpuset-cpus=$TESTPLATZ_CPUS"
# Gleiche Hauptversion wie das Playwright-Image; bei einem Wechsel beide anpassen
PLAYWRIGHT_VERSION="${PLAYWRIGHT_VERSION:-1.55.0}"
PW_IMAGE="mcr.microsoft.com/playwright:v$PLAYWRIGHT_VERSION-noble"
PG_IMAGE=$(grep -m1 -oE 'image: postgres:[0-9][^ ]*' "$ROOT/docker-compose.server.yml" | cut -d' ' -f2)
REDIS_IMAGE=$(grep -m1 -oE 'image: redis:[0-9][^ ]*' "$ROOT/docker-compose.yml" | cut -d' ' -f2)
# Nur für diesen Lauf; die Demozugänge verschwinden mit den Containern
PASSWORD="Bilder-$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')"

ID="hubiplan-bilder-$(date +%s)-$$"
IMG="hubiplan-bilder-backend:$ID"
WORK=$(mktemp -d)
cleanup() {
    for c in pw web backend redis db; do docker rm -f "$ID-$c" > /dev/null 2>&1 || true; done
    docker network rm "$ID" > /dev/null 2>&1 || true
    docker image rm "$IMG" > /dev/null 2>&1 || true
    rm -rf "$WORK" 2> /dev/null || docker run --rm -v "$WORK:/w" node:24-alpine rm -rf /w/frontend
    rm -rf "$WORK"
}
trap cleanup EXIT

echo "Bildschirmfotos der Hilfe aus dem Arbeitsstand mit $TEST_KERNE Kernen …"
# Kopie ohne node_modules, damit nichts mit Root-Rechten im Klon landet
tar -C "$ROOT" --exclude=node_modules --exclude=dist -cf - frontend | tar -C "$WORK" -xf -

docker build -q -t "$IMG" "$ROOT/backend" > /dev/null
docker network create "$ID" > /dev/null
docker run -d --name "$ID-db" --network "$ID" --network-alias db "$CPUS" --tmpfs /var/lib/postgresql \
    -e POSTGRES_USER=hubiplan -e POSTGRES_PASSWORD=hubiplan -e POSTGRES_DB=hubiplan "$PG_IMAGE" > /dev/null
docker run -d --name "$ID-redis" --network "$ID" --network-alias redis "$CPUS" "$REDIS_IMAGE" > /dev/null
until docker exec "$ID-db" pg_isready -U hubiplan > /dev/null 2>&1; do sleep 1; done

docker run -d --name "$ID-backend" --network "$ID" --network-alias backend "$CPUS" \
    -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-fuer-bilder \
    -e DJANGO_ALLOWED_HOSTS=localhost,backend,web \
    -e DJANGO_CSRF_TRUSTED_ORIGINS=http://web:5173 -e FRONTEND_URL=http://web:5173 \
    -e DATABASE_URL=postgres://hubiplan:hubiplan@db:5432/hubiplan -e DATABASE_APP_ROLE=hubiplan_app \
    -e REDIS_URL=redis://redis:6379/0 -e CACHE_URL=redis://redis:6379/1 \
    -e HUBIPLAN_LANGUAGES=de,en -e RUN_MIGRATIONS=1 -e MIGRATE_VERBOSITY=0 \
    "$IMG" python manage.py runserver 0.0.0.0:8000 > /dev/null
until docker exec "$ID-backend" python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/public/languages/')" > /dev/null 2>&1; do
    docker inspect -f '{{.State.Running}}' "$ID-backend" | grep -q true || { docker logs "$ID-backend" | tail -30; exit 1; }
    sleep 2
done
docker exec "$ID-backend" python manage.py seed_testdata --password "$PASSWORD" > /dev/null
# Für die Bilder auch die Module, die neue Vereine erst einschalten (nur in diesem Wegwerf-Stand)
docker exec -e DATABASE_APP_ROLE= "$ID-backend" python manage.py shell -c "
from organizations.models import Organization
# Nur diese Wegwerf-Datenbank: Auch die Organisationsanzeigen sind vollständig erfunden.
# seed_testdata bleibt für andere Einsatzzwecke unverändert.
for kind, name, city in [
    ('federation', 'Dachverband Musterstadt', 'Musterstadt'),
    ('club', 'Schützenverein Beispieldorf', 'Beispieldorf'),
]:
    Organization.objects.filter(type=kind).update(
        name=name, short_name='', city=city, postal_code='12345',
        street='Musterweg 1', contact_email='kontakt@example.org',
    )
for o in Organization.objects.filter(type='club'):
    o.enabled_modules = sorted(set(o.enabled_modules or []) | {'competitions', 'entries', 'website', 'material'})
    o.cash_counts_enabled = True
    # Englische Bezeichnung der Untereinheiten (sonst zeigt die englische Oberfläche „Züge“)
    if o.department_label == 'Zug' and not o.department_label_en:
        o.department_label_en, o.department_label_plural_en = 'platoon', 'platoons'
    o.save(update_fields=['enabled_modules', 'cash_counts_enabled', 'department_label_en', 'department_label_plural_en'])
# Materialbeispiele nur in der wegwerfbaren Bildschirmfoto-Datenbank.
from materials.models import MaterialItem
from access.models import Role
for o in Organization.objects.filter(type='club'):
    for name, description, purpose in [
        ('Beamer mit Zubehör', 'Beamer im schwarzen Koffer mit Fernbedienung und HDMI-Kabel.', 'Präsentationen und Mitgliederversammlungen'),
        ('Kabeltrommel 25 m', 'Kabeltrommel mit vier Steckdosen für Veranstaltungen.', 'Stromversorgung bei Vereinsveranstaltungen'),
        ('Werkzeugkoffer', 'Schraubendreher, Zangen und Schraubenschlüssel im Koffer.', 'Aufbau und kleinere Reparaturen'),
    ]:
        MaterialItem.objects.create(organization=o, title=name, description=description,
            purpose=purpose, location_kind='address', address={'name': 'Vereinsheim',
            'street': 'Musterweg 1', 'postal_code': '12345', 'city': 'Musterstadt', 'country': 'Deutschland'},
            location_note='Materialraum, Regal links')
    for role in Role.objects.filter(organization=o, department__isnull=True):
        if 'roles.edit' in role.permissions:
            role.permissions = sorted(set(role.permissions) | {'material.edit'})
            role.save(update_fields=['permissions'])
# Lastschrift (Beispiel-Gläubiger-ID der Bundesbank) und eine Mahnstufe
from billing.models import BillingSettings, DunningLevel
from finance.models import Account
for o in Organization.objects.filter(type='club'):
    # Bankkonto mit einer bekannten Test-IBAN, sonst fehlt der Lastschrift das Konto
    bank = Account.objects.filter(organization=o, kind='bank').order_by('pk').first()
    if bank and not bank.iban:
        bank.iban = 'DE02120300000000202051'
        bank.save(update_fields=['iban'])
    BillingSettings.objects.update_or_create(organization=o, defaults={'sepa_enabled': True, 'creditor_id': 'DE98ZZZ09999999999', 'account': bank})
    DunningLevel.objects.get_or_create(organization=o, level=1, defaults={'name': 'Zahlungserinnerung', 'days': 14})
# Erfundener Mitgliedszugang mit Mitgliederbereich (Meine Daten, App verbinden)
from django.contrib.auth import get_user_model
from access.models import RoleAssignment
from members.models import Membership
from portal.models import PortalAccess
club = RoleAssignment.objects.get(user__email='vorstand@hubertus-grimlinghausen.test').organization
club.member_portal_enabled = True
club.save(update_fields=['member_portal_enabled'])
membership = next(m for m in Membership.objects.filter(organization=club).select_related('person').order_by('pk') if m.current_period())
user, _ = get_user_model().objects.get_or_create(email='mitglied@hubertus-grimlinghausen.test',
    defaults={'first_name': membership.person.first_name, 'last_name': membership.person.last_name})
user.set_password('$PASSWORD')
user.save()
PortalAccess.objects.get_or_create(membership=membership, defaults={'organization': club, 'user': user})
# Kalenderbeispiele: gleicher Titel in zwei Einheiten und ein Termin über Mitternacht.
# Ausschließlich in dieser Wegwerf-Datenbank, damit die Hilfebilder den Kontext zeigen.
from datetime import datetime
from zoneinfo import ZoneInfo
from organizations.models import Department
from events.models import Event
month = datetime.now(ZoneInfo('Europe/Berlin')).replace(day=5, hour=20, minute=0, second=0, microsecond=0)
for department in Department.objects.filter(organization=club).order_by('pk')[:2]:
    Event.objects.create(organization=club, department=department, title='Übungsabend',
        starts_at=month, ends_at=month.replace(hour=22), visibility='members', share_up=True)
Event.objects.create(organization=club, title='Nachtwanderung',
    starts_at=month.replace(hour=23, minute=5), ends_at=month.replace(day=6, hour=1, minute=5),
    visibility='members')
# Ein empfangenes Schreiben mit echtem PDF, ausschließlich für die wegwerfbare Bilderdatenbank.
import io
from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.pdfgen import canvas
from portal.models import PortalAccess
from circulars.models import Circular, CircularRecipient, CircularAttachment
access = PortalAccess.objects.filter(user__email='mitglied@hubertus-grimlinghausen.test').select_related('organization').first()
if access:
    letter = Circular.objects.create(organization=access.organization, subject='Einladung zur Mitgliederversammlung',
        body='**Einladung**\\n\\nBitte bringe mit:\\n- Deinen Mitgliedsausweis\\n- Einen Stift\\n\\n1. Ankommen\\n2. Anmelden\\n\\n[Weitere Informationen](https://example.org)',
        kind='notice', status='sent', sent_at=timezone.now())
    CircularRecipient.objects.create(circular=letter, club=access.organization, membership_id=access.membership_id,
        channel='app', status='sent', sent_at=timezone.now())
    pdf = io.BytesIO()
    page = canvas.Canvas(pdf)
    page.drawString(72, 760, 'Einladung zur Mitgliederversammlung - erfundene Beispieldaten')
    page.showPage()
    page.save()
    attachment = CircularAttachment(circular=letter, name='Einladung.pdf', size=len(pdf.getvalue()))
    attachment.file.save('Einladung.pdf', ContentFile(pdf.getvalue()))
" > /dev/null
echo "Backend mit Demodaten bereit"

docker run -d --name "$ID-web" --network "$ID" --network-alias web "$CPUS" \
    -v "$WORK/frontend:/app" -v hubiplan-npm-cache:/root/.npm -w /app \
    -e BACKEND_URL=http://backend:8000 -e __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=web \
    node:24-alpine sh -c "npm ci --no-audit --no-fund --loglevel=error > /dev/null && npx vite --host 0.0.0.0 --port 5173" > /dev/null
until docker run --rm --network "$ID" node:24-alpine wget -q -O /dev/null http://web:5173/ 2> /dev/null; do
    docker inspect -f '{{.State.Running}}' "$ID-web" | grep -q true || { docker logs "$ID-web" | tail -30; exit 1; }
    sleep 3
done
echo "Oberfläche bereit"

mkdir -p "$ROOT/frontend/public/hilfe-bilder"
docker run --rm --name "$ID-pw" --network "$ID" "$CPUS" --ipc=host \
    -v "$WORK/frontend:/app" -v "$ROOT/frontend/public/hilfe-bilder:/out" -v hubiplan-npm-cache:/root/.npm \
    -e BASE_URL=http://web:5173 -e DEMO_PASSWORD="$PASSWORD" -e OUT=/out -w /app/scripts \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e npm_config_cache=/tmp/.npm \
    "$PW_IMAGE" sh -c "npm i --no-save --no-audit --no-fund --loglevel=error --prefix /app/scripts playwright@$PLAYWRIGHT_VERSION > /dev/null && node hilfe-bilder.mjs $*"
echo "Fertig: frontend/public/hilfe-bilder/ (Bilder ansehen, dann einchecken)"
