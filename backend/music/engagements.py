"""Immutable commercial snapshots with explicit offer/acceptance/confirmation steps."""

import hashlib
import io
from decimal import Decimal
from xml.sax.saxutils import escape

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from audit.log import record
from changes import idempotency
from core.i18n import language_of
from finance.services import lock_bank_sources
from letterhead.data import letter_data
from letterhead.pdf import LetterDocument, text_styles

from .guest import NoStore
from .models import EngagementDocument, PerformanceAccount
from .settlement import SettlementView


class OfferInput(serializers.Serializer):
    valid_until = serializers.DateField()
    terms = serializers.CharField(max_length=8000)


def current(performance):
    account = get_object_or_404(PerformanceAccount, performance=performance)
    customer = performance.customer
    if not customer or not customer.is_active:
        raise serializers.ValidationError(gettext("Bitte einen aktiven Auftraggeber wählen."))
    buyer = customer.details
    if not all(buyer.get(field) for field in ["name", "street", "postcode", "city", "country"]):
        raise serializers.ValidationError(
            gettext("Bitte die Rechnungsanschrift des Auftraggebers vervollständigen.")
        )
    return {
        "customer": customer.pk,
        "buyer": buyer,
        "title": performance.event.title,
        "starts_at": performance.event.starts_at.isoformat(),
        "ends_at": performance.event.ends_at.isoformat(),
        "location": performance.event.location,
        "meeting_at": performance.meeting_at.isoformat() if performance.meeting_at else "",
        "meeting_place": performance.meeting_place,
        "uniform": performance.uniform,
        "formation": performance.formation,
        "notes": performance.notes,
        "fee": str(account.fee),
        "travel": str(account.travel),
        "extras": str(account.extras),
        "note": account.note,
        "total": str(account.fee + account.travel + account.extras),
    }


def label(document):
    return (
        f"{'A' if document.kind == 'offer' else 'B'}-{document.created_at.year}-{document.pk:06d}"
    )


def pdf(document, letter):
    s = document.snapshot
    buf = io.BytesIO()
    doc = LetterDocument(buf, [letter])
    styles = text_styles(letter)
    buyer = s["buyer"]
    address = [
        buyer["name"],
        buyer["street"],
        f"{buyer['postcode']} {buyer['city']}",
        buyer["country"],
    ]
    story = LetterDocument.start(
        letter,
        address,
        [
            (gettext("Dokumentnummer"), label(document)),
            (gettext("Datum"), document.created_at.strftime("%d.%m.%Y")),
        ],
        True,
    )

    def paragraph(text, style="body"):
        story.append(Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style]))

    paragraph(
        gettext("Angebot") if document.kind == "offer" else gettext("Auftragsbestätigung"), "title"
    )
    paragraph(s["title"], "title")

    def dt(raw):
        return timezone.localtime(timezone.datetime.fromisoformat(raw)).strftime("%d.%m.%Y %H:%M")

    paragraph(f"{dt(s['starts_at'])} - {dt(s['ends_at'])}")
    paragraph(f"{gettext('Ort')}: {s['location']}")
    if s["meeting_at"] or s["meeting_place"]:
        paragraph(
            f"{gettext('Treffpunkt')}: "
            f"{dt(s['meeting_at']) if s['meeting_at'] else ''} {s['meeting_place']}"
        )
    for title, field in [
        (gettext("Uniform"), "uniform"),
        (gettext("Weitere Informationen"), "notes"),
    ]:
        if s[field]:
            paragraph(f"{title}: {s[field]}")
    story.append(Spacer(1, 3 * mm))
    for title, field in [
        (gettext("Honorar"), "fee"),
        (gettext("Fahrtkosten"), "travel"),
        (gettext("Weitere Leistungen"), "extras"),
        (gettext("Gesamtbetrag brutto"), "total"),
    ]:
        paragraph(f"{title}: {Decimal(s[field]):.2f} EUR", "title" if field == "total" else "body")
    if s["note"]:
        paragraph(s["note"])
    paragraph(gettext("Vereinbarungen"), "title")
    paragraph(s["terms"])
    if document.valid_until:
        paragraph(f"{gettext('Angebot gültig bis')}: {document.valid_until:%d.%m.%Y}")
    if document.offer_id:
        paragraph(f"{gettext('Bestätigtes Angebot')}: {s['offer_number']}")
    paragraph(gettext("Dieses Dokument ist keine Rechnung."), "small")
    doc.build(story)
    return buf.getvalue()


def data(document):
    return {
        "id": document.pk,
        "number": label(document),
        "kind": document.kind,
        "status": document.status,
        "valid_until": document.valid_until,
        "accepted_at": document.accepted_at,
        "acceptance_note": document.acceptance_note,
        "resolution_note": document.resolution_note,
        "source_status": document.offer.status if document.offer_id else document.status,
        "created_at": document.created_at,
        "snapshot": document.snapshot,
        "sha256": document.sha256,
    }


