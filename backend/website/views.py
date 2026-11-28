"""Verwaltung der Webseite in HUBIplan (Einrichtung, Zustand, Domains, Vorschau)
und Einwilligungen zur Veröffentlichung in der Mitgliederakte."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import get_language, gettext
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    CHRONICLE_EDIT,
    CHRONICLE_VIEW,
    MEMBERS_EDIT,
    ORG_EDIT,
    WEBCONTENT_VIEW,
    WEBSITE_CONTENT,
    WEBSITE_MANAGE,
    WEBSITE_VIEW,
)
from access.modules import module_on
from audit.log import diff, record, snapshot
from core.api_base import OrgScopedMixin
from members.models import Membership
from members.views import _ClubMixin
from organizations.models import Organization
from organizations.theme import effective_theme

from . import designs, home, menu, privacy, services, style, variants
from .drafts import content_only_draft, preview_url, publish_draft, text_versions, version_data
from .models import (
    BLOCK_HINTS,
    BLOCKS,
    DEFAULT_HOME_OFF,
    DESIGN_VERSIONS,
    DRAFT_FIELDS,
    HOME_HINTS,
    HOME_NEEDS_BLOCK,
    HOME_SECTIONS,
    DesignVersion,
    PreviewLink,
    PublicationConsent,
    Website,
    WebsiteDomain,
    blocks_without_module,
    home_without_module,
    normalize_home_sections,
)
from .options import (
    MENU_ITEM_FIELDS,
    can_import_designs,
    domain_data,
    header_image_id,
    held_data,
    home_choices,
    link_data,
    site_url,
)
from .serializers import (
    ConsentSerializer,
    DomainSerializer,
    PreviewLinkSerializer,
    WebsiteSerializer,
    clean_draft,
)


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
            # F7: Inhalte der Abschnitte bearbeiten auch ohne Verwaltungsrecht
            "can_edit_home_content": bool({WEBSITE_CONTENT, WEBSITE_MANAGE} & self.org_permissions),
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
            # Darstellung der festen Bereiche (G5)
            "layout_catalog": variants.catalog(),
            # Designpakete einspielen: wer die Webseite verwaltet, für die eigene Einheit
            # (#481); für die ganze Installation und zum Sperren nur Plattformverwalter
            "can_import_designs": WEBSITE_MANAGE in self.org_permissions,
            "designs_platform": can_import_designs(self.request.user),
            # Termine-Block: Häkchen „übergeordnete Einheiten“ nur, wenn es sie gibt
            "has_parent_units": services.has_parent_events(self.org),
            # Mit Einheit darüber (``parent``; leer: oberste Ebene), damit die Liste unter
            # Webseite › Untereinheiten je Ebene sortiert werden kann
            "units": [
                {
                    "id": u.pk,
                    "name": u.name,
                    "parent": None if u.parent_id == self.org.pk else u.parent_id,
                }
                for u in services.in_tree_order(services.units_below(self.org))
            ],
            # Reihenfolge dort ziehen: wie unter „Untereinheiten“ nur mit Recht
            # „Einheit bearbeiten“ und nicht auf der Webseite einer Untereinheit
            "can_sort_units": ORG_EDIT in self.org_permissions
            and not services.is_unit_site(self.org),
            "website": None,
        }
        if website is not None:
            theme = effective_theme(self.org.ancestors())
            palette = theme["palette"]
            data["palette"] = palette
            data["gradients"] = theme["gradients"]
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
                    key: designs.resolve(
                        key,
                        palette,
                        website.color_roles,
                        extra,
                        theme["gradients"],
                        theme["palette_roles"],
                    )
                    for key in [*designs.DESIGNS, *extra]
                },
                # F7: Entwurf ändert nur Inhalte der Abschnitte (dann auch mit „Inhalte bearbeiten“)
                "draft_content_only": content_only_draft(website),
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
                "text_versions": text_versions(website),
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
        old_narrow = header_image_id(website, "header_image_narrow")
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
        new_narrow = header_image_id(website, "header_image_narrow")
        if new_narrow != old_narrow:
            changes["Kopfbild für schmale Bildschirme"] = [old_narrow, new_narrow]
        if changes:
            record(self.org, request.user, "update", website, changes)
        return Response(self.payload(website))

    @transaction.atomic
    def delete(self, request, org_id: int):
        website = self.website()
        record(self.org, request.user, "delete", website, {"Webseite": ["eingerichtet", None]})
        website.delete()
        return Response(self.payload(None))


class DesignPublishView(WebsiteView):
    """POST: Entwurf der Gestaltung veröffentlichen; die Fassung kommt in den Verlauf."""

    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        publish_draft(website, request.user, self.org)
        return Response(self.payload(website))


class HomeContentView(WebsiteView):
    """PUT: Inhalte vorhandener Abschnitte der Startseite in den Entwurf (F7, Ralf 10.11.2026).

    Auch mit dem Recht „Inhalte bearbeiten“. Aufbau, Reihenfolge und Aussehen der Abschnitte
    bleiben der Webseitenverwaltung vorbehalten."""

    http_method_names = ["put", "options"]
    write_permission = (WEBSITE_CONTENT, WEBSITE_MANAGE)

    @transaction.atomic
    def put(self, request, org_id: int):
        website = self.website()
        given = request.data.get("home_sections") if isinstance(request.data, dict) else None
        draft = clean_draft(website, website.draft)
        current = draft.get("home_sections", normalize_home_sections(website.home_sections))
        try:
            value = home.validate(given, website, HOME_SECTIONS, DEFAULT_HOME_OFF)
        except home.Invalid as exc:
            raise ValidationError({"home_sections": [str(exc)]}) from exc
        if home.skeleton(value) != home.skeleton(current):
            raise ValidationError(
                {
                    "home_sections": [
                        gettext(
                            "Mit dem Recht „Inhalte bearbeiten“ änderst du nur den Inhalt "
                            "vorhandener Abschnitte."
                        )
                    ]
                }
            )
        website.draft = clean_draft(website, {**draft, "home_sections": value})
        website.save(update_fields=["draft", "updated_at"])
        record(
            self.org,
            request.user,
            "update",
            website,
            {"Entwurf: Inhalte der Startseite": [current, value]},
        )
        return Response(self.payload(website))


class HomeContentPublishView(WebsiteView):
    """POST: Entwurf veröffentlichen, wenn er nur Inhalte der Abschnitte ändert (F7)."""

    http_method_names = ["post", "options"]
    write_permission = (WEBSITE_CONTENT, WEBSITE_MANAGE)

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        if not content_only_draft(website):
            raise ValidationError(
                {
                    "draft": [
                        gettext(
                            "Der Entwurf ändert auch die Gestaltung. Veröffentlichen kann ihn "
                            "nur, wer die Webseite verwaltet."
                        )
                    ]
                }
            )
        publish_draft(website, request.user, self.org)
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
