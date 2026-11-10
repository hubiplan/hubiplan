"""Verwaltung der Webseite in HUBIplan (Einrichtung, Zustand, Domains, Vorschau)
und Einwilligungen zur Veröffentlichung in der Mitgliederakte."""

from __future__ import annotations

import datetime
import re
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import get_language, gettext
from django.utils.translation import gettext as _
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    CHRONICLE_EDIT,
    CHRONICLE_VIEW,
    MEMBERS_EDIT,
    WEBCONTENT_VIEW,
    WEBSITE_CONTENT,
    WEBSITE_MANAGE,
    WEBSITE_VIEW,
)
from access.modules import module_on
from audit.log import diff, record, snapshot
from core.api_base import ModelCleanMixin, OrgScopedMixin
from core.tenancy import rls_bypass
from members.models import Membership
from members.views import _ClubMixin
from organizations.models import Organization
from organizations.theme import effective_theme

from . import designs, home, menu, privacy, services, style
from .models import (
    BLOCK_HINTS,
    BLOCK_NAME_MAX,
    BLOCKS,
    DEFAULT_HOME_OFF,
    DESIGN_VERSIONS,
    DRAFT_FIELDS,
    HOME_HINTS,
    HOME_NEEDS_BLOCK,
    HOME_SECTIONS,
    HOSTNAME_RE,
    LINK_URL_MAX,
    PREVIEW_LINK_MAX_DAYS,
    DesignVersion,
    PreviewLink,
    PublicationConsent,
    Website,
    WebsiteDomain,
    WebsiteImage,
    blocks_without_module,
    home_without_module,
    is_extra_block,
    is_heading_key,
    is_link_key,
    is_renamable,
    normalize_home_sections,
)

MAX_HEADINGS = 20
MAX_LINKS = 10
MENU_ITEM_FIELDS = (
    "label",
    "default_label",
    "renamable",
    "hint",
    "toggle",
    "heading",
    "parent",
    "url",
)

SETTINGS_FIELDS = [
    "state",
    "maintenance_text",
    "blocks",
    "menu",
    "block_names",
    "menu_links",
    "menu_button",
    "home_sections",
    "design",
    "color_roles",
    "style",
    "name_format",
    "show_vacant",
    "show_instrument",
    "show_address",
    "show_member_since",
    "missing_consent",
    "units_mode",
    "unit_ids",
    "include_unit_events",
    "include_parent_events",
    "include_parent_honors",
    "allow_indexing",
    "language",
    "contact_limit_per_hour",
    "privacy_mode",
    "privacy_text",
    "privacy_url",
]


