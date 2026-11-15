"""Designpakete unter Webseite › Gestaltung: einspielen, freigeben, exportieren, löschen.

Pakete der Installation spielen nur Plattformverwalter ein, geben sie frei und löschen sie
(ein Paket ist Gestaltungscode). Seit #481 spielt auch ein, wer die Webseite einer Einheit
verwaltet: Das Paket gilt dann nur für diese Einheit, ist für andere unsichtbar, und
Plattformverwalter können es sperren. Exportieren darf, wer die Webseite verwaltet und
das Paket nutzen darf.
Standarddesigns exportiert die Webseite selbst (``/design-paket/<schlüssel>.zip``), weil
nur sie deren CSS und Vorlagen kennt.
"""

from __future__ import annotations

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import WEBSITE_MANAGE
from audit.log import record
from core.tenancy import rls_bypass

from . import design_packages
from .models import DesignPackage
from .views import _WebsiteMixin, can_import_designs

IN_USE = gettext_noop(
    "Eine Webseite nutzt dieses Design noch. Bitte dort zuerst ein anderes wählen."
)
KEY_TAKEN = gettext_noop(
    "Diese Webseite hat schon ein Design „{k}“. Bitte ein anderes Kürzel wählen."
)
# Höchstens so viele eigene Pakete je Einheit (#481)
MAX_UNIT_PACKAGES = 10


def package_data(package: DesignPackage, website, can_change: bool = True) -> dict:
    users = list(package.websites.all())
    return {
        "key": package.key,
        "label": package.label,
        "label_en": package.label_en,
        "hint": package.hint,
        "released": any(w.pk == website.pk for w in users),
        "in_use": website.design == package.key,
        "released_count": len(users),
        "templates": sorted(package.templates),
        # „unit“: nur für diese Einheit eingespielt (#481), sonst für die Installation
        "scope": "unit" if package.organization_id else "installation",
        "blocked": package.blocked,
        "can_change": can_change,
        "created_at": package.created_at,
        "updated_at": package.updated_at,
    }


def unit_package_data(package: DesignPackage) -> dict:
    """Ein Paket einer Einheit in der Liste der Plattformverwalter."""
    return {
        "id": package.pk,
        "key": package.key,
        "label": package.label,
        "unit": package.organization.name if package.organization else "",
        "blocked": package.blocked,
        "css_bytes": len(package.css.encode()),
        "created_at": package.created_at,
        "updated_at": package.updated_at,
    }


def key_taken(website, key: str, package: DesignPackage | None = None) -> bool:
    """Gibt es für diese Webseite schon ein anderes freigegebenes Paket mit dem Kürzel?

    Die Webseite merkt sich das Design nur am Kürzel; zwei Pakete gleichen Kürzels
    (eines der Installation, eines der Einheit) dürfen nie zugleich freigegeben sein."""
    found = website.design_packages.filter(key=key)
    if package is not None and package.pk:
        found = found.exclude(pk=package.pk)
    return found.exists()


class _PackageMixin(_WebsiteMixin):
    def is_admin(self) -> bool:
        return can_import_designs(self.request.user)

    def require_manage(self):
        if WEBSITE_MANAGE not in self.org_permissions:
            raise PermissionDenied(_("Designpakete spielt ein, wer die Webseite verwaltet."))

    def require_admin(self):
        if WEBSITE_MANAGE not in self.org_permissions or not self.is_admin():
            raise PermissionDenied(_("Designpakete spielen nur Plattformverwalter ein."))

    def visible(self):
        """Pakete, die hier zu sehen sind: die der Einheit und die für ihre Webseite
        freigegebenen der Installation, für Plattformverwalter alle der Installation."""
        from django.db.models import Q

        installation = Q(organization__isnull=True)
        if not self.is_admin():
            installation &= Q(websites=self.website())
        ids = DesignPackage.objects.filter(Q(organization=self.org) | installation).values("pk")
        return DesignPackage.objects.filter(pk__in=ids)

    def package(self, key: str) -> DesignPackage:
        # Ein Paket der Einheit geht einem gleichnamigen der Installation vor
        found = sorted(self.visible().filter(key=key), key=lambda p: p.organization_id is None)
        if not found:
            raise NotFound(_("Dieses Designpaket gibt es nicht."))
        return found[0]

    def require_change(self, package: DesignPackage):
        """Pakete der Installation ändern nur Plattformverwalter, die der Einheit auch
        deren Webseitenverwaltung."""
        if package.organization_id is None:
            self.require_admin()
        else:
            self.require_manage()


