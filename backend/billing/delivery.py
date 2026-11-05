"""Provider-neutral HTTPS gateway, with durable request IDs and reconciled retries.

Adapters implement the small /documents contract documented in docs/e-rechnungen.md.
Only server administrators configure endpoints, tenant identities and credential names.
"""

import base64
import hashlib
import json
import os
import re
from datetime import timedelta
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from finance.einvoice import _child, _root

from .einvoice_services import read_artifact
from .models import Invoice, InvoiceDelivery

TERMINAL = {"submitted", "delivered", "rejected"}


def config(org):
    raw = settings.EINVOICE_GATEWAYS.get(str(org.pk))
    if not raw:
        return None
    base = urlsplit(raw.get("base_url", ""))
    if (
        base.scheme != "https"
        or not base.hostname
        or base.username
        or base.password
        or base.query
        or base.fragment
        or raw.get("channel") not in {"peppol", "portal"}
        or not re.fullmatch(r"[0-9]{4}:[^\s:]{1,100}", raw.get("participant", ""))
        or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", raw.get("token_env", ""))
    ):
        raise ValidationError(gettext("Die Versandanbindung ist nicht korrekt eingerichtet."))
    value = {key: raw[key] for key in ["base_url", "channel", "participant"]}
    value["base_url"] = value["base_url"].rstrip("/")
    value["signature"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    value["label"] = str(raw.get("label", raw["channel"]))[:100]
    value["token"] = os.environ.get(raw["token_env"]) or settings.EINVOICE_GATEWAY_TOKENS.get(
        raw["token_env"], ""
    )
    if not value["token"]:
        raise ValidationError(gettext("Die Zugangsdaten der Versandanbindung fehlen."))
    return value


def state(row):
    return {
        "id": row.pk,
        "document": row.document,
        "request_id": str(row.request_id),
        "provider": row.provider_label,
        "status": row.status,
        "receipt": row.receipt,
        "error_code": row.error_code,
        "updated_at": row.updated_at,
    }


def overview(invoice):
    cfg = config(invoice.organization)
    return {
        "configuration": {
            "enabled": bool(cfg),
            **({key: cfg[key] for key in ["label", "channel", "participant"]} if cfg else {}),
        },
        "deliveries": [state(row) for row in invoice.deliveries.order_by("-created_at")],
    }


def participants(source, cfg):
    root = _root(source)
    output = []
    for role in ["AccountingSupplierParty", "AccountingCustomerParty"]:
        node = _child(root, role, "Party", "EndpointID")
        if node is None or not node.text:
            raise ValidationError(gettext("Elektronische Absender- und Empfängeradresse fehlen."))
        scheme = node.get("schemeID", "")
        if cfg["channel"] == "peppol" and not re.fullmatch(r"[0-9]{4}", scheme):
            raise ValidationError(
                gettext("Für Peppol sind registrierte elektronische Adressen erforderlich.")
            )
        output.append(f"{scheme}:{node.text}")
    if output[0] != cfg["participant"]:
        raise ValidationError(
            gettext("Der Absender des Originals passt nicht zur Versandanbindung.")
        )
    return output


def exchange(cfg, row, method, payload=None):
    with requests.Session() as session:
        session.trust_env = False
        url = cfg["base_url"] + "/documents" + (f"/{row.request_id}" if method == "GET" else "")
        with session.request(
            method,
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['token']}",
                "Idempotency-Key": str(row.request_id),
                "Accept": "application/json",
            },
            timeout=(5, 20),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code == 404 and method == "GET":
                return None
            if response.status_code not in {200, 201, 202}:
                raise ValueError("gateway_response")
            chunks, size = [], 0
            for chunk in response.iter_content(4096):
                size += len(chunk)
                if size > 65536:
                    raise ValueError("gateway_response")
                chunks.append(chunk)
            body = json.loads(b"".join(chunks))
    if (
        not isinstance(body, dict)
        or body.get("request_id") != str(row.request_id)
        or body.get("sha256") != row.sha256
        or body.get("status") not in TERMINAL
    ):
        raise ValueError("gateway_receipt")
    # Never persist arbitrary provider responses, URLs or authentication data.
    return {
        "request_id": str(row.request_id),
        "sha256": row.sha256,
        "status": body["status"],
        "reference": str(body.get("reference", ""))[:200],
    }


def dispatch(invoice, document, operation):
    cfg = config(invoice.organization)
    if not cfg:
        raise ValidationError(gettext("Für diesen Verein ist keine Versandanbindung eingerichtet."))
    # Persist the intent BEFORE network I/O. A crash is reconciled with GET by stable UUID.
    with transaction.atomic():
        current = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if document == "cancellation":
            if current.status != Invoice.Status.CANCELLED:
                raise ValidationError(gettext("Es liegt kein Stornooriginal vor."))
        elif (
            current.status in {Invoice.Status.DRAFT, Invoice.Status.CANCELLED}
            and operation == "send"
        ):
            raise ValidationError(
                gettext("Nur festgeschriebene Rechnungen können versendet werden.")
            )
        source = read_artifact(current, "cancellation_xml" if document == "cancellation" else "xml")
        sender, recipient = participants(source, cfg)
        row, _ = InvoiceDelivery.objects.get_or_create(
            organization=invoice.organization,
            invoice=invoice,
            document=document,
            provider_signature=cfg["signature"],
            defaults={"provider_label": cfg["label"], "sha256": hashlib.sha256(source).hexdigest()},
        )
        if row.sha256 != hashlib.sha256(source).hexdigest():
            raise ValidationError(gettext("Die Prüfsumme des Rechnungsoriginals stimmt nicht."))
        if row.status in {"delivered", "rejected"} or (
            row.status == "submitted" and operation == "send"
        ):
            return state(row)
        if (
            row.attempted_at
            and row.status == "dispatching"
            and row.attempted_at > timezone.now() - timedelta(seconds=90)
        ):
            return state(row)
        row.status, row.attempted_at, row.error_code = "dispatching", timezone.now(), ""
        row.save(update_fields=["status", "attempted_at", "error_code", "updated_at"])
    try:
        receipt = exchange(cfg, row, "GET")
        if receipt is None and operation == "send":
            receipt = exchange(
                cfg,
                row,
                "POST",
                {
                    "request_id": str(row.request_id),
                    "sha256": row.sha256,
                    "channel": cfg["channel"],
                    "sender": sender,
                    "recipient": recipient,
                    "document": document,
                    "content_type": "application/xml",
                    "content_base64": base64.b64encode(source).decode("ascii"),
                },
            )
        outcome, error = (receipt["status"], "") if receipt else ("unknown", "not_found")
    except (requests.RequestException, ValueError, TypeError, KeyError):
        receipt, outcome, error = {}, "unknown", "gateway_unconfirmed"
    with transaction.atomic():
        row = InvoiceDelivery.objects.select_for_update().get(pk=row.pk)
        row.status, row.error_code = outcome, error
        if receipt:
            row.receipt = receipt
        row.save(update_fields=["status", "receipt", "error_code", "updated_at"])
    return state(row)
