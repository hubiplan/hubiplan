"""Reviewable, immutable SEPA runs; export never creates a financial booking."""

import datetime
import re
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from lxml import etree
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from audit.log import record
from billing.sepa import clean_iban, sepa_text
from changes import idempotency
from finance.models import Account, iban_valid
from finance.services import lock_bank_sources

from .guest import NoStore
from .models import MusicianClaim, PayoutItem, PayoutRun
from .settlement import SettlementView, paid_amount, total
from .views import PerformanceViewSet

NS = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"


class Payee(serializers.Serializer):
    holder = serializers.CharField(max_length=70)
    iban = serializers.CharField(max_length=50)
    bic = serializers.RegexField(
        r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$", required=False, allow_blank=True, default=""
    )

    def validate_iban(self, value):
        value = clean_iban(value)
        if not iban_valid(value) or not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]+", value):
            raise serializers.ValidationError(gettext("Die IBAN ist ungültig."))
        return value

    def validate_holder(self, value):
        if not sepa_text(value, 70):
            raise serializers.ValidationError(
                gettext("Bitte einen Kontoinhaber im SEPA-Zeichensatz angeben.")
            )
        return value


class ItemInput(Payee):
    claim = serializers.IntegerField(min_value=1)


class RunInput(serializers.Serializer):
    bank_account = serializers.IntegerField(min_value=1)
    execution_date = serializers.DateField()
    items = ItemInput(many=True, allow_empty=False, max_length=500)


def run_visible(view, run):
    return all(
        PerformanceViewSet.visible(view, item.claim.assignment.performance)
        for item in run.items.select_related("claim__assignment__performance__event")
    )


def data(run):
    items = list(
        run.items.select_related("expense__booking", "claim__assignment__performance__event")
    )

    def settled(item):
        return item.expense_id and not hasattr(item.expense.booking, "cancellation")

    return {
        "id": run.pk,
        "reference": str(run.reference),
        "bank_account": run.bank_account_id,
        "execution_date": run.execution_date,
        "cancelled": bool(run.cancelled_at),
        "exported": bool(run.exported_at),
        "completed": all(settled(item) for item in items),
        "total": str(sum((item.amount for item in items), Decimal(0))),
        "items": [
            {
                "claim": item.claim_id,
                "performance": item.claim.assignment.performance_id,
                "title": item.claim.assignment.performance.event.title,
                "amount": str(item.amount),
                "holder": item.payee["holder"],
                "iban": item.payee["iban"],
                "bic": item.payee["bic"],
                "settled": bool(settled(item)),
            }
            for item in items
        ],
    }


