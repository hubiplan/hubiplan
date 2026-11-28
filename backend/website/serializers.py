"""Eingaben der Webseiten-Einstellungen prüfen (Serializer), auch für den Entwurf."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext as _
from rest_framework import serializers

from core.api_base import ModelCleanMixin
from core.tenancy import rls_bypass

from . import designs, home, menu, services, style, variants
from .models import (
    BLOCK_NAME_MAX,
    BLOCKS,
    DEFAULT_HOME_OFF,
    DRAFT_FIELDS,
    HEADER_IMAGE_FIELDS,
    HOME_SECTIONS,
    HOSTNAME_RE,
    LINK_URL_MAX,
    MAX_HEADER_IMAGES,
    MAX_IMAGE_HOSTS,
    MENU_DRAFT_FIELDS,
    NAME_FORMAT_AREAS,
    PREVIEW_LINK_MAX_DAYS,
    PublicationConsent,
    Website,
    WebsiteDomain,
    WebsiteImage,
    header_ids,
    header_value,
    is_extra_block,
    is_heading_key,
    is_link_key,
    is_renamable,
    normalize_home_sections,
)
from .options import header_image_id, set_header_image

MAX_HEADINGS = 20


MAX_LINKS = 10


SETTINGS_FIELDS = [
    "state",
    "maintenance_text",
    "blocks",
    "menu",
    "block_names",
    "menu_links",
    "menu_button",
    "menu_places",
    "home_sections",
    "design",
    "color_roles",
    "style",
    "layouts",
    "name_format",
    "name_formats",
    "show_vacant",
    "show_instrument",
    "show_titles",
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
    "notice_text",
    "notice_target",
    "notice_from",
    "notice_until",
    "notice_style",
    "notice_place",
    "notice_icon",
    "notice_button",
    "notice_date",
    "image_hosts",
]


# W3: erlaubte Bildquellen nur als Rechnername, keine IP-Adresse
IP_LIKE = re.compile(r"^[0-9.]+$")


class WebsiteSerializer(ModelCleanMixin, serializers.ModelSerializer):
    # Kopfbild (Ralf 05.11.): Nummer eines Bildes der Bilderverwaltung oder null; seit #480
    # auch eine Liste mehrerer Bilder, von denen die Webseite bei jedem Aufruf eines zeigt
    header_image = serializers.JSONField(required=False, allow_null=True)
    # Kopfbild für schmale Bildschirme (Webseite #73), optional, ebenso eines oder mehrere
    header_image_narrow = serializers.JSONField(required=False, allow_null=True)
    # Ziel der Hinweisleiste (G6): null oder {} entfernt es
    notice_target = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = Website
        fields = [*SETTINGS_FIELDS, *HEADER_IMAGE_FIELDS]

    def validate_header_image(self, value):
        items = value if isinstance(value, list) else [value]
        if any(
            v is not None and (not isinstance(v, int) or isinstance(v, bool)) for v in items
        ) or (isinstance(value, list) and None in value):
            raise serializers.ValidationError(_("Unbekanntes Bild."))
        ids = header_ids(value)
        if len(ids) > MAX_HEADER_IMAGES:
            raise serializers.ValidationError(
                _("Höchstens {x0} Kopfbilder.").format(x0=MAX_HEADER_IMAGES)
            )
        if ids and (
            self.instance is None
            or WebsiteImage.objects.filter(website=self.instance, pk__in=ids).count() != len(ids)
        ):
            raise serializers.ValidationError(_("Unbekanntes Bild."))
        return header_value(ids)

    validate_header_image_narrow = validate_header_image

    def update(self, instance, validated_data):
        for key in HEADER_IMAGE_FIELDS:
            if key in validated_data:
                set_header_image(instance, validated_data.pop(key), key)
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

    def validate_notice_text(self, value):
        return " ".join((value or "").split())

    def validate_notice_button(self, value):
        return " ".join((value or "").split())

    def validate_notice_target(self, value):
        # Ziel wie bei Knöpfen der Startseite: Menüpunkt, Untereinheit, Termin oder Link nach außen
        if value in (None, {}) or self.instance is None:
            return {}
        try:
            target = home._target(value, home.references(self.instance))
        except home.Invalid as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if target is None:
            raise serializers.ValidationError(_("Dieses Ziel gibt es nicht."))
        return target

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

    def validate_menu_places(self, value):
        if self.instance is None:
            return {}
        names, links = self._pending_menu()
        try:
            return menu.validate_places(value, menu.items(self.instance, names=names, links=links))
        except ValueError as exc:
            raise serializers.ValidationError(
                _("Diesen Menüpunkt kann man nicht in den Fuß setzen.")
            ) from exc

    def validate_image_hosts(self, value):
        # Nur Rechnernamen (W3, docs/mcp.md): keine Adressen, keine Ports, keine IP-Adressen
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError(_("Bitte die Server als Liste angeben."))
        result = []
        for raw in value:
            host = raw.strip().lower().rstrip(".")
            if not host:
                continue
            if not re.match(HOSTNAME_RE, host) or IP_LIKE.match(host):
                raise serializers.ValidationError(
                    _("Bitte nur Rechnernamen angeben, z. B. cloud.example.org: {host}").format(
                        host=raw
                    )
                )
            if host not in result:
                result.append(host)
        if len(result) > MAX_IMAGE_HOSTS:
            raise serializers.ValidationError(_("Höchstens {n} Server.").format(n=MAX_IMAGE_HOSTS))
        return result

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

    def validate_name_formats(self, value):
        """Bereich → Namensform (Issue #709); leer oder null = Namensform der Webseite."""
        if not isinstance(value, dict):
            raise serializers.ValidationError(gettext("Namensform bitte je Bereich angeben."))
        result = {}
        for key, fmt in value.items():
            known = key in NAME_FORMAT_AREAS or (
                isinstance(key, str) and key.startswith("membertype:") and key[11:].isdigit()
            )
            if not known:
                raise serializers.ValidationError(
                    gettext("Unbekannter Bereich „{x0}“.").format(x0=key)
                )
            if fmt in (None, ""):
                continue
            if fmt not in Website.NameFormat.values:
                raise serializers.ValidationError(
                    gettext("Unbekannte Namensform „{x0}“.").format(x0=fmt)
                )
            result[key] = fmt
        return dict(sorted(result.items()))

    def validate_layouts(self, value):
        try:
            return variants.validate(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_color_roles(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(gettext("Farbzuordnung bitte je Design angeben."))
        return designs.normalize_color_roles(value, self._package_roles())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["home_sections"] = normalize_home_sections(instance.home_sections)
        data["layouts"] = variants.normalize(instance.layouts)
        data["menu"] = menu.normalize(instance.menu, menu.items(instance))
        data["color_roles"] = designs.normalize_color_roles(
            instance.color_roles, designs.package_roles(instance.packages())
        )
        data["design"] = instance.effective_design()
        data["header_image"] = header_image_id(instance)
        data["header_image_narrow"] = header_image_id(instance, "header_image_narrow")
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
        "header_image_narrow": header_image_id(website, "header_image_narrow"),
        "home_sections": normalize_home_sections(website.home_sections),
        "layouts": variants.normalize(website.layouts),
        "name_formats": website.name_formats if isinstance(website.name_formats, dict) else {},
        "menu": menu.normalize(website.menu, menu.items(website)),
        "block_names": website.block_names if isinstance(website.block_names, dict) else {},
        "menu_links": website.menu_links if isinstance(website.menu_links, dict) else {},
        "menu_button": website.menu_button or "",
        "menu_places": menu.places(website),
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
                data = {key: draft[key]}
                if key in MENU_DRAFT_FIELDS:
                    # Menü, Namen und Links hängen zusammen (neue Überschriften und Links)
                    data = {k: draft[k] for k in MENU_DRAFT_FIELDS if k in draft}
                one = WebsiteSerializer(website, data=data, partial=True)
                one.is_valid()
                if key not in one.errors and key in one.validated_data:
                    valid[key] = one.validated_data[key]
        values = valid
    else:
        values = dict(ser.validated_data)
    live = live_design(website)
    return {k: values[k] for k in DRAFT_FIELDS if k in values and values[k] != live[k]}


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


class PreviewLinkSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=100, required=False, allow_blank=True)
    days = serializers.IntegerField(min_value=1, max_value=PREVIEW_LINK_MAX_DAYS, default=7)


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
