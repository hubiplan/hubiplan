"""Frozen UBL -> locally validated Factur-X EN16931, PDF/A-3b and audit reports."""

import hashlib
import os
import shutil
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext

from finance.einvoice import _root, parse_xml, render, xml_from_pdf

from .einvoice_services import read_artifact
from .models import InvoiceHybridArtifact


def run(args, folder, *, env=None):
    result = subprocess.run(  # noqa: S603 -- fixed trusted tools, private generated input, no shell
        args, cwd=folder, capture_output=True, timeout=60, check=False, env=env
    )
    if result.returncode:
        raise ValueError("Local document validation failed")


def convert(source, seller):
    """No external validators or network services; every stage fails closed."""
    from facturx import generate_cii_xml, generate_from_binary, parse_ubl_cii_xml, xml_check_xsd
    from lxml import etree

    data = parse_ubl_cii_xml(source, check_xsd=True, check_schematron=False)
    data["BT-24"] = "urn:cen.eu:en16931:2017"
    cii = generate_cii_xml(data, level="en16931", check_xsd=False, check_schematron=False)
    tree = etree.fromstring(cii, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    # factur-x 7.9 marks the required, empty delivery container xsi:nil although
    # CII's schema disallows that attribute. An empty container is the valid form.
    for node in tree.iter():
        if node.tag.endswith("}ApplicableHeaderTradeDelivery") and len(node) == 0:
            node.attrib.pop("{http://www.w3.org/2001/XMLSchema-instance}nil", None)
    cii = etree.tostring(tree, xml_declaration=True, encoding="UTF-8")
    xml_check_xsd(cii, flavor="factur-x", level="en16931")
    original, converted = parse_xml(source), parse_xml(cii)
    # A syntax conversion may never silently discard or alter financial content.
    for key in original.keys() - {"format", "lines", "taxes"}:
        if original[key] != converted[key]:
            raise ValueError(f"Conversion changed {key}")
    if original["lines"] != converted["lines"]:
        raise ValueError("Conversion changed invoice lines")
    tax_key = lambda group: (group["category"], group["rate"])  # noqa: E731
    if sorted(original["taxes"], key=tax_key) != sorted(converted["taxes"], key=tax_key):
        raise ValueError("Conversion changed VAT groups")
    java, gs = shutil.which("java"), shutil.which("gs")
    if not java or not gs:
        raise ValueError("Local PDF tools unavailable")
    rules = files("facturx") / "xsd_and_schematron/facturx-en16931/FACTUR-X_EN16931.xslt"
    with tempfile.TemporaryDirectory(prefix="hubiplan-hybrid-") as folder:
        path = Path(folder)
        (path / "invoice.xml").write_bytes(cii)
        run(
            [
                java,
                "-Xmx256m",
                "-Djavax.xml.accessExternalDTD=",
                "-Djavax.xml.accessExternalSchema=file",
                "-Djavax.xml.accessExternalStylesheet=file",
                "-cp",
                str(Path(settings.EINVOICE_VALIDATOR_DIR) / "validator.jar"),
                "net.sf.saxon.Transform",
                "-ext:off",
                "-dtd:off",
                "-xi:off",
                "-s:invoice.xml",
                f"-xsl:{rules}",
                "-o:cii-report.xml",
            ],
            folder,
        )
        cii_report = (path / "cii-report.xml").read_bytes()
        svrl = _root(cii_report)
        if any(
            n.tag.endswith("}failed-assert") and n.get("flag", "fatal").lower() != "warning"
            for n in svrl.iter()
        ):
            raise ValueError("CII EN16931 validation failed")
        (path / "readable.pdf").write_bytes(render(converted, seller))
        templates = sorted(Path("/usr/share/ghostscript").glob("*/lib/PDFA_def.ps"))
        if not templates:
            raise ValueError("PDF/A template unavailable")
        definition = (
            templates[-1]
            .read_text()
            .replace(
                "/ICCProfile (srgb.icc)",
                "/ICCProfile (/usr/share/color/icc/ghostscript/srgb.icc)",
            )
        )
        definition = definition.replace("/Title (Title)", "/Title (Invoice)")
        (path / "definition.ps").write_text(definition)
        run(
            [
                gs,
                "-dSAFER",
                "--permit-file-read=/usr/share/color/icc/ghostscript/srgb.icc",
                "-dPDFA=3",
                "-dPDFACompatibilityPolicy=2",
                "-dBATCH",
                "-dNOPAUSE",
                "-sColorConversionStrategy=RGB",
                "-sDEVICE=pdfwrite",
                "-sOutputFile=pdfa.pdf",
                "definition.ps",
                "readable.pdf",
            ],
            folder,
        )
        pdf = generate_from_binary(
            (path / "pdfa.pdf").read_bytes(),
            cii,
            flavor="factur-x",
            level="en16931",
            check_xsd=True,
            check_schematron=False,
            pdf_metadata={"title": original["number"], "author": seller},
        )
        if xml_from_pdf(pdf) != cii:
            raise ValueError("Embedded XML differs")
        (path / "final.pdf").write_bytes(pdf)
        env = {**os.environ, "JAVA_OPTS": "-Xmx256m"}
        result = subprocess.run(  # noqa: S603 -- fixed local validator and generated PDF
            ["/opt/verapdf/verapdf", "--format", "xml", "--flavour", "3b", "final.pdf"],
            cwd=folder,
            capture_output=True,
            timeout=60,
            check=False,
            env=env,
        )
        report = _root(result.stdout)
        validations = [n for n in report.iter() if n.tag.endswith("validationReport")]
        if (
            result.returncode
            or len(validations) != 1
            or validations[0].get("isCompliant") != "true"
        ):
            raise ValueError("Final PDF/A-3b validation failed")
        return pdf, cii, cii_report, result.stdout


def create(invoice, document):
    source = read_artifact(invoice, "cancellation_xml" if document == "cancellation" else "xml")
    existing = invoice.hybrid_artifacts.filter(document=document).first()
    if existing:
        return existing
    try:
        pdf, xml, cii_report, pdf_report = convert(source, parse_xml(source)["seller"])
    except Exception as exc:  # noqa: BLE001 -- third-party schema library raises plain Exception
        raise ValidationError(
            gettext("Die ZUGFeRD-Prüfung ist fehlgeschlagen. Es wurde keine Datei freigegeben.")
        ) from exc
    row = InvoiceHybridArtifact.objects.create(
        organization=invoice.organization,
        invoice=invoice,
        document=document,
        sha256=hashlib.sha256(pdf).hexdigest(),
        xml_sha256=hashlib.sha256(xml).hexdigest(),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )
    for field, raw, name in [
        ("pdf", pdf, "invoice.pdf"),
        ("xml", xml, "factur-x.xml"),
        ("cii_report", cii_report, "cii-validation.xml"),
        ("pdf_report", pdf_report, "pdfa-validation.xml"),
    ]:
        getattr(row, field).save(name, ContentFile(raw), save=False)
    row.save()
    return row


def read(invoice, document):
    source = read_artifact(invoice, "cancellation_xml" if document == "cancellation" else "xml")
    row = invoice.hybrid_artifacts.get(document=document)
    with row.pdf.open("rb") as stream:
        pdf = stream.read()
    if (
        hashlib.sha256(pdf).hexdigest() != row.sha256
        or hashlib.sha256(source).hexdigest() != row.source_sha256
    ):
        raise ValidationError(gettext("Die Prüfsumme des Rechnungsoriginals stimmt nicht."))
    return pdf
