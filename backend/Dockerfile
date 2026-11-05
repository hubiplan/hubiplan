FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Im Betrieb nur die Laufzeit-Abhängigkeiten; scripts/test.sh baut mit
# --build-arg REQUIREMENTS=requirements-dev.txt (pytest, ruff)
ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r "$REQUIREMENTS"

# XRechnung: lokale XSD-/Schematron-Prüfung. Keine Rechnungsdaten an externe Dienste.
COPY install_einvoice_validator.py install_pdf_validator.py ./
RUN apt-get update -q && apt-get install -y -q --no-install-recommends default-jre-headless ghostscript > /dev/null \
    && rm -rf /var/lib/apt/lists/* \
    && python install_einvoice_validator.py /opt/hubiplan-einvoice \
    && python install_pdf_validator.py

COPY . .

# Statische Dateien schon beim Bauen einsammeln: Im Betrieb ist das Dateisystem
# schreibgeschützt (read_only in docker-compose.server.yml). Ohne die Dateien von
# DRF (Bootstrap, jQuery, Font Awesome): Die HTML-Ansicht der API ist aus, und so
# gehen keine fremden Dateien ohne Lizenzhinweis an den Browser (Lizenzaudit 31.10., L06).
RUN DJANGO_DEBUG=true DJANGO_SECRET_KEY=nur-zum-bauen python manage.py collectstatic --noinput -v0 --ignore rest_framework
# Übersetzungen (konzepte/englisch.md): .po → .mo beim Bauen. GNU gettext bleibt nur im
# Testabbild (scripts/test.sh prüft damit den Katalog), im Betrieb wird es wieder entfernt.
RUN apt-get update -q && apt-get install -y -q --no-install-recommends gettext > /dev/null \
    && DJANGO_DEBUG=true DJANGO_SECRET_KEY=nur-zum-bauen python manage.py compilemessages -v0 \
    && if [ "$REQUIREMENTS" = requirements.txt ]; then \
           apt-get purge -y -q gettext > /dev/null && apt-get autoremove -y -q > /dev/null; fi \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 app && mkdir -p /app/media /app/private /app/loeschliste /app/upload-tmp && chown -R app /app
USER app

EXPOSE 8000
ENTRYPOINT ["sh", "./docker-entrypoint.sh"]
# Ohne Steuer-Socket: braucht kein beschreibbares Home-Verzeichnis und ist eine Angriffsfläche weniger.
# 3 Prozesse mit je 4 Threads: Bilder der Webseite und die Bedienung warten nicht
# aufeinander (vorher 1 Anfrage je Prozess). Anpassen ohne Neubau: GUNICORN_CMD_ARGS.
# Zugriffslog mit Antwortzeit in Sekunden (letzte Spalte), ohne IP-Adresse, ohne Abfrage
# (?…) und ohne Referer: Schlüssel in Adressen landen so in keinem Log.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "gthread", "--threads", "4", "--no-control-socket", "--access-logfile", "-", "--access-logformat", "%(t)s \"%(m)s %(U)s\" %(s)s %(b)s %(L)s"]
