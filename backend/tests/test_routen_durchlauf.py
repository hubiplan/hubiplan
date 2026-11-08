"""Durchlauf über alle Routen: Mandantentrennung als Dauertest (Gesamtaudit 08.11., F-06).

1. Ohne Anmeldung: Jede Route, die nicht ausdrücklich offen ist (``AllowAny`` oder keine
   Anmeldeklassen), darf auf GET nicht mit 2xx antworten.
2. Fremder Verein: Ein Vorstand mit allen Rechten und Modulen in Verein A ruft jede Route mit
   ``org_id`` von Verein B auf (GET, POST, PATCH, DELETE mit leerem Inhalt). Erlaubt sind nur
   401, 403, 404 und 405. Eine 400 hieße: Die Anfrage kam bis zur Prüfung der Eingaben.
3. Fremdes Objekt: Derselbe Vorstand ruft Detailrouten unter Verein A mit Kennungen von
   Objekten aus Verein B (Demoverein) auf. Auch hier nur 401/403/404/405.
4. Keine Route antwortet mit 5xx.

Alles läuft in der eingeschränkten Rolle der Anwendung (RLS aktiv). Begründete Ausnahmen
stehen in ``AUSNAHMEN`` (Muster der Route → Grund). Dauer: einige Minuten.
"""

import io
import re
import uuid

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from .factories import give_role, make_org, make_user
from .verbund_netz import app_role

ABGELEHNT = {401, 403, 404, 405}

# Muster der Route (wie von Django ausgegeben) → Grund. Nur mit Begründung ergänzen.
AUSNAHMEN: dict[str, str] = {}

_ROUTE_PARAM = re.compile(r"<(?:(\w+):)?(\w+)>")
_REGEX_PARAM = re.compile(r"\(\?P<(\w+)>[^)]*\)")


def _walk(resolver, prefix=""):
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p


def _params(pattern: str) -> list[str]:
    return [m.group(2) for m in _ROUTE_PARAM.finditer(pattern)] + [
        m.group(1) for m in _REGEX_PARAM.finditer(pattern)
    ]


def _build(pattern: str, values: dict) -> str | None:
    """Platzhalter ersetzen; None, wenn das Muster nicht sauber auflösbar ist."""
    if "format" in pattern:
        return None

    def route(m):
        conv, name = m.group(1) or "str", m.group(2)
        if name in values:
            return str(values[name])
        return {"int": "1", "uuid": str(uuid.UUID(int=1)), "slug": "x", "path": "x"}.get(conv, "x")

    url = _ROUTE_PARAM.sub(route, pattern)
    url = _REGEX_PARAM.sub(lambda m: str(values.get(m.group(1), "1")), url)
    url = url.replace("^", "").replace("$", "").replace("\\.", ".").replace("\\", "")
    if any(ch in url for ch in "()[]*+?|{}"):
        return None
    return "/" + url.lstrip("/")


def _info(p: URLPattern) -> dict:
    cb = p.callback
    cls = getattr(cb, "cls", None) or getattr(cb, "view_class", None)
    info = {"view": f"{cb.__module__}.{getattr(cls, '__name__', cb.__name__)}", "model": None}
    if cls is not None:
        info["auth"] = [c.__name__ for c in (getattr(cls, "authentication_classes", None) or [])]
        info["perm"] = [c.__name__ for c in (getattr(cls, "permission_classes", None) or [])]
        qs = getattr(cls, "queryset", None)
        meta = getattr(getattr(cls, "serializer_class", None), "Meta", None)
        if qs is not None:
            info["model"] = qs.model._meta.label
        elif meta is not None and getattr(meta, "model", None) is not None:
            info["model"] = meta.model._meta.label
    return info


def _offen(info) -> bool:
    return "AllowAny" in info.get("perm", []) or info.get("auth") == []


def _pks(model_label: str, org) -> list[int]:
    from django.apps import apps

    from core.tenancy import rls_bypass

    model = apps.get_model(model_label)
    if "organization" not in {f.name for f in model._meta.get_fields()}:
        return []
    with rls_bypass():
        return list(model._base_manager.filter(organization=org).values_list("pk", flat=True)[:3])


def _call(client, method, url):
    if method == "get":
        return client.get(url)
    return getattr(client, method)(url, {}, content_type="application/json")


@pytest.fixture
def welt(db, settings, tmp_path):
    from access.modules import MODULE_IDS
    from organizations.models import Organization

    settings.PRIVATE_ROOT = tmp_path / "private"
    settings.CELERY_TASK_ALWAYS_EAGER = True
    call_command("seed_demoverein", password="Erfunden-Passwort-1", stdout=io.StringIO())
    b = Organization.objects.filter(type="club").order_by("-pk").first()
    a = make_org("Verein A Durchlauf", enabled_modules=list(MODULE_IDS))
    user = make_user("durchlauf-a@example.org")
    give_role(user, a)
    return {"a": a, "b": b, "user": user}


@pytest.mark.django_db(transaction=True)
def test_routen_durchlauf(welt):
    a, b, user = welt["a"], welt["b"], welt["user"]
    assert b is not None and b.pk != a.pk
    routes = [(pat, _info(p)) for pat, p in _walk(get_resolver())]
    funde: list[str] = []
    anon, vorstand = Client(raise_request_exception=False), Client(raise_request_exception=False)
    vorstand.force_login(user)

    def melden(pat, text):
        if pat not in AUSNAHMEN:
            funde.append(f"{pat}: {text}")

    with app_role():
        for pat, info in routes:
            if not pat.startswith(("api/", "_allauth/")):
                continue
            url = _build(pat, {"org_id": b.pk})
            if url is None:
                continue
            r = anon.get(url)
            if 200 <= r.status_code < 300 and not _offen(info):
                melden(pat, f"ohne Anmeldung GET {url} -> {r.status_code}")
            if r.status_code >= 500:
                melden(pat, f"ohne Anmeldung GET {url} -> {r.status_code}")

        for pat, info in routes:
            if "org_id" not in _params(pat) or _offen(info):
                continue
            url = _build(pat, {"org_id": b.pk})
            if url is None:
                continue
            for method in ("get", "post", "patch", "delete"):
                r = _call(vorstand, method, url)
                if r.status_code not in ABGELEHNT:
                    melden(pat, f"fremder Verein {method.upper()} {url} -> {r.status_code}")

        for pat, info in routes:
            names = _params(pat)
            if "org_id" not in names or len(names) != 2 or _offen(info) or not info["model"]:
                continue
            other = next(n for n in names if n != "org_id")
            for pk in _pks(info["model"], b):
                url = _build(pat, {"org_id": a.pk, other: pk})
                if url is None:
                    continue
                for method in ("get", "patch", "delete"):
                    r = _call(vorstand, method, url)
                    if r.status_code not in ABGELEHNT:
                        melden(pat, f"fremdes Objekt {method.upper()} {url} -> {r.status_code}")

    assert not funde, "\n".join(funde)