class DesignPackageListView(_PackageMixin, APIView):
    """GET: Pakete der Einheit, für Plattformverwalter auch die der Installation ·
    POST: Paket prüfen oder einspielen (ohne Plattformrecht, oder mit ``unit``, nur für
    diese Einheit)."""

    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, org_id: int):
        self.require_manage()
        website = self.website()
        packages = self.visible().prefetch_related("websites")
        admin = self.is_admin()
        return Response(
            [package_data(p, website, admin or p.organization_id is not None) for p in packages]
        )

    @transaction.atomic
    def post(self, request, org_id: int):
        self.require_manage()
        website = self.website()
        for_unit = not self.is_admin() or request.data.get("unit") in ("1", "true", True)
        owner = self.org if for_unit else None
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": [_("Bitte ein Designpaket (ZIP) auswählen.")]})
        if upload.size > design_packages.MAX_ZIP_BYTES:
            raise ValidationError({"file": [_("Das Paket ist größer als 2 MB.")]})
        try:
            package = design_packages.read(
                upload.read(design_packages.MAX_ZIP_BYTES + 1),
                key=(request.data.get("key") or "").strip() or None,
                label=(request.data.get("label") or "").strip() or None,
                label_en=(request.data.get("label_en") or "").strip() or None,
            )
        except design_packages.PackageError as exc:
            raise ValidationError({"file": exc.problems}) from None
        existing = DesignPackage.objects.filter(key=package.key, organization=owner).first()
        if key_taken(website, package.key, existing):
            raise ValidationError({"key": [_(KEY_TAKEN).format(k=package.key)]})
        if (
            for_unit
            and existing is None
            and DesignPackage.objects.filter(organization=owner).count() >= MAX_UNIT_PACKAGES
        ):
            raise ValidationError(
                {
                    "file": [
                        _("Eine Einheit kann höchstens {n} eigene Designs einspielen.").format(
                            n=MAX_UNIT_PACKAGES
                        )
                    ]
                }
            )
        summary = {
            "key": package.key,
            "label": package.label,
            "label_en": package.label_en,
            "hint": package.hint,
            "sketch": package.sketch_like,
            "roles": sorted(package.roles),
            "templates": sorted(package.templates),
            "css_bytes": len(package.css.encode()),
            "warnings": package.warnings,
            "source": package.source,
            "exists": existing is not None,
            "scope": "unit" if for_unit else "installation",
        }
        if request.data.get("check") in ("1", "true", True):
            return Response({"ok": True, "package": summary})
        if existing is not None and request.data.get("replace") not in ("1", "true", True):
            raise ValidationError(
                {"key": [_("Ein Designpaket „{k}“ gibt es schon.").format(k=package.key)]}
            )
        fields = {
            "label": package.label,
            "label_en": package.label_en,
            "hint": package.hint,
            "hint_en": package.hint_en,
            "roles": package.roles,
            "sketch_like": package.sketch_like,
            "css": package.css,
            "templates": package.templates,
            "content_hash": package.content_hash,
        }
        if existing is None:
            obj = DesignPackage.objects.create(
                key=package.key, organization=owner, created_by=request.user, **fields
            )
            action = "create"
        else:
            obj = existing
            for k, v in fields.items():
                setattr(obj, k, v)
            obj.save()
            action = "update"
        obj.websites.add(website)
        # Aus einem Standarddesign exportiert: dessen Farbzuordnung dieser Webseite übernehmen
        # (das alte Klassisch sieht als „Hubertus“ genauso aus)
        roles = dict(website.color_roles or {})
        if package.source and package.source in roles and obj.key not in roles:
            roles[obj.key] = roles[package.source]
            website.color_roles = roles
            website.save(update_fields=["color_roles"])
        record(
            self.org,
            request.user,
            action,
            obj,
            {
                "Designpaket": [
                    None,
                    f"{obj.label} ({obj.key}), "
                    + ("nur für diese Einheit" if for_unit else "freigegeben für diese Webseite"),
                ]
            },
        )
        return Response(
            {"ok": True, "package": package_data(obj, website)},
            status=201 if action == "create" else 200,
        )


