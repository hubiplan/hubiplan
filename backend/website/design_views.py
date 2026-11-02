"""Designpakete unter Webseite › Gestaltung: einspielen, freigeben, exportieren, löschen.

Einspielen, Freigeben und Löschen dürfen nur Plattformverwalter (ein Paket ist
Gestaltungscode); exportieren darf, wer die Webseite verwaltet und das Paket nutzen darf.
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

from . import design_packages
from .models import DesignPackage
from .views import _WebsiteMixin, can_import_designs

IN_USE = gettext_noop(
    "Eine Webseite nutzt dieses Design noch. Bitte dort zuerst ein anderes wählen."
)


def package_data(package: DesignPackage, website) -> dict:
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
        "created_at": package.created_at,
        "updated_at": package.updated_at,
    }


class _PackageMixin(_WebsiteMixin):
    def require_admin(self):
        if WEBSITE_MANAGE not in self.org_permissions or not can_import_designs(self.request.user):
            raise PermissionDenied(_("Designpakete spielen nur Plattformverwalter ein."))

    def package(self, key: str) -> DesignPackage:
        package = DesignPackage.objects.filter(key=key).first()
        if package is None:
            raise NotFound(_("Dieses Designpaket gibt es nicht."))
        return package


class DesignPackageListView(_PackageMixin, APIView):
    """GET: alle Pakete (nur Plattformverwalter) · POST: Paket prüfen oder einspielen."""

    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, org_id: int):
        self.require_admin()
        website = self.website()
        packages = DesignPackage.objects.prefetch_related("websites")
        return Response([package_data(p, website) for p in packages])

    @transaction.atomic
    def post(self, request, org_id: int):
        self.require_admin()
        website = self.website()
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
        existing = DesignPackage.objects.filter(key=package.key).first()
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
            obj = DesignPackage.objects.create(key=package.key, created_by=request.user, **fields)
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
            {"Designpaket": [None, f"{obj.label} ({obj.key}), freigegeben für diese Webseite"]},
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
        self.require_admin()
        website = self.website()
        package = self.package(key)
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
        self.require_admin()
        self.website()
        package = self.package(key)
        from .models import Website

        if Website.objects.filter(design=package.key).exists():
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
            not can_import_designs(request.user)
            and not package.websites.filter(pk=website.pk).exists()
        ):
            raise NotFound(_("Dieses Designpaket gibt es nicht."))
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