def xml(run):
    root = etree.Element(f"{{{NS}}}Document", nsmap={None: NS})

    def add(parent, name, text=None, **attrs):
        elem = etree.SubElement(parent, f"{{{NS}}}{name}", **attrs)
        if text is not None:
            elem.text = str(text)
        return elem

    items = list(run.items.order_by("pk"))
    reference = run.reference.hex
    init = add(root, "CstmrCdtTrfInitn")
    header = add(init, "GrpHdr")
    add(header, "MsgId", reference)
    add(header, "CreDtTm", run.created_at.isoformat())
    add(header, "NbOfTxs", len(items))
    add(header, "CtrlSum", f"{sum(item.amount for item in items):.2f}")
    add(add(header, "InitgPty"), "Nm", sepa_text(run.debtor["holder"], 70))
    payment = add(init, "PmtInf")
    add(payment, "PmtInfId", reference)
    add(payment, "PmtMtd", "TRF")
    add(payment, "BtchBookg", "false")
    add(payment, "NbOfTxs", len(items))
    add(payment, "CtrlSum", f"{sum(item.amount for item in items):.2f}")
    add(add(add(payment, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
    add(add(payment, "ReqdExctnDt"), "Dt", run.execution_date.isoformat())
    add(add(payment, "Dbtr"), "Nm", sepa_text(run.debtor["holder"], 70))
    add(add(add(payment, "DbtrAcct"), "Id"), "IBAN", run.debtor["iban"])
    agent = add(add(payment, "DbtrAgt"), "FinInstnId")
    if run.debtor["bic"]:
        add(agent, "BICFI", run.debtor["bic"])
    else:
        add(add(agent, "Othr"), "Id", "NOTPROVIDED")
    add(payment, "ChrgBr", "SLEV")
    for item in items:
        tx = add(payment, "CdtTrfTxInf")
        add(add(tx, "PmtId"), "EndToEndId", f"{reference[:20]}-{item.pk}")
        add(add(tx, "Amt"), "InstdAmt", f"{item.amount:.2f}", Ccy="EUR")
        if item.payee["bic"]:
            add(add(add(tx, "CdtrAgt"), "FinInstnId"), "BICFI", item.payee["bic"])
        add(add(tx, "Cdtr"), "Nm", sepa_text(item.payee["holder"], 70))
        add(add(add(tx, "CdtrAcct"), "Id"), "IBAN", item.payee["iban"])
        add(add(tx, "RmtInf"), "Ustrd", f"Musikverguetung {item.claim_id} / {reference[:12]}")
    validate(root)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# Unverändertes ISO-20022-Originalschema (schemas/README.md). Die strengeren Regeln der
# Deutschen Kreditwirtschaft (GBIC 5) prüft dk_rules selbst; deren Schemadatei liegt nicht
# mehr im Repo, weil eine Erlaubnis zur Weitergabe fehlt (Lizenzaudit 10.11.2026, L04).
SCHEMA = Path(__file__).parent / "schemas" / "pain.001.001.09.xsd"
_SEPA_TEXT = re.compile(r"[A-Za-z0-9/?:().,'+\- ]*")
_AMOUNT = re.compile(r"(0|[1-9][0-9]{0,8})\.[0-9]{2}")
# Element → höchste Länge nach DK-Anlage 3 (GBIC 5) für Überweisungen
_DK_LENGTH = {"MsgId": 35, "PmtInfId": 35, "EndToEndId": 35, "Nm": 70, "Ustrd": 140}


def dk_rules(root) -> list[str]:
    """Regeln aus dem DK-Datenformat (GBIC 5), die über das ISO-Schema hinausgehen:
    SEPA-Zeichensatz und Längen der Texte, nur Euro mit zwei Nachkommastellen, Betrag bis
    999.999.999,99, Service-Level SEPA, Entgelt SLEV, Anzahl und Kontrollsumme stimmig.
    Gibt die Verstöße als technische Angaben fürs Protokoll zurück (leer: in Ordnung); sie
    erscheinen nie in der Oberfläche, ein Verstoß bricht den Zahlungslauf mit Serverfehler ab,
    weil HUBIplan die Datei selbst erzeugt."""

    def local(elem):
        return etree.QName(elem).localname

    faults = []
    for elem in root.iter():
        name, text = local(elem), elem.text or ""
        if name in _DK_LENGTH:
            if not text or len(text) > _DK_LENGTH[name] or not _SEPA_TEXT.fullmatch(text):
                faults.append(f"{name}: Länge oder Zeichensatz")
            if name in ("MsgId", "PmtInfId", "EndToEndId") and (
                text.startswith("/") or "//" in text
            ):
                faults.append(f"{name}: Schrägstrich")
        if name == "InstdAmt":
            if elem.get("Ccy") != "EUR" or not _AMOUNT.fullmatch(text) or Decimal(text) <= 0:
                faults.append("InstdAmt: nur Euro, 0,01 bis 999.999.999,99")
    find = root.xpath
    for code, path in (
        ("SEPA", "//*[local-name()='SvcLvl']/*[local-name()='Cd']"),
        ("SLEV", "//*[local-name()='ChrgBr']"),
    ):
        if [e.text for e in find(path)] != [code]:
            faults.append(f"nur {code} erlaubt")
    amounts = [Decimal(e.text) for e in find("//*[local-name()='InstdAmt']") if e.text]
    for scope in find("//*[local-name()='GrpHdr'] | //*[local-name()='PmtInf']"):
        count = scope.xpath("string(*[local-name()='NbOfTxs'])")
        ctrl = scope.xpath("string(*[local-name()='CtrlSum'])")
        if count != str(len(amounts)) or ctrl != f"{sum(amounts, Decimal(0)):.2f}":
            faults.append(f"{local(scope)}: Anzahl oder Kontrollsumme")
    return faults


def validate(root) -> None:
    """ISO-Schema und DK-Regeln; Fehler bricht den Zahlungslauf ab."""
    etree.XMLSchema(etree.parse(str(SCHEMA))).assertValid(root)
    faults = dk_rules(root)
    if faults:
        raise ValueError("pain.001 verletzt DK-Regeln: " + "; ".join(faults))


class PayoutRuns(NoStore, SettlementView):
    def get(self, request, org_id):
        claims = []
        for claim in (
            MusicianClaim.objects.filter(organization=self.org, status="approved")
            .exclude(payout_items__released=False)
            .select_related(
                "assignment__performance__event", "assignment__musician__membership__person"
            )
            .order_by("pk")
        ):
            if PerformanceViewSet.visible(self, claim.assignment.performance):
                amount = total(claim) - paid_amount(claim)
                if amount > 0:
                    musician = claim.assignment.musician
                    claims.append(
                        {
                            "id": claim.pk,
                            "name": str(musician.membership.person)
                            if musician.membership_id
                            else musician.name,
                            "title": claim.assignment.performance.event.title,
                            "amount": str(amount),
                        }
                    )
        return Response(
            {
                "runs": [
                    data(run)
                    for run in PayoutRun.objects.filter(organization=self.org).order_by("-pk")
                    if run_visible(self, run)
                ],
                "claims": claims,
                "banks": list(
                    Account.objects.filter(
                        organization=self.org, kind="bank", is_active=True
                    ).values("id", "name")
                ),
            }
        )

    @transaction.atomic
    def post(self, request, org_id):
        lock_bank_sources(self.org)
        key = idempotency.claim(request, f"music.payout.{self.org.pk}", required=True)
        if key.done:
            run = get_object_or_404(PayoutRun, organization=self.org, pk=key.result["run"])
            if not run_visible(self, run):
                raise NotFound()
            return Response(data(run))
        form = RunInput(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        if (
            not timezone.localdate()
            <= values["execution_date"]
            <= timezone.localdate() + datetime.timedelta(days=365)
        ):
            raise serializers.ValidationError(
                gettext("Bitte einen zukünftigen Ausführungstag innerhalb eines Jahres wählen.")
            )
        bank = get_object_or_404(
            Account, organization=self.org, pk=values["bank_account"], kind="bank", is_active=True
        )
        debtor = Payee(data={"holder": self.org.name, "iban": bank.iban, "bic": bank.bic})
        debtor.is_valid(raise_exception=True)
        ids = [row["claim"] for row in values["items"]]
        claims = {
            row.pk: row
            for row in MusicianClaim.objects.select_for_update()
            .filter(organization=self.org, pk__in=ids)
            .select_related("assignment__performance__event")
        }
        if len(set(ids)) != len(ids) or len(claims) != len(ids):
            raise serializers.ValidationError(
                gettext("Bitte unterschiedliche verfügbare Vergütungen wählen.")
            )
        run = PayoutRun.objects.create(
            organization=self.org,
            bank_account=bank,
            execution_date=values["execution_date"],
            debtor=debtor.validated_data,
            created_by=request.user,
        )
        for row in values["items"]:
            claim = claims[row.pop("claim")]
            if not PerformanceViewSet.visible(self, claim.assignment.performance):
                raise NotFound()
            amount = total(claim) - paid_amount(claim)
            if (
                claim.status != "approved"
                or amount <= 0
                or PayoutItem.objects.filter(claim=claim, released=False).exists()
            ):
                raise serializers.ValidationError(
                    gettext(
                        "Diese Vergütung ist bezahlt, nicht freigegeben "
                        "oder bereits in einem Zahlungslauf."
                    )
                )
            PayoutItem.objects.create(
                organization=self.org, run=run, claim=claim, amount=amount, payee=row
            )
        xml(run)  # Fail atomically before a run can be offered for download.
        key.remember({"run": run.pk})
        record(self.org, request.user, "create", run, {"Zahlungslauf": [None, str(run.reference)]})
        return Response(data(run), status=201)


class PayoutRunAction(NoStore, SettlementView):
    @transaction.atomic
    def post(self, request, org_id, pk):
        lock_bank_sources(self.org)
        run = get_object_or_404(PayoutRun.objects.select_for_update(), organization=self.org, pk=pk)
        if not run_visible(self, run):
            raise NotFound()
        if request.data.get("action") == "cancel":
            if not run.cancelled_at:
                run.cancelled_at = timezone.now()
                run.save(update_fields=["cancelled_at"])
                run.items.update(released=True)
                record(
                    self.org,
                    request.user,
                    "update",
                    run,
                    {"Zahlungslauf aufgehoben": [False, True]},
                )
            return Response(data(run))
        if request.data.get("action") != "export" or run.cancelled_at:
            raise serializers.ValidationError(
                gettext("Dieser Zahlungslauf kann nicht exportiert werden.")
            )
        if not run.debtor.get("iban") or any(
            not item.payee.get("iban") for item in run.items.all()
        ):
            raise serializers.ValidationError(
                gettext("Dieser Zahlungslauf kann nicht exportiert werden.")
            )
        for item in run.items.select_related("claim"):
            if (
                item.claim.status != "approved"
                or total(item.claim) - paid_amount(item.claim) != item.amount
                or item.expense_id
            ):
                raise serializers.ValidationError(
                    gettext("Die Zahlungen haben sich geändert. Bitte den Zahlungslauf prüfen.")
                )
        content = xml(run)
        if not run.exported_at:
            run.exported_at = timezone.now()
            run.save(update_fields=["exported_at"])
            record(
                self.org, request.user, "update", run, {"Bankexport": [None, str(run.reference)]}
            )
        response = HttpResponse(content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="music-payout-{run.reference}.xml"'
        response["Cache-Control"] = "no-store"
        return response