class EngagementView(NoStore, SettlementView):
    def get(self, request, org_id, pk):
        performance = self.account(pk)
        documents = performance.engagement_documents.select_related("offer").order_by("-pk")
        if "document" in request.query_params:
            document = get_object_or_404(
                documents,
                pk=serializers.IntegerField(min_value=1).run_validation(
                    request.query_params["document"]
                ),
            )
            if not document.file:
                from rest_framework.exceptions import NotFound

                raise NotFound()
            content = document.file.read()
            if hashlib.sha256(content).hexdigest() != document.sha256:
                raise serializers.ValidationError(
                    gettext("Das archivierte Dokument konnte nicht geprüft werden.")
                )
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{label(document)}.pdf"'
            return response
        return Response({"documents": [data(document) for document in documents]})

    @transaction.atomic
    def post(self, request, org_id, pk):
        if "music.edit" not in self.org_permissions:
            raise PermissionDenied()
        lock_bank_sources(self.org)
        performance = self.account(pk)
        key = idempotency.claim(request, f"music.engagement.{self.org.pk}.{pk}", required=True)
        if key.done:
            return Response(
                data(
                    get_object_or_404(
                        EngagementDocument, performance=performance, pk=key.result["document"]
                    )
                )
            )
        action = serializers.ChoiceField(
            choices=["offer", "accept", "reject", "cancel", "confirm"]
        ).run_validation(request.data.get("action"))
        if action == "offer":
            if performance.event.is_cancelled or performance.event.ends_at <= timezone.now():
                raise serializers.ValidationError(
                    gettext("Bitte einen zukünftigen, nicht abgesagten Auftritt wählen.")
                )
            if performance.engagement_documents.filter(kind="offer", status="accepted").exists():
                raise serializers.ValidationError(
                    gettext("Bitte zuerst die bestehende Zusage aufheben.")
                )
            form = OfferInput(data=request.data)
            form.is_valid(raise_exception=True)
            if form.validated_data["valid_until"] < timezone.localdate():
                raise serializers.ValidationError(
                    gettext("Die Angebotsfrist liegt in der Vergangenheit.")
                )
            values = current(performance)
            values["terms"] = form.validated_data["terms"]
            performance.engagement_documents.filter(kind="offer", status="issued").update(
                status="superseded"
            )
            document = EngagementDocument.objects.create(
                organization=self.org,
                performance=performance,
                kind="offer",
                snapshot=values,
                valid_until=form.validated_data["valid_until"],
                created_by=request.user,
            )
            self.archive(document)
        else:
            document = get_object_or_404(
                EngagementDocument,
                performance=performance,
                organization=self.org,
                kind="offer",
                pk=serializers.IntegerField(min_value=1).run_validation(
                    request.data.get("document")
                ),
            )
            if action == "confirm":
                if document.status != "accepted":
                    raise serializers.ValidationError(
                        gettext("Bitte das Angebot zuerst als angenommen erfassen.")
                    )
                existing = document.confirmations.first()
                if existing:
                    key.remember({"document": existing.pk})
                    return Response(data(existing))
                values = {**document.snapshot, "offer_number": label(document)}
                document = EngagementDocument.objects.create(
                    organization=self.org,
                    performance=performance,
                    offer=document,
                    kind="confirmation",
                    snapshot=values,
                    created_by=request.user,
                )
                self.archive(document)
            else:
                note = serializers.CharField(max_length=1000).run_validation(
                    request.data.get("acceptance_note")
                )
                if action == "accept":
                    if (
                        document.status != "issued"
                        or document.valid_until < timezone.localdate()
                        or performance.event.is_cancelled
                    ):
                        raise serializers.ValidationError(
                            gettext("Dieses Angebot kann nicht mehr angenommen werden.")
                        )
                    if any(document.snapshot.get(k) != v for k, v in current(performance).items()):
                        raise serializers.ValidationError(
                            gettext(
                                "Die Auftrittsdaten haben sich geändert. "
                                "Bitte ein neues Angebot ausgeben."
                            )
                        )
                    document.status = "accepted"
                    document.accepted_at = timezone.now()
                    document.acceptance_note = note
                else:
                    if document.status not in ["issued", "accepted"] or (
                        action == "reject" and document.status == "accepted"
                    ):
                        raise serializers.ValidationError(
                            gettext("Dieser Statuswechsel ist nicht möglich.")
                        )
                    document.status = "rejected" if action == "reject" else "cancelled"
                    document.resolution_note = note
                document.save(
                    update_fields=["status", "accepted_at", "acceptance_note", "resolution_note"]
                )
        key.remember({"document": document.pk})
        record(
            self.org,
            request.user,
            "update",
            document,
            {"Auftrittsdokument": [None, {"id": document.pk, "action": action}]},
        )
        return Response(data(document))

    def archive(self, document):
        with language_of(self.org):
            content = pdf(document, letter_data(self.org))
        document.sha256 = hashlib.sha256(content).hexdigest()
        document.file.save(f"{label(document)}.pdf", ContentFile(content), save=False)
        document.save(update_fields=["file", "sha256"])