class WebsiteSerializer(ModelCleanMixin, serializers.ModelSerializer):
    # Kopfbild (Ralf 05.11.): Nummer eines Bildes der Bilderverwaltung oder null
    header_image = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = Website
        fields = [*SETTINGS_FIELDS, "header_image"]

    def validate_header_image(self, value):
        if value is not None and (
            self.instance is None
            or not WebsiteImage.objects.filter(website=self.instance, pk=value).exists()
        ):
            raise serializers.ValidationError(_("Unbekanntes Bild."))
        return value

    def update(self, instance, validated_data):
        if "header_image" in validated_data:
            set_header_image(instance, validated_data.pop("header_image"))
        return super().update(instance, validated_data)

    def validate_language(self, value):
        # Nur freigeschaltete Sprachen (HUBIPLAN_LANGUAGES); die bisherige bleibt erlaubt
        from core.i18n import available

        current = self.instance.language if self.instance else "de"
        if value != current and value not in available():
            raise serializers.ValidationError(
                _("Diese Sprache ist auf diesem Server nicht freigeschaltet.")
            )
        return value

    def validate_unit_ids(self, value):
        if not isinstance(value, list) or not all(isinstance(v, int) for v in value):
            raise serializers.ValidationError(
                gettext("Bitte eine Liste von Untereinheiten angeben.")
            )
        org = self.context["org"]
        known = set(services.units_below(org).values_list("pk", flat=True))
        if set(value) - known:
            raise serializers.ValidationError(gettext("Unbekannte Untereinheit."))
        return sorted(set(value))

    def validate_blocks(self, value):
        if not isinstance(value, dict) or not all(isinstance(v, bool) for v in value.values()):
            raise serializers.ValidationError(gettext("Bausteine bitte als Schalter angeben."))
        result = {key: bool(value.get(key, True)) for key in BLOCKS}
        # Unterpunkte von „Würdenträger“ (je Würde, Ehrungen): nur bekannte, nur „aus“ merken
        if self.instance is not None:
            toggles = {
                item["toggle"]
                for item in menu.items(self.instance).values()
                if is_extra_block(item["toggle"])
            }
            for key, on in value.items():
                # Listen je Mitgliedsart sind ohne Eintrag aus: dort zählt auch „an“
                if key in toggles and (not on or key.startswith("membertype:")):
                    result[key] = on
        return result

    def validate_home_sections(self, value):
        try:
            return home.validate(value, self.instance, HOME_SECTIONS, DEFAULT_HOME_OFF)
        except home.Invalid as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_block_names(self, value):
        # Eigene Namen der Bausteine: nur bekannte Schlüssel, leer = Standardname
        if not isinstance(value, dict) or not all(
            isinstance(v, str) or v is None for v in value.values()
        ):
            raise serializers.ValidationError(_("Bitte die Namen der Bausteine als Text angeben."))
        result = {}
        for key, name in value.items():
            if not is_renamable(key):
                raise serializers.ValidationError(
                    _("Dieser Baustein lässt sich nicht umbenennen: {key}").format(key=key)
                )
            name = " ".join((name or "").split())
            if len(name) > BLOCK_NAME_MAX:
                raise serializers.ValidationError(
                    _("Ein Name darf höchstens {n} Zeichen lang sein.").format(n=BLOCK_NAME_MAX)
                )
            if name:
                result[key] = name
        if sum(1 for key in result if is_heading_key(key)) > MAX_HEADINGS:
            raise serializers.ValidationError(
                _("Höchstens {n} eigene Überschriften.").format(n=MAX_HEADINGS)
            )
        return result

    def validate_menu_links(self, value):
        # Links nach außen (Ralf 10.11.): nur http(s), höchstens MAX_LINKS
        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Bitte die Links als Liste angeben."))
        check = URLValidator(schemes=["http", "https"])
        result = {}
        for key, url in value.items():
            if not is_link_key(key):
                raise serializers.ValidationError(_("Unbekannter Link: {key}").format(key=key))
            url = (url or "").strip() if isinstance(url, str) or url is None else None
            if url is None:
                raise serializers.ValidationError(_("Bitte die Adresse als Text angeben."))
            if not url:
                continue
            if len(url) > LINK_URL_MAX:
                raise serializers.ValidationError(
                    _("Eine Adresse darf höchstens {n} Zeichen lang sein.").format(n=LINK_URL_MAX)
                )
            try:
                check(url)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(
                    _("Bitte eine vollständige Adresse mit https:// angeben: {url}").format(url=url)
                ) from exc
            result[key] = url
        if len(result) > MAX_LINKS:
            raise serializers.ValidationError(_("Höchstens {n} Links im Menü.").format(n=MAX_LINKS))
        return result

    def _pending_menu(self) -> tuple[dict | None, dict | None]:
        """Namen und Adressen aus derselben Änderung (neue Überschriften und Links)."""
        data = self.initial_data if hasattr(self, "initial_data") else {}
        names, links = data.get("block_names"), data.get("menu_links")
        try:
            names = self.validate_block_names(names) if names is not None else None
        except serializers.ValidationError:
            names = None
        try:
            links = self.validate_menu_links(links) if links is not None else None
        except serializers.ValidationError:
            links = None
        return names, links

    def validate_menu(self, value):
        if self.instance is None:
            return []
        names, links = self._pending_menu()
        try:
            return menu.validate(value, menu.items(self.instance, names=names, links=links))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_menu_button(self, value):
        value = (value or "").strip()
        if not value or self.instance is None:
            return ""
        names, links = self._pending_menu()
        item = menu.items(self.instance, names=names, links=links).get(value)
        if item is None or item["heading"]:
            raise serializers.ValidationError(
                _("Diesen Menüpunkt kann man nicht als Knopf hervorheben.")
            )
        return value

    def _package_roles(self) -> dict:
        return designs.package_roles(self.instance.packages()) if self.instance else {}

    def validate_design(self, value):
        allowed = self.instance.design_choices() if self.instance else set(designs.DESIGNS)
        if value not in allowed:
            raise serializers.ValidationError(
                _("Dieses Design gibt es nicht oder es ist für diese Webseite nicht freigegeben.")
            )
        return value

    def validate_style(self, value):
        try:
            return style.validate(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_color_roles(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(gettext("Farbzuordnung bitte je Design angeben."))
        return designs.normalize_color_roles(value, self._package_roles())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["home_sections"] = normalize_home_sections(instance.home_sections)
        data["menu"] = menu.normalize(instance.menu, menu.items(instance))
        data["color_roles"] = designs.normalize_color_roles(
            instance.color_roles, designs.package_roles(instance.packages())
        )
        data["design"] = instance.effective_design()
        data["header_image"] = header_image_id(instance)
        data["draft"] = clean_draft(instance, instance.draft)
        return data


# --- Entwurf der Gestaltung (Konzept webseite-baukasten G2) ---


def live_design(website: Website) -> dict:
    """Veröffentlichte Werte der Gestaltung, so wie die Oberfläche sie bekommt."""
    return {
        "design": website.effective_design(),
        "color_roles": designs.normalize_color_roles(
            website.color_roles, designs.package_roles(website.packages())
        ),
        "style": style.public(website.style),
        "header_image": header_image_id(website),
        "home_sections": normalize_home_sections(website.home_sections),
    }


def clean_draft(website: Website, draft) -> dict:
    """Nur Felder, die vom veröffentlichten Stand abweichen und noch gültig sind."""
    if not isinstance(draft, dict) or not draft:
        return {}
    ser = WebsiteSerializer(
        website, data={k: draft[k] for k in DRAFT_FIELDS if k in draft}, partial=True
    )
    if not ser.is_valid():
        # Was nicht mehr passt (z. B. gelöschtes Bild, entzogenes Paket), fällt weg
        valid = {}
        for key in DRAFT_FIELDS:
            if key in draft and key not in ser.errors:
                one = WebsiteSerializer(website, data={key: draft[key]}, partial=True)
                if one.is_valid():
                    valid[key] = one.validated_data[key]
        values = valid
    else:
        values = dict(ser.validated_data)
    live = live_design(website)
    return {k: values[k] for k in DRAFT_FIELDS if k in values and values[k] != live[k]}


def version_data(version: DesignVersion) -> dict:
    return {
        "id": version.pk,
        "published_at": version.published_at,
        "published_by": (version.published_by.get_full_name() or version.published_by.email)
        if version.published_by
        else "",
    }


def header_image_id(website: Website) -> int | None:
    return (
        WebsiteImage.objects.filter(website=website, header=True)
        .values_list("pk", flat=True)
        .first()
    )


def set_header_image(website: Website, pk: int | None) -> None:
    WebsiteImage.objects.filter(website=website, header=True).exclude(pk=pk).update(header=False)
    if pk is not None:
        WebsiteImage.objects.filter(website=website, pk=pk).update(header=True)


def can_import_designs(user) -> bool:
    from access.permissions import is_platform_admin

    return bool(user and user.is_authenticated and (user.is_superuser or is_platform_admin(user)))


def domain_data(d: WebsiteDomain) -> dict:
    return {"id": d.pk, "hostname": d.hostname, "is_primary": d.is_primary}


def link_data(link: PreviewLink) -> dict:
    return {
        "id": link.pk,
        "label": link.label,
        "expires_at": link.expires_at,
        "revoked_at": link.revoked_at,
        "is_active": link.is_active,
        "created_at": link.created_at,
        "created_by": (link.created_by.get_full_name() or link.created_by.email)
        if link.created_by
        else "",
    }


def site_url(website: Website) -> str | None:
    # Testserver: alle Webseiten laufen unter einer festen Adresse (z. B. …/webseite/)
    if settings.WEBSITE_PUBLIC_URL:
        return settings.WEBSITE_PUBLIC_URL.rstrip("/") + "/"
    primary = next(iter(website.domains.all()), None)
    return f"https://{primary.hostname}/" if primary else None


class _WebsiteMixin(OrgScopedMixin):
    """Lesen: Bereich Webseite (Inhalte oder Einrichtung) lesen · Ändern: Einrichtung bearbeiten.

    Ohne Leserecht antwortet die Schnittstelle mit 404 (die Webseite bleibt verborgen)."""

    allowed_org_types = (
        Organization.Type.FEDERATION,
        Organization.Type.CLUB,
        Organization.Type.UNIT,
    )
    read_permission = None
    write_permission = WEBSITE_MANAGE
    # Auch für die Pflege der Chronik (Modul „Chronik“, ohne Rechte an der Webseite)
    chronicle_ok = False
    via_chronicle = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.chronicle_ok and self._chronicle_only():
            self.via_chronicle = True
            if request.method not in ("GET", "HEAD", "OPTIONS") and (
                CHRONICLE_EDIT not in self.org_permissions
            ):
                raise NotFound()
            return
        if not ({WEBCONTENT_VIEW, WEBSITE_VIEW} & self.org_permissions):
            raise NotFound()
        if request.method not in ("GET", "HEAD", "OPTIONS") and not services.module_enabled(
            self.org
        ):
            raise NotFound(
                gettext("Das Modul „Webseite“ ist für diese Einheit nicht freigeschaltet.")
            )

    def _chronicle_only(self) -> bool:
        """Chronik pflegen, ohne Inhalte der Webseite bearbeiten zu dürfen."""
        if CHRONICLE_VIEW not in self.org_permissions or not module_on(self.org, "chronicle"):
            return False
        return not (
            {WEBSITE_CONTENT, WEBSITE_MANAGE} & self.org_permissions
            and services.module_enabled(self.org)
        )

    def website(self) -> Website:
        website = services.website_of(self.org)
        if website is None and self.via_chronicle:
            # Chronik ohne Webseite: Ablage für Text und Bilder, öffentlich aus
            website = Website.objects.create(
                organization=self.org, public_key=Website.new_key(), state=Website.State.OFF
            )
        if website is None:
            raise NotFound(gettext("Für diese Einheit ist keine Webseite eingerichtet."))
        return website


def home_choices(website: Website) -> dict:
    """Auswahl für die eigenen Abschnitte der Startseite: Rollen auf der Webseite, Alben
    der Galerie und kommende öffentliche Termine (je einmal, nach Datum)."""
    from events.models import Event
    from events.recurrence import occurrences

    from .content_models import GalleryAlbum
    from .public import SiteView

    site = SiteView(website)
    now = timezone.now()
    found = occurrences(
        Event.objects.filter(
            organization=site.area, visibility=Event.Visibility.PUBLIC, source_stale=False
        ),
        now,
        now + datetime.timedelta(days=home.EVENT_DAYS_AHEAD),
    )
    events, seen = [], set()
    for o in sorted(found, key=lambda o: o.starts_at):
        if o.event.pk not in seen and len(events) < 100:
            seen.add(o.event.pk)
            events.append({"id": o.event.pk, "title": o.event.title, "starts_at": o.starts_at})
    return {
        "roles": [{"id": r.pk, "name": r.name} for r in site.own_roles().filter(on_website=True)],
        "albums": [
            {"id": a.pk, "title": a.title}
            for a in GalleryAlbum.objects.filter(website=website).order_by("title", "pk")
        ],
        "events": events,
    }


class WebsiteView(_WebsiteMixin, APIView):
    """GET: Stand · POST: Webseite einrichten · PUT: Einstellungen · DELETE: entfernen."""

    def payload(self, website: Website | None) -> dict:
        # Bausteine abgeschalteter Module (z. B. „Ergebnisse“ ohne Wettbewerbe) fehlen
        hide = blocks_without_module(self.org)
        hide_home = home_without_module(self.org)
        data = {
            "module_enabled": services.module_enabled(self.org),
            "can_manage": WEBSITE_MANAGE in self.org_permissions,
            "can_edit_content": WEBSITE_CONTENT in self.org_permissions
            or WEBSITE_MANAGE in self.org_permissions,
            "preview_only": services.preview_only(),
            "block_labels": {
                **{k: v for k, v in BLOCKS.items() if k not in hide},
                "units": self.org.department_label_plural or BLOCKS["units"],
            },
            "block_hints": BLOCK_HINTS,
            "home_labels": {
                **{k: v for k, v in HOME_SECTIONS.items() if k not in hide_home},
                "units": self.org.department_label_plural or HOME_SECTIONS["units"],
            },
            "home_hints": HOME_HINTS,
            "home_needs_block": HOME_NEEDS_BLOCK,
            # Eigene Abschnitte der Startseite (G3): Arten mit Hinweis
            "home_kinds": home.KINDS,
            "home_kind_hints": home.KIND_HINTS,
            "home_kind_needs_block": home.KIND_NEEDS_BLOCK,
            "designs": designs.catalog(
                website.packages() if website else (), (get_language() or "de")[:2]
            ),
            # Stilregler: Stufen je Regler und Sperren je Design (Namen in der Oberfläche)
            "style_catalog": style.catalog(),
            # Designpakete einspielen und freigeben: nur Plattformverwalter
            "can_import_designs": can_import_designs(self.request.user),
            "units": [
                {"id": u.pk, "name": u.name}
                for u in services.in_tree_order(services.units_below(self.org))
            ],
            "website": None,
        }
        if website is not None:
            palette = effective_theme(self.org.ancestors())["palette"]
            data["palette"] = palette
            data["home_choices"] = home_choices(website)
            packages = website.packages()
            extra = designs.package_roles(packages)
            data["website"] = {
                **WebsiteSerializer(website).data,
                "public_key": website.public_key,
                "effective_state": services.effective_state(website),
                "url": site_url(website),
                # Farben je Rolle für alle Designs (Skizzen in der Auswahl)
                "design_colors": {
                    key: designs.resolve(key, palette, website.color_roles, extra)
                    for key in [*designs.DESIGNS, *extra]
                },
                "privacy_generated_at": website.privacy_generated_at,
                "privacy_published_text": website.privacy_published_text,
                "privacy_published_at": website.privacy_published_at,
                "checks": privacy.checks(website),
                # Mögliche Menüpunkte (Bausteine, Textseiten, Würden) in Standardreihenfolge
                "menu_items": [
                    {"key": key, **{f: item.get(f) for f in MENU_ITEM_FIELDS}}
                    for key, item in menu.items(website).items()
                ],
                "domains": [domain_data(d) for d in website.domains.all()],
                "design_versions": [
                    version_data(v)
                    for v in website.design_versions.select_related("published_by")[
                        :DESIGN_VERSIONS
                    ]
                ],
                "preview_links": [
                    link_data(link)
                    for link in website.preview_links.select_related("created_by")
                    if link.revoked_at is None
                ],
            }
        return data

    def get(self, request, org_id: int):
        return Response(self.payload(services.website_of(self.org)))

    @transaction.atomic
    def post(self, request, org_id: int):
        if services.website_of(self.org) is not None:
            raise ValidationError(gettext("Die Webseite ist schon eingerichtet."))
        website = Website.objects.create(organization=self.org, public_key=Website.new_key())
        record(self.org, request.user, "create", website, {"Webseite": [None, "eingerichtet"]})
        return Response(self.payload(website), status=status.HTTP_201_CREATED)

    @transaction.atomic
    def put(self, request, org_id: int):
        website = self.website()
        before = snapshot(website)
        old_state = website.state
        old_header = header_image_id(website)
        data = request.data
        if isinstance(data, dict) and "draft" in data:
            # Gestaltung als Entwurf: nur in der Vorschau sichtbar (G2)
            data = {k: v for k, v in data.items() if k != "draft"}
            given = request.data["draft"]
            if not isinstance(given, dict) or set(given) - set(DRAFT_FIELDS):
                raise ValidationError({"draft": [gettext("Unbekannte Angaben im Entwurf.")]})
            check = WebsiteSerializer(website, data=given, partial=True, context={"org": self.org})
            check.is_valid(raise_exception=True)
            website.draft = clean_draft(
                website, {**clean_draft(website, website.draft), **check.validated_data}
            )
            website.save(update_fields=["draft", "updated_at"])
        ser = WebsiteSerializer(website, data=data, partial=True, context={"org": self.org})
        ser.is_valid(raise_exception=True)
        ser.save()
        if website.state == Website.State.PUBLIC:
            missing = privacy.blocking(website)
            if old_state == Website.State.PUBLIC:
                # Schon öffentlich: nur verhindern, dass die Datenschutzhinweise wegfallen
                missing = [m for m in missing if m.startswith("Datenschutzhinweise")]
            if missing:
                raise ValidationError(
                    {"state": ["Vor dem Veröffentlichen fehlt noch: " + " · ".join(missing)]}
                )
        changes = diff(before, snapshot(website))
        new_header = header_image_id(website)
        if new_header != old_header:
            changes["Kopfbild"] = [old_header, new_header]
        if changes:
            record(self.org, request.user, "update", website, changes)
        return Response(self.payload(website))

    @transaction.atomic
    def delete(self, request, org_id: int):
        website = self.website()
        record(self.org, request.user, "delete", website, {"Webseite": ["eingerichtet", None]})
        website.delete()
        return Response(self.payload(None))


def _apply_design(website: Website, values: dict) -> None:
    for key in DRAFT_FIELDS:
        if key in values and key != "header_image":
            setattr(website, key, values[key])
    if "header_image" in values:
        set_header_image(website, values["header_image"])


class DesignPublishView(WebsiteView):
    """POST: Entwurf der Gestaltung veröffentlichen; die Fassung kommt in den Verlauf."""

    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        draft = clean_draft(website, website.draft)
        if not draft:
            raise ValidationError(
                {"draft": [gettext("Es gibt keine Änderungen zum Veröffentlichen.")]}
            )
        before = live_design(website)
        if not website.design_versions.exists():
            # Erste Veröffentlichung: der bisherige Stand bleibt zum Zurückholen
            DesignVersion.objects.create(
                organization=website.organization,
                website=website,
                data=before,
                published_at=website.updated_at or timezone.now(),
            )
        _apply_design(website, draft)
        website.draft = {}
        website.save()
        after = live_design(website)
        DesignVersion.objects.create(
            organization=website.organization,
            website=website,
            data=after,
            published_by=request.user,
        )
        old = list(website.design_versions.values_list("pk", flat=True)[DESIGN_VERSIONS:])
        if old:
            DesignVersion.objects.filter(pk__in=old).delete()
        record(
            self.org,
            request.user,
            "update",
            website,
            {f"Gestaltung: {k}": [before[k], after[k]] for k in draft},
        )
        return Response(self.payload(website))


class DesignDiscardView(WebsiteView):
    """POST: Entwurf der Gestaltung verwerfen."""

    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        website.draft = {}
        website.save(update_fields=["draft", "updated_at"])
        return Response(self.payload(website))


class DesignRestoreView(WebsiteView):
    """POST: frühere Fassung als Entwurf zurückholen; öffentlich erst nach „Veröffentlichen“."""

    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        website = self.website()
        version = get_object_or_404(DesignVersion, website=website, pk=pk)
        website.draft = clean_draft(website, version.data)
        website.save(update_fields=["draft", "updated_at"])
        return Response(self.payload(website))


class PrivacyGenerateView(WebsiteView):
    """POST: Datenschutzhinweise der Webseite aus den Einstellungen (neu) erzeugen."""

    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        before = snapshot(website)
        privacy.generate(website)
        website.privacy_mode = "text"
        website.save()
        changes = diff(before, snapshot(website))
        if changes:
            record(self.org, request.user, "update", website, changes)
        return Response(self.payload(website))


class PrivacyPublishView(WebsiteView):
    """POST: Entwurf der Datenschutzhinweise veröffentlichen (UI-Audit NAF-02)."""

    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        if not website.privacy_text.strip():
            raise serializers.ValidationError({"privacy_text": gettext("Der Entwurf ist leer.")})
        before = website.privacy_published_at
        website.privacy_published_text = website.privacy_text
        website.privacy_published_at = timezone.now()
        website.save(update_fields=["privacy_published_text", "privacy_published_at", "updated_at"])
        record(
            self.org,
            request.user,
            "update",
            website,
            {
                "Datenschutzhinweise veröffentlicht": [
                    str(before or ""),
                    str(website.privacy_published_at),
                ]
            },
        )
        return Response(self.payload(website))


class DomainSerializer(serializers.Serializer):
    hostname = serializers.CharField(max_length=253)
    is_primary = serializers.BooleanField(default=False)

    def validate_hostname(self, value: str) -> str:
        host = value.strip().lower().rstrip(".")
        host = re.sub(r"^https?://", "", host).split("/", 1)[0]
        if not re.match(HOSTNAME_RE, host):
            raise serializers.ValidationError(
                gettext("Bitte eine Domain wie „www.beispiel.de“ angeben.")
            )
        with rls_bypass():
            taken = WebsiteDomain.objects.filter(hostname=host).exists()
        if taken:
            raise serializers.ValidationError(gettext("Diese Domain ist schon vergeben."))
        return host


class DomainListView(_WebsiteMixin, APIView):
    """POST: Domain hinzufügen."""

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        ser = DomainSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        primary = ser.validated_data["is_primary"] or not website.domains.exists()
        if primary:
            website.domains.update(is_primary=False)
        try:
            with transaction.atomic():
                domain = WebsiteDomain.objects.create(
                    organization=self.org,
                    website=website,
                    hostname=ser.validated_data["hostname"],
                    is_primary=primary,
                )
        except IntegrityError as exc:
            raise ValidationError(
                {"hostname": [gettext("Diese Domain ist schon vergeben.")]}
            ) from exc
        record(self.org, request.user, "create", domain, diff({}, snapshot(domain)))
        return Response(domain_data(domain), status=status.HTTP_201_CREATED)


class DomainDetailView(_WebsiteMixin, APIView):
    """PUT: als Hauptadresse setzen · DELETE: Domain entfernen."""

    def domain(self, pk: int) -> WebsiteDomain:
        return get_object_or_404(WebsiteDomain, website=self.website(), pk=pk)

    @transaction.atomic
    def put(self, request, org_id: int, pk: int):
        domain = self.domain(pk)
        if not domain.is_primary:
            domain.website.domains.update(is_primary=False)
            domain.is_primary = True
            domain.save(update_fields=["is_primary"])
            record(self.org, request.user, "update", domain, {"Hauptadresse": [False, True]})
        return Response(domain_data(domain))

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        domain = self.domain(pk)
        website = domain.website
        record(self.org, request.user, "delete", domain, diff(snapshot(domain), {}))
        domain.delete()
        if domain.is_primary:
            first = website.domains.first()
            if first is not None:
                first.is_primary = True
                first.save(update_fields=["is_primary"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreviewLinkSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=100, required=False, allow_blank=True)
    days = serializers.IntegerField(min_value=1, max_value=PREVIEW_LINK_MAX_DAYS, default=7)


def preview_url(website: Website, token: str) -> str | None:
    base = site_url(website)
    if not base:
        return None
    url = f"{base}vorschau?schluessel={quote(token)}"
    if settings.WEBSITE_PUBLIC_URL:
        # Testserver: eine Adresse für alle Webseiten; der Link nennt, welche gemeint ist
        domain = website.domains.order_by("-is_primary", "pk").first()
        if domain:
            url += f"&seite={quote(domain.hostname)}"
    return url


class PreviewLinkListView(_WebsiteMixin, APIView):
    """POST: Vorschau-Link zum Weitergeben erzeugen (der Link erscheint nur einmal)."""

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        ser = PreviewLinkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        link, token = PreviewLink.create(
            website, ser.validated_data["days"], ser.validated_data.get("label", ""), request.user
        )
        record(
            self.org,
            request.user,
            "create",
            link,
            {
                "Vorschau-Link": [
                    None,
                    f"gültig bis {timezone.localtime(link.expires_at):%d.%m.%Y %H:%M}",
                ]
            },
        )
        return Response(
            {**link_data(link), "token": token, "url": preview_url(website, token)},
            status=status.HTTP_201_CREATED,
        )


class PreviewLinkDetailView(_WebsiteMixin, APIView):
    """DELETE: Vorschau-Link widerrufen."""

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        link = get_object_or_404(PreviewLink, website=self.website(), pk=pk)
        if link.revoked_at is None:
            link.revoked_at = timezone.now()
            link.save(update_fields=["revoked_at"])
            record(
                self.org, request.user, "update", link, {"Vorschau-Link": ["aktiv", "widerrufen"]}
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreviewOpenView(_WebsiteMixin, APIView):
    """POST: kurzlebigen Schlüssel für „Vorschau öffnen“ erzeugen.

    Auch mit dem Recht „Inhalte bearbeiten“, damit Redakteure ihre Texte prüfen können.
    """

    write_permission = None

    def post(self, request, org_id: int):
        website = self.website()
        token = services.open_token(website)
        return Response({"token": token, "url": preview_url(website, token)})


# --- Einwilligungen in der Mitgliederakte ---


class ConsentSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=PublicationConsent.Category.choices)
    active = serializers.BooleanField()
    source = serializers.ChoiceField(
        choices=[PublicationConsent.Source.BOARD, PublicationConsent.Source.PAPER],
        default=PublicationConsent.Source.BOARD,
    )
    on = serializers.DateField(required=False)

    def validate_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError(
                gettext("Das Datum darf nicht in der Zukunft liegen.")
            )
        return value


class MemberPublicationView(_ClubMixin, APIView):
    """GET: Einwilligungen/Widersprüche eines Mitglieds · PUT: eine Kategorie ändern."""

    write_permission = MEMBERS_EDIT

    def membership(self) -> Membership:
        return get_object_or_404(Membership, organization=self.org, pk=self.kwargs["pk"])

    def get(self, request, org_id: int, pk: int):
        return Response({"categories": services.status(self.membership())})

    @transaction.atomic
    def put(self, request, org_id: int, pk: int):
        membership = self.membership()
        ser = ConsentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        before, after = services.set_entry(
            membership,
            data["category"],
            data["active"],
            data["source"],
            request.user,
            data.get("on"),
        )
        if before != after:
            label = PublicationConsent.Category(data["category"]).label
            kind = (
                "Widerspruch"
                if data["category"] in PublicationConsent.OBJECTION_CATEGORIES
                else "Einwilligung"
            )
            record(
                self.org,
                request.user,
                "update",
                membership,
                {f"Webseite: {kind} {label}": [before, after]},
                person=membership.person,
            )
        return Response({"categories": services.status(membership)})


# --- zurückgehaltene Nachrichten aus dem Kontaktformular ---


def held_data(m) -> dict:
    return {
        "id": m.pk,
        "recipient_name": m.recipient_name,
        "sender_name": m.sender_name,
        "sender_email": m.sender_email,
        "subject": m.subject,
        "body": m.body,
        "reason": m.reason,
        "created_at": m.created_at,
    }


class HeldListView(_WebsiteMixin, APIView):
    """GET: zurückgehaltene Nachrichten (nur „Webseite verwalten“)."""

    read_permission = WEBSITE_MANAGE

    def get(self, request, org_id: int):
        from .contact_models import HeldMessage

        return Response([held_data(m) for m in HeldMessage.objects.filter(website=self.website())])


class HeldDetailView(_WebsiteMixin, APIView):
    """POST: freigeben und zustellen · DELETE: verwerfen."""

    read_permission = WEBSITE_MANAGE

    def message(self, pk: int):
        from .contact_models import HeldMessage

        return get_object_or_404(HeldMessage, website=self.website(), pk=pk)

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        from . import contact
        from .public import SiteView

        message = self.message(pk)
        target = SiteView(message.website).resolve_recipient(message.recipient)
        if target is None:
            raise ValidationError(gettext("Den Empfänger gibt es nicht mehr. Bitte verwerfen."))
        name, emails = target
        delivered = contact.deliver(
            message.website,
            name,
            emails,
            {
                "name": message.sender_name,
                "email": message.sender_email,
                "subject": message.subject,
                "message": message.body,
            },
        )
        if not delivered:
            # Nachricht bleibt in der Liste; die gescheiterte Mail steht im Postausgang
            # (kein raise: der Eintrag im Postausgang soll gespeichert bleiben)
            return Response(
                {
                    "detail": gettext(
                        "Die Nachricht konnte nicht zugestellt werden und bleibt in der "
                        "Liste. Bitte den Postausgang prüfen und später erneut freigeben."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        record(
            self.org,
            request.user,
            "delete",
            message,
            {"Nachricht von der Webseite": [f"zurückgehalten ({message.reason})", "zugestellt"]},
        )
        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        message = self.message(pk)
        record(
            self.org,
            request.user,
            "delete",
            message,
            {"Nachricht von der Webseite": [f"zurückgehalten ({message.reason})", "verworfen"]},
        )
        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
