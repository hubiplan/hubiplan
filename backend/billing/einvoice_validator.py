"""Lokale, fail-closed KoSIT-Prüfung mit festgeschriebenem Regelstand."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext

from finance.einvoice import EInvoiceError, _root

VERSION = "KoSIT 1.6.3 / XRechnung 3.0.2 / 2026-08-31"
REPORT_NS = "http://www.xoev.de/de/validator/varl/1"


def failed(message, status="invalid"):
    return {
        "status": status,
        "validator": VERSION,
        "messages": [{"level": "error", "text": message}],
    }, b""


def validate(xml, timeout=None):
    """Prüft das XML mit dem KoSIT-Validator. ``timeout`` in Sekunden, sonst
    ``EINVOICE_VALIDATOR_TIMEOUT``; der Hintergrundjob lässt sich mehr Zeit."""
    try:
        root = _root(xml)
    except EInvoiceError as exc:
        return failed(str(exc))
    # Nicht nur lokale Tag-Namen: ein beliebiges XML ist keine E-Rechnung.
    if root.tag not in {
        "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice",
        "{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}CreditNote",
        "{urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100}CrossIndustryInvoice",
    }:
        return failed(gettext("Keine unterstützte Rechnungsstruktur erkannt."))
    base = Path(settings.EINVOICE_VALIDATOR_DIR)
    if not (base / "validator.jar").is_file() or not (base / "scenarios.xml").is_file():
        return failed(
            gettext("Die E-Rechnungsprüfung ist auf diesem Server nicht eingerichtet."),
            "unavailable",
        )
    with tempfile.TemporaryDirectory(prefix="hubiplan-einvoice-") as folder:
        source = Path(folder) / "invoice.xml"
        source.write_bytes(xml)
        try:
            java = shutil.which("java")
            if not java:
                return failed(
                    gettext("Die E-Rechnungsprüfung ist auf diesem Server nicht eingerichtet."),
                    "unavailable",
                )
            run = subprocess.run(  # noqa: S603 - feste Argumente, keine Shell, Datei im privaten Temp-Verzeichnis
                [
                    java,
                    "-Xmx256m",
                    "-Djavax.xml.accessExternalDTD=",
                    "-Djavax.xml.accessExternalSchema=file",
                    "-Djavax.xml.accessExternalStylesheet=file",
                    "-jar",
                    str(base / "validator.jar"),
                    "-s",
                    str(base / "scenarios.xml"),
                    "-r",
                    str(base),
                    "-o",
                    folder,
                    str(source),
                ],
                cwd=folder,
                capture_output=True,
                timeout=timeout or settings.EINVOICE_VALIDATOR_TIMEOUT,
                check=False,
            )
            report_file = Path(folder) / "invoice-report.xml"
            if not report_file.is_file() or report_file.stat().st_size > 10 * 1024 * 1024:
                return failed(
                    gettext("Die E-Rechnungsprüfung konnte nicht abgeschlossen werden."),
                    "unavailable",
                )
            raw = report_file.read_bytes()
            from defusedxml import ElementTree

            report = ElementTree.fromstring(raw, forbid_dtd=True)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return failed(
                gettext("Die E-Rechnungsprüfung konnte nicht abgeschlossen werden."), "unavailable"
            )
    messages = []
    # Der generierte Bericht enthält auch eine Kopie des Eingangs. Nur die vom
    # Validator erzeugten message-Elemente auswerten, nie darin eingebettetes XML.
    for node in report.findall(f".//{{{REPORT_NS}}}message"):
        messages.append(
            {
                "level": node.get("level", "error"),
                "code": node.get("code", ""),
                "text": " ".join(node.itertext()).strip()[:2000],
            }
        )
    accepted = (
        run.returncode == 0
        and report.find(f"{{{REPORT_NS}}}assessment/{{{REPORT_NS}}}accept") is not None
    )
    if not accepted and not messages:
        messages.append(
            {
                "level": "error",
                "text": gettext(
                    "Die Datei erfüllt die Prüfregeln nicht. Details stehen im Prüfbericht."
                ),
            }
        )
    return {
        "status": "valid" if accepted else "invalid",
        "validator": VERSION,
        "messages": messages[:200],
    }, raw
