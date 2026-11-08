"""Ranglisten im Mitgliederbereich und in der App (konzepte/schiessen-android.md, Schritt SB4).

Mitglieder sehen genau das, was die Webseite des Vereins zu Wettbewerben zeigt: nur
veröffentlichte Wettbewerbe (live oder nach Abschluss), im eingestellten Umfang (Preisplätze
oder ganze Rangliste) und mit den Einwilligungen der Webseite. Anders als die Webseite gilt
das auch, solange die Webseite selbst noch nicht öffentlich ist (Wartungsseite).
"""

from __future__ import annotations

from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import rls_bypass

from .views import MODULE

# Öffentliche Adressen der Webseite braucht die App nicht
_DROP = ("url", "version_url")


def _site(request, access_id: int):
    """Webseite des Vereins zum Zugang, wenn sie Ergebnisse zeigt, sonst ``None``."""
    from portal.views import _portal_access
    from website import results
    from website.public import SiteView

    access = _portal_access(request.user, access_id)
    club = access.organization
    if MODULE not in (club.enabled_modules or []):
        return None
    website = getattr(club, "site", None)
    if website is None:
        return None
    site = SiteView(website, request.build_absolute_uri("/"))
    return site if results.enabled(site) else None


def _clean(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in _DROP}


class _PortalRankings(APIView):
    def dispatch(self, request, *args, **kwargs):
        # Wie die öffentliche Webseite: Umfang und Namen regelt website.results
        with rls_bypass():
            return super().dispatch(request, *args, **kwargs)

    def finish(self, data) -> Response:
        resp = Response(data)
        resp["Cache-Control"] = "private, no-store"
        return resp


class PortalRankingsView(_PortalRankings):
    """GET: veröffentlichte Wettbewerbe des Vereins, neueste zuerst."""

    def get(self, request, access_id: int):
        from website import results

        site = _site(request, access_id)
        if site is None:
            return self.finish({"competitions": [], "poll_seconds": results.POLL_SECONDS})
        return self.finish(
            {
                "competitions": [_clean(results.summary(site, c)) for c in results.published(site)],
                "poll_seconds": results.POLL_SECONDS,
            }
        )


class PortalRankingView(_PortalRankings):
    """GET: Rangliste eines Wettbewerbs (``?version=1``: nur der kleine Stand)."""

    def get(self, request, access_id: int, token: str):
        from website import results

        site = _site(request, access_id)
        comp = results.find(site, token) if site is not None else None
        if comp is None:
            raise Http404
        if request.query_params.get("version"):
            return self.finish(results.version(site, comp))
        return self.finish(_clean(results.detail(site, comp)))
