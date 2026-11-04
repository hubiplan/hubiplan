"""UBL 2.1 / XRechnung 3.0 aus dem validierten fachlichen Datenmodell."""

import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
NS = {
    "": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate(lines):
    """Steuer je Kategorie/Satz runden, Restcents nach größten Nachkommaresten verteilen."""
    result = []
    groups = defaultdict(list)
    for source in lines:
        line = dict(source)
        net = money(Decimal(line["quantity"]) * Decimal(line["unit_price"]))
        net += money(line.get("charge", 0)) - money(line.get("allowance", 0))
        line["net"] = net
        line["tax"] = (net * Decimal(line["tax_rate"]) / 100).quantize(CENT, rounding=ROUND_DOWN)
        result.append(line)
        groups[(line["tax_category"], Decimal(line["tax_rate"]))].append(line)
    taxes = []
    for (category, rate), items in groups.items():
        net = sum((line["net"] for line in items), Decimal(0))
        tax = money(net * rate / 100)
        cents = int((tax - sum((line["tax"] for line in items), Decimal(0))) / CENT)
        # Jede Zeile erhält höchstens einen Restcent. Auch bei vielen Kleinbeträgen
        # wird dadurch keine einzelne Bruttozeile negativ.
        remainder_order = sorted(
            items, key=lambda line: line["net"] * rate / 100 - line["tax"], reverse=True
        )
        for line in remainder_order[:cents]:
            line["tax"] += CENT
        taxes.append(
            {
                "category": category,
                "rate": rate,
                "net": net,
                "tax": tax,
                "reason": "; ".join(
                    dict.fromkeys(line["tax_reason"] for line in items if line.get("tax_reason"))
                ),
            }
        )
    for line in result:
        line["gross"] = line["net"] + line["tax"]
    net = sum((line["net"] for line in result), Decimal(0))
    tax = sum((group["tax"] for group in taxes), Decimal(0))
    return {"lines": result, "taxes": taxes, "net": net, "tax": tax, "gross": net + tax}


def element(parent, name, value=None, **attrs):
    prefix, local = name.split(":")
    node = ET.SubElement(parent, f"{{{NS[prefix]}}}{local}", attrs)
    if value is not None:
        node.text = str(value)
    return node


def amount(parent, name, value):
    return element(parent, "cbc:" + name, f"{money(value):.2f}", currencyID="EUR")


def party(root, name, data, seller=False):
    node = element(element(root, "cac:" + name), "cac:Party")
    element(node, "cbc:EndpointID", data["email"], schemeID="EM")
    if data.get("identifier"):
        element(element(node, "cac:PartyIdentification"), "cbc:ID", data["identifier"])
    address = element(node, "cac:PostalAddress")
    element(address, "cbc:StreetName", data["street"])
    element(address, "cbc:CityName", data["city"])
    element(address, "cbc:PostalZone", data["postcode"])
    element(element(address, "cac:Country"), "cbc:IdentificationCode", data["country"])
    for key, scheme in [("vat_id", "VAT"), ("tax_number", "FC")]:
        if data.get(key) and (seller or key == "vat_id"):
            tax = element(node, "cac:PartyTaxScheme")
            element(tax, "cbc:CompanyID", data[key])
            element(element(tax, "cac:TaxScheme"), "cbc:ID", scheme)
    entity = element(node, "cac:PartyLegalEntity")
    element(entity, "cbc:RegistrationName", data["name"])
    if seller:
        contact = element(node, "cac:Contact")
        element(contact, "cbc:Name", data["contact"])
        element(contact, "cbc:Telephone", data["phone"])
        element(contact, "cbc:ElectronicMail", data["email"])


def tax_category(parent, name, category, rate, reason=""):
    node = element(parent, "cac:" + name)
    element(node, "cbc:ID", category)
    # XRechnung BR-DE-14 verlangt BT-119 auch bei O; auf Positionsebene
    # verbietet EN 16931 BR-O-05 dagegen BT-152.
    if category != "O" or name == "TaxCategory":
        element(node, "cbc:Percent", f"{Decimal(rate):f}")
    if reason:
        element(node, "cbc:TaxExemptionReason", reason)
    element(element(node, "cac:TaxScheme"), "cbc:ID", "VAT")


def generate(invoice):
    data = invoice.electronic_data
    totals = calculate([line.electronic_data for line in invoice.lines.all()])
    root = ET.Element(f"{{{NS['']}}}Invoice")
    element(
        root,
        "cbc:CustomizationID",
        "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
    )
    element(root, "cbc:ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    element(root, "cbc:ID", invoice.display_number)
    element(root, "cbc:IssueDate", invoice.date.isoformat())
    element(root, "cbc:DueDate", invoice.due_date.isoformat())
    element(root, "cbc:InvoiceTypeCode", "380")
    element(root, "cbc:Note", "\n".join(filter(None, [invoice.subject, invoice.note])))
    element(root, "cbc:DocumentCurrencyCode", "EUR")
    element(root, "cbc:BuyerReference", data["buyer_reference"])
    period = element(root, "cac:InvoicePeriod")
    element(period, "cbc:StartDate", data["service_start"])
    element(period, "cbc:EndDate", data["service_end"])
    if data.get("order_reference"):
        element(element(root, "cac:OrderReference"), "cbc:ID", data["order_reference"])
    party(root, "AccountingSupplierParty", data["seller"], seller=True)
    party(root, "AccountingCustomerParty", data["buyer"])
    payment = element(root, "cac:PaymentMeans")
    element(payment, "cbc:PaymentMeansCode", "58")
    element(payment, "cbc:PaymentID", invoice.display_number)
    element(element(payment, "cac:PayeeFinancialAccount"), "cbc:ID", data["iban"])
    taxes = element(root, "cac:TaxTotal")
    amount(taxes, "TaxAmount", totals["tax"])
    for group in totals["taxes"]:
        subtotal = element(taxes, "cac:TaxSubtotal")
        amount(subtotal, "TaxableAmount", group["net"])
        amount(subtotal, "TaxAmount", group["tax"])
        tax_category(subtotal, "TaxCategory", group["category"], group["rate"], group["reason"])
    summary = element(root, "cac:LegalMonetaryTotal")
    for name, value in [
        ("LineExtensionAmount", totals["net"]),
        ("TaxExclusiveAmount", totals["net"]),
        ("TaxInclusiveAmount", totals["gross"]),
        ("PayableAmount", totals["gross"]),
    ]:
        amount(summary, name, value)
    for index, data in enumerate(totals["lines"], start=1):
        line = element(root, "cac:InvoiceLine")
        element(line, "cbc:ID", index)
        element(line, "cbc:InvoicedQuantity", data["quantity"], unitCode=data["unit"])
        amount(line, "LineExtensionAmount", data["net"])
        for key, charge in [("allowance", "false"), ("charge", "true")]:
            if Decimal(data.get(key, 0)):
                adjustment = element(line, "cac:AllowanceCharge")
                element(adjustment, "cbc:ChargeIndicator", charge)
                element(adjustment, "cbc:AllowanceChargeReason", data["adjustment_reason"])
                amount(adjustment, "Amount", data[key])
        item = element(line, "cac:Item")
        element(item, "cbc:Name", data["text"])
        tax_category(item, "ClassifiedTaxCategory", data["tax_category"], data["tax_rate"])
        price = element(line, "cac:Price")
        element(price, "cbc:PriceAmount", data["unit_price"], currencyID="EUR")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
