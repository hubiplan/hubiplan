"""Sammelüberweisung freigegebener Auslagen (A3): eine pain.001-Datei fürs Onlinebanking.

Die Datei entsteht mit demselben Baustein wie bei den Musikern (``music.payouts.xml``, ISO-
Schema und DK-Regeln). Beim ersten Herunterladen bucht HUBIplan jede Auslage als Ausgabe am
Ausführungstag; vorher lässt sich der Lauf aufheben. Danach korrigiert nur ein Storno der
Buchung (die Auslage ist dann wieder freigegeben).
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from changes import idempotency

from . import services
from .data import drf_errors, masked
from .models import ExpenseClaim, TransferItem, TransferRun
from .views import ExpenseMixin

S = ExpenseClaim.Status


def run_data(run: TransferRun) -> dict:
    items = list(run.items.select_related("claim__membership__person").order_by("pk"))
    return {
        "id": run.pk,
        "reference": str(run.reference),
        "bank_account": run.bank_account_id,
        "execution_date": run.execution_date,
        "cancelled": bool(run.cancelled_at),
        "exported": bool(run.exported_at),
        "created_at": run.created_at,
        "total": str(sum((i.amount for i in items), Decimal(0))),
        "items": [
            {
                "claim": i.claim_id,
                "number": i.claim.number,
                "name": services.person_name(i.claim),
                "amount": str(i.amount),
                "holder": i.payee.get("holder", ""),
                "iban": masked(i.payee.get("iban", "")),
                "paid": i.claim.status == S.PAID,
            }
            for i in items
        ],
    }


def remittance(item, reference: str) -> str:
    return f"Auslage {item.claim.number} {item.claim.purpose}"[:140]


class TransferRunsView(ExpenseMixin, APIView):
    """GET: Läufe und auszahlbare Auslagen · POST: neuen Lauf anlegen."""

    def check_pay(self):
        if not self.can_pay:
            raise PermissionDenied(gettext("Zum Auszahlen fehlt das Recht, die Kasse zu führen."))

    def get(self, request, org_id: int):
        from finance.models import Account

        busy = set(
            TransferItem.objects.filter(organization=self.org, released=False).values_list(
                "claim_id", flat=True
            )
        )
        ready = []
        for claim in (
            ExpenseClaim.objects.filter(
                organization=self.org, status=S.APPROVED, payout=ExpenseClaim.Payout.BANK
            )
            .select_related("membership__person", "advance")
            .prefetch_related("lines")
            .order_by("approved_at", "pk")
        ):
            if claim.pk in busy or claim.amount_due <= 0 or not claim.payee.get("iban"):
                continue
            ready.append(
                {
                    "id": claim.pk,
                    "number": claim.number,
                    "name": services.person_name(claim),
                    "purpose": claim.purpose,
                    "amount": str(claim.amount_due),
                    "holder": claim.payee.get("holder", ""),
                    "iban": masked(claim.payee.get("iban", "")),
                    "categories_ok": all(line.category_id for line in claim.lines.all()),
                }
            )
        return Response(
            {
                "runs": [
                    run_data(r) for r in TransferRun.objects.filter(organization=self.org)[:50]
                ],
                "ready": ready,
                "banks": [
                    {"id": a.pk, "name": a.name}
                    for a in Account.objects.filter(
                        organization=self.org, kind="bank", is_active=True
                    ).exclude(iban="")
                ],
                "can_pay": self.can_pay,
            }
        )

    @transaction.atomic
    def post(self, request, org_id: int):
        from finance.models import Account
        from finance.services import lock_bank_sources
        from music.payouts import Payee

        self.check_pay()
        lock_bank_sources(self.org)
        key = idempotency.claim(request, f"expenses.transfer.{self.org.pk}", required=True)
        if key.done:
            run = get_object_or_404(TransferRun, organization=self.org, pk=key.result["run"])
            return Response(run_data(run))
        try:
            day = datetime.date.fromisoformat(str(request.data.get("execution_date")))
        except ValueError as exc:
            raise serializers.ValidationError(
                {"execution_date": gettext("Bitte einen Ausführungstag angeben.")}
            ) from exc
        today = timezone.localdate()
        if not today <= day <= today + datetime.timedelta(days=365):
            raise serializers.ValidationError(
                gettext("Bitte einen zukünftigen Ausführungstag innerhalb eines Jahres wählen.")
            )
        bank = get_object_or_404(
            Account,
            organization=self.org,
            pk=request.data.get("bank_account"),
            kind="bank",
            is_active=True,
        )
        debtor = Payee(data={"holder": self.org.name, "iban": bank.iban, "bic": bank.bic})
        debtor.is_valid(raise_exception=True)
        ids = [int(i) for i in request.data.get("claims") or [] if str(i).isdigit()]
        if not ids or len(set(ids)) != len(ids) or len(ids) > 500:
            raise serializers.ValidationError(gettext("Bitte Auslagen auswählen."))
        claims = list(
            ExpenseClaim.objects.select_for_update()
            .filter(organization=self.org, pk__in=ids)
            .order_by("pk")
        )
        if len(claims) != len(ids):
            raise serializers.ValidationError(gettext("Unbekannte Auslage."))
        run = TransferRun.objects.create(
            organization=self.org,
            reference=uuid.uuid4(),
            bank_account=bank,
            execution_date=day,
            debtor=debtor.validated_data,
            created_by=request.user,
        )
        for claim in claims:
            payee = Payee(data=claim.payee or {})
            if (
                claim.status != S.APPROVED
                or claim.payout != ExpenseClaim.Payout.BANK
                or claim.amount_due <= 0
                or claim.transfers.filter(released=False).exists()
                or not payee.is_valid()
            ):
                raise serializers.ValidationError(
                    gettext(
                        "{number} ist nicht freigegeben, ohne Bankverbindung oder schon in "
                        "einer Sammelüberweisung."
                    ).format(number=claim.number)
                )
            if not all(line.category_id for line in claim.lines.all()):
                raise serializers.ValidationError(
                    gettext(
                        "{number}: Bitte zuerst für jede Position eine Kategorie wählen."
                    ).format(number=claim.number)
                )
            TransferItem.objects.create(
                organization=self.org,
                run=run,
                claim=claim,
                amount=claim.amount_due,
                payee=payee.validated_data,
            )
        from music.payouts import xml

        xml(run, remittance)  # Ungültige Datei bricht hier ab, bevor jemand sie bekommt
        key.remember({"run": run.pk})
        record(
            self.org, request.user, "create", run, {"Sammelüberweisung": [None, str(run.reference)]}
        )
        return Response(run_data(run), status=status.HTTP_201_CREATED)


class TransferActionView(ExpenseMixin, APIView):
    """POST {action: export|cancel}: Datei herunterladen (bucht beim ersten Mal) oder aufheben."""

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        from finance.services import lock_bank_sources
        from music.payouts import xml

        if not self.can_pay:
            raise PermissionDenied()
        lock_bank_sources(self.org)
        run = get_object_or_404(
            TransferRun.objects.select_for_update(), organization=self.org, pk=pk
        )
        action = request.data.get("action")
        if action == "cancel":
            if run.exported_at:
                raise serializers.ValidationError(
                    gettext(
                        "Die Datei wurde schon heruntergeladen und gebucht. Bitte einzelne "
                        "Buchungen stornieren."
                    )
                )
            if not run.cancelled_at:
                run.cancelled_at = timezone.now()
                run.save(update_fields=["cancelled_at"])
                run.items.update(released=True)
                record(
                    self.org,
                    request.user,
                    "update",
                    run,
                    {"Sammelüberweisung aufgehoben": [False, True]},
                )
            return Response(run_data(run))
        if action != "export" or run.cancelled_at:
            raise serializers.ValidationError(gettext("Dieser Lauf lässt sich nicht exportieren."))
        if not run.exported_at:
            with drf_errors():
                for item in run.items.select_related("claim").order_by("pk"):
                    claim = item.claim
                    if claim.status != S.APPROVED or claim.amount_due != item.amount:
                        raise serializers.ValidationError(
                            gettext(
                                "{number} hat sich geändert. Bitte den Lauf aufheben und neu "
                                "anlegen."
                            ).format(number=claim.number)
                        )
                    services.pay(
                        claim,
                        request.user,
                        account=run.bank_account,
                        date=run.execution_date,
                        transfer=run,
                    )
            # Bezahlt: Ein späteres Storno macht die Auslage wieder frei für einen neuen Lauf
            run.items.update(released=True)
            run.exported_at = timezone.now()
            run.save(update_fields=["exported_at"])
            record(
                self.org, request.user, "update", run, {"Bankexport": [None, str(run.reference)]}
            )
        content = xml(run, remittance)
        response = HttpResponse(content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="auslagen-{run.reference}.xml"'
        response["Cache-Control"] = "no-store"
        return response
