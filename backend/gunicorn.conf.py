"""Einstellungen für gunicorn (liest es selbst aus dem Arbeitsverzeichnis /app).

Vorwärmen: Jeder neue Prozess beantwortet vor der ersten echten Anfrage zwei Abrufe
an sich selbst. So lädt er Adressen, Ansichten und die Datenbankverbindung vorab;
sonst wartete der erste Besucher nach dem Ausrollen darauf.
"""

WARMUP_PATHS = ("/api/health/", "/api/public/site/v1/resolve/")


def post_worker_init(worker):
    warm_up(worker.wsgi, worker.log)


def warm_up(app, log) -> None:
    from django.db import connections

    try:
        _warm_up(app, log)
    finally:
        # gthread bearbeitet Anfragen in anderen Threads. Die hier geöffnete
        # Verbindung kann dort nicht wiederverwendet werden.
        connections.close_all()


def _warm_up(app, log) -> None:
    import io

    for path in WARMUP_PATHS:
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": path,
            "QUERY_STRING": "host=aufwaermen.invalid",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "HTTP_HOST": "localhost",
            "REMOTE_ADDR": "127.0.0.1",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(),
            "wsgi.errors": io.StringIO(),
            "wsgi.version": (1, 0),
            "wsgi.multithread": True,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
        }
        status: list[str] = []
        body = None
        try:
            body = app(environ, _collect(status))
            for _ in body:
                pass
            log.info("Vorwärmen %s: %s", path, status[0] if status else "?")
        except Exception as exc:  # noqa: BLE001 – Vorwärmen darf den Start nie verhindern
            log.warning("Vorwärmen %s fehlgeschlagen: %s", path, exc)
        finally:
            if body is not None and hasattr(body, "close"):
                try:
                    body.close()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Vorwärmen %s: Schließen fehlgeschlagen: %s", path, exc)


def _collect(status: list[str]):
    def start_response(value, headers, exc_info=None):
        status.append(value)

    return start_response