class DesignPackageDetailView(_PackageMixin, APIView):
    """PATCH: für diese Webseite freigeben oder nicht · DELETE: Paket löschen."""

    parser_classes = [JSONParser]

    @transaction.atomic
    def patch(self, request, org_id: int, key: str):
        self.require_manage()
        website = self.website()
        package = self.package(key)
        self.require_change(package)
        released = request.data.get("released")
        if not isinstance(released, bool):
            raise ValidationError({"released": [_("Bitte ja oder nein angeben.")]})
        if not released and website.design == package.key:
            raise ValidationError(
                {
                    "released": [
                        _("Die Webseite nutzt dieses Design. Bitte zuerst ein anderes wählen.")
                    ]
                }
            )
        if released and key_taken(website, package.key, package):
            raise ValidationError({"released": [_(KEY_TAKEN).format(k=package.key)]})
        if released:
            package.websites.add(website)
        else:
            package.websites.remove(website)
        record(
            self.org,
            request.user,
            "update",
            package,
            {"Freigabe für diese Webseite": [not released, released]},
        )
        return Response(package_data(package, website))

    @transaction.atomic
    def delete(self, request, org_id: int, key: str):
        self.require_manage()
        self.website()
        package = self.package(key)
        self.require_change(package)
        if package.websites.filter(design=package.key).exists():
            raise ValidationError({"key": [_(IN_USE)]})
        record(self.org, request.user, "delete", package, {"Designpaket": [package.label, None]})
        package.delete()
        return Response(status=204)


class DesignPackageExportView(_PackageMixin, APIView):
    """GET: Paket als ZIP (zum Sichern und Übertragen auf eine andere Installation)."""

    def get(self, request, org_id: int, key: str):
        if WEBSITE_MANAGE not in self.org_permissions:
            raise NotFound()
        website = self.website()
        package = self.package(key)
        if (
            package.organization_id is None
            and not self.is_admin()
            and not package.websites.filter(pk=website.pk).exists()
        ):
            raise NotFound(_("Dieses Designpaket gibt es nicht."))
        if package.templates:
            raise ValidationError(design_packages.template_problems("", ""))
        data = design_packages.build_zip(
            key=package.key,
            label=package.label,
            label_en=package.label_en,
            hint=package.hint,
            hint_en=package.hint_en,
            roles=package.roles,
            sketch_like=package.sketch_like,
            css=package.css,
            templates=package.templates,
            exported=timezone.localdate().isoformat(),
        )
        response = HttpResponse(data, content_type="application/zip")
        name = f"design-{package.key}-{timezone.localdate().isoformat()}.zip"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class UnitDesignPackageListView(_PackageMixin, APIView):
    """Plattformverwalter: Designpakete aller Einheiten, zum Prüfen und Sperren (#481).

    GET: Liste · PATCH ``{"id": …, "blocked": true|false}``: sperren oder freigeben. Ein
    gesperrtes Paket zeigt keine Webseite mehr; wer es nutzt, sieht Klassisch."""

    parser_classes = [JSONParser]

    def get(self, request, org_id: int):
        self.require_admin()
        # Pakete aller Einheiten: am Zeilenschutz der Einheit vorbei, nur Plattformverwalter
        with rls_bypass():
            packages = list(
                DesignPackage.objects.filter(organization__isnull=False).select_related(
                    "organization"
                )
            )
        return Response([unit_package_data(p) for p in packages])

    @transaction.atomic
    def patch(self, request, org_id: int):
        self.require_admin()
        blocked = request.data.get("blocked")
        if not isinstance(blocked, bool):
            raise ValidationError({"blocked": [_("Bitte ja oder nein angeben.")]})
        pk = request.data.get("id")
        with rls_bypass():
            return Response(self._block(request, pk, blocked))

    def _block(self, request, pk, blocked: bool) -> dict:
        package = (
            DesignPackage.objects.filter(pk=pk, organization__isnull=False)
            .select_related("organization")
            .first()
            if isinstance(pk, int) and not isinstance(pk, bool)
            else None
        )
        if package is None:
            raise NotFound(_("Dieses Designpaket gibt es nicht."))
        if package.blocked != blocked:
            package.blocked = blocked
            package.save(update_fields=["blocked", "updated_at"])
            # Ins Änderungsprotokoll der Einheit, der das Paket gehört
            record(
                package.organization,
                request.user,
                "update",
                package,
                {"gesperrt (Plattformverwaltung)": [not blocked, blocked]},
            )
        return unit_package_data(package)
