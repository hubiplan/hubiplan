from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import Http404, JsonResponse
from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from devices import passkey as app_passkey


class SwaggerView(SpectacularSwaggerView):
    """Swagger-Oberfläche nur, wenn eingeschaltet (lädt Code von einem CDN)."""

    def get(self, request, *args, **kwargs):
        if not settings.API_DOCS_ENABLED:
            raise Http404
        return super().get(request, *args, **kwargs)


@csrf_exempt
def _allauth_gesperrt(request, *args, **kwargs):
    """Kontoverwaltung von allauth, die HUBIplan selbst abgesichert anbietet (siehe unten)."""
    return JsonResponse({"status": 404, "errors": [{"code": "not_found"}]}, status=404)


urlpatterns = [
    # E-Mail-Adressen und Passwort ändert HUBIplan selbst (accounts/self_service.py: Passwort
    # nötig, alte Adresse bestätigt, Hinweismail). allauths eigene Verwaltung verlangte nichts
    # davon: Mit einer übernommenen Sitzung ließ sich eine zweite Adresse anhängen und darüber
    # das Passwort neu setzen (Gesamtaudit 15.11., AUTH-02). Deshalb hier gesperrt, vor dem
    # Einbinden von allauth.
    re_path(
        r"^_allauth/(?:browser|app)/v1/account/(?:email|phone|password/change)/?$",
        _allauth_gesperrt,
    ),
    # Anmeldung, Abmeldung, 2FA (allauth headless, eigene OpenAPI-Doku unter
    # /_allauth/openapi.html)
    path("_allauth/", include("allauth.headless.urls")),
    path("api/", include("core.urls")),
    # Passkeys in der Android-App: welche Apps diese Adresse nutzen dürfen (devices/passkey.py)
    path(".well-known/assetlinks.json", app_passkey.assetlinks, name="assetlinks"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Anmeldung der KI-Assistenten: Beschreibungen unter /.well-known/ (docs/mcp.md)
    path("", include("mcpserver.urls_root")),
    path("api/docs/", SwaggerView.as_view(url_name="schema"), name="docs"),
]


def _admin_nur_mit_2fa(request) -> bool:
    """Admin nur für aktive Superuser mit eingerichteter Zwei-Faktor-Anmeldung.

    Mit eingerichtetem zweiten Faktor verlangt die Anmeldung ihn auch (allauth); eine reine
    Passwortsitzung eines Superusers ohne 2FA kommt so nicht in den Admin, der Rechte und
    Zeilenschutz übergeht (Gesamtaudit 15.11., AUTH-04)."""
    from accounts.mfa_policy import has_mfa

    user = request.user
    return bool(user.is_active and user.is_superuser and has_mfa(user))


if settings.ADMIN_ENABLED:
    admin.site.has_permission = _admin_nur_mit_2fa
    urlpatterns += [
        # Der Admin hat eine eigene Passwort-Anmeldung ohne Zwei-Faktor-Abfrage.
        # Deshalb führt sie zur normalen Anmeldung; danach gilt die Sitzung auch hier.
        path("admin/login/", RedirectView.as_view(url="/anmelden", query_string=False)),
        path("admin/", admin.site.urls),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
