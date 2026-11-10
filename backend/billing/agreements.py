"""Vereinbarungen mit Geschäftspartnern (Konzept geschaeftspartner.md, P4).

Sponsoring- und Rahmenvereinbarungen an der Partnerakte: Zeitraum, Betrag oder Sachleistung,
Gegenleistung und steuerliche Einordnung. Mit Enddatum legt HUBIplan eine Aufgabe an, die
rechtzeitig an die Verlängerung erinnert. Für Sponsoren gibt es einen Dankesbrief als PDF auf
dem Briefbogen des Vereins.
"""

from __future__ import annotations

import datetime
import io
from xml.sax.saxutils import escape

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, viewsets
from rest_framework.decorators import action

from audit.log import record
from core.api_base import AuditMixin

from .models import BusinessPartner, PartnerAgreement
from .partners import PartnerAccess

THANKS_MAX = 3000


class AgreementSerializer(serializers.ModelSerializer):
    benefits = serializers.ListField(
        child=serializers.ChoiceField(choices=PartnerAgreement.Benefit.choices),
        required=False,
        max_length=len(PartnerAgreement.Benefit.choices),
    )
    reminder_due = serializers.SerializerMethodField()

    class Meta:
        model = PartnerAgreement
        fields = [
            "id",
            "kind",
            "title",
            "start",
            "end",
            "amount",
            "in_kind",
            "benefits",
            "benefits_text",
            "tax_kind",
            "category",
            "remind_days",
            "reminder",
            "reminder_due",
            "thanked_at",
            "notes",
            "updated_at",
        ]
        read_only_fields = ["id", "reminder", "reminder_due", "thanked_at", "updated_at"]

    def get_reminder_due(self, obj):
        todo = obj.reminder
        if not todo or todo.deleted_at or todo.status != "open":
            return None
        return todo.due_date.isoformat() if todo.due_date else None

    def validate_benefits(self, value):
        return sorted(set(value))

    def validate_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(gettext("Der Betrag darf nicht negativ sein."))
        return value

    def validate_remind_days(self, value):
        if value > 365:
            raise serializers.ValidationError(gettext("Höchstens 365 Tage vorher."))
        return value

    def validate_category(self, category):
        org = self.context["view"].org
        if category and category.organization_id != org.pk:
            raise serializers.ValidationError(gettext("Unbekannte Kategorie."))
        return category

    def validate(self, attrs):
        start = attrs.get("start", getattr(self.instance, "start", None))
        end = attrs.get("end", getattr(self.instance, "end", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end": gettext("Das Ende liegt vor dem Beginn.")})
        return attrs


def reminder_date(agreement: PartnerAgreement) -> datetime.date | None:
    if not agreement.end:
        return None
    return agreement.end - datetime.timedelta(days=agreement.remind_days)


def sync_reminder(agreement: PartnerAgreement, user) -> None:
    """Aufgabe „Vereinbarung verlängern?“ anlegen, verschieben oder entfernen.

    Nur offene Aufgaben werden geändert; eine erledigte bleibt, wie sie ist. Ohne Modul
    Aufgaben gibt es keine Erinnerung."""
    from todos.models import Todo

    due = reminder_date(agreement)
    todo = agreement.reminder
    if todo and (todo.status != "open" or todo.deleted_at):
        # erledigt oder gelöscht: erst ein neues Enddatum braucht eine neue Erinnerung
        if due is None or todo.due_date == due:
            return
        todo = None
    enabled = "todos" in (agreement.organization.enabled_modules or [])
    if due is None or not enabled:
        if todo:
            todo.deleted_at = timezone.now()
            todo.save(update_fields=["deleted_at", "updated_at"])
        return
    title = gettext("Vereinbarung mit {name} verlängern?").format(name=agreement.partner.name)[:200]
    description = gettext("„{title}“ endet am {end}.").format(
        title=agreement.title, end=f"{agreement.end:%d.%m.%Y}"
    )
    if todo:
        if todo.due_date != due or todo.title != title:
            todo.due_date = due
            todo.title = title
            todo.description = description
            todo.save()
        return
    todo = Todo.objects.create(
        organization=agreement.organization,
        title=title,
        description=description,
        due_date=due,
        created_by=user,
        owner=user,
    )
    agreement.reminder = todo
    agreement.save(update_fields=["reminder", "updated_at"])


class AgreementViewSet(PartnerAccess, AuditMixin, viewsets.ModelViewSet):
    """Vereinbarungen eines Geschäftspartners: ``partners/{partner_pk}/agreements/``."""

    serializer_class = AgreementSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None

    def partner(self):
        return get_object_or_404(
            BusinessPartner, organization=self.org, pk=self.kwargs["partner_pk"]
        )

    def get_queryset(self):
        return PartnerAgreement.objects.filter(
            organization=self.org, partner=self.partner()
        ).select_related("reminder", "partner")

    def get_create_kwargs(self):
        return {"organization": self.org, "partner": self.partner()}

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            sync_reminder(serializer.instance, self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            super().perform_update(serializer)
            serializer.instance.refresh_from_db()
            sync_reminder(serializer.instance, self.request.user)

    def perform_destroy(self, instance):
        with transaction.atomic():
            todo = instance.reminder
            if todo and todo.status == "open" and not todo.deleted_at:
                todo.deleted_at = timezone.now()
                todo.save(update_fields=["deleted_at", "updated_at"])
            super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def thanks(self, request, org_id, partner_pk, pk):
        """Dankesbrief als PDF; ``{text?}`` ersetzt den Vorschlag."""
        agreement = self.get_object()
        text = serializers.CharField(
            max_length=THANKS_MAX, required=False, allow_blank=True
        ).run_validation(request.data.get("text", ""))
        content = thanks_pdf(self.org, agreement, text or default_thanks(self.org, agreement))
        agreement.thanked_at = timezone.localdate()
        agreement.save(update_fields=["thanked_at", "updated_at"])
        record(
            self.org,
            request.user,
            "update",
            agreement,
            {"Dankesbrief": [None, f"{agreement.thanked_at:%d.%m.%Y}"]},
        )
        response = HttpResponse(content, content_type="application/pdf")
        name = f"Dankesbrief-{agreement.partner.number or agreement.partner.pk}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


def default_thanks(org, agreement: PartnerAgreement) -> str:
    """Vorschlag für den Dankesbrief; der Verein kann ihn vor dem Erzeugen ändern."""
    support = (
        gettext("Ihre Unterstützung von {amount}").format(amount=_euro(agreement.amount))
        if agreement.amount
        else gettext("Ihre Unterstützung")
    )
    if agreement.in_kind:
        support += " " + gettext("und {in_kind}").format(in_kind=agreement.in_kind)
    return "\n\n".join(
        [
            gettext("vielen Dank für {support}.").format(support=support),
            gettext(
                "Damit helfen Sie uns sehr, unser Vereinsleben zu gestalten. "
                "Wir freuen uns auf die weitere Zusammenarbeit."
            ),
        ]
    )


def _euro(value) -> str:
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} €"


def recipient_lines(partner: BusinessPartner) -> list[str]:
    details = partner.details or {}
    contact = partner.contacts.filter(receives_mail=True).first()
    lines = [partner.name]
    if contact:
        lines.append(" ".join(p for p in (contact.first_name, contact.last_name) if p))
    lines.append(details.get("street", ""))
    lines.append(" ".join(p for p in (details.get("postcode", ""), details.get("city", "")) if p))
    if (details.get("country") or "DE") != "DE":
        lines.append(details.get("country", ""))
    return [line for line in lines if line]


def greeting(partner: BusinessPartner) -> str:
    contact = partner.contacts.filter(receives_mail=True).first()
    if contact and contact.last_name:
        name = " ".join(p for p in (contact.first_name, contact.last_name) if p)
        return gettext("Guten Tag {name},").format(name=name)
    return gettext("Sehr geehrte Damen und Herren,")


def thanks_pdf(org, agreement: PartnerAgreement, text: str) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    from letterhead.data import letter_data
    from letterhead.pdf import LetterDocument, text_styles

    data = letter_data(org)
    st = text_styles(data)
    info = [(gettext("Datum"), f"{timezone.localdate():%d.%m.%Y}")]
    story: list = LetterDocument.start(data, recipient_lines(agreement.partner), info, True)
    story.append(Paragraph(escape(gettext("Herzlichen Dank")), st["title"]))
    story.append(Paragraph(escape(greeting(agreement.partner)), st["body"]))
    for part in text.split("\n\n"):
        if part.strip():
            story.append(Paragraph(escape(part.strip()).replace("\n", "<br/>"), st["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"{escape(gettext('Mit freundlichen Grüßen'))}<br/>{escape(data.name)}", st["body"]
        )
    )
    buf = io.BytesIO()
    LetterDocument(buf, [data], title=gettext("Dankesbrief"), author=org.name).build(story)
    return buf.getvalue()


def partner_logos(org) -> list[dict]:
    """Partner mit Einwilligung für den Webseiten-Abschnitt „Partner und Sponsoren“."""
    rows = BusinessPartner.objects.filter(
        organization=org, is_active=True, website_consent=True
    ).order_by("name")
    return [
        {"id": p.pk, "name": p.name, "url": p.website_url or (p.details or {}).get("website", "")}
        for p in rows
    ]
