"""Beiträge und Rechnungen.

- ``BillingSettings``: Rhythmus, Zahlungsziel, Konto und Kategorie für Zahlungen.
- ``FeeRate`` und ``AgeRate``: Beitrag je Mitgliedsart, Altersstufen mit eigenem
  Betrag oder Abschlag. Beträge gelten für ein ganzes Beitragsjahr (= Geschäftsjahr).
- ``WorkHourRule``: Pflichtstunden je Mitgliedsart mit Ersatzbeitrag.
- ``FeeRun``: ein Beitragslauf für einen Abrechnungszeitraum.
- ``Invoice`` mit ``InvoiceLine``: Rechnung an ein Mitglied oder als
  Sammelrechnung an eine Abteilung.
- ``Payment``: Zahlungseingang, erzeugt eine Einnahme-Buchung in der Kasse.
"""

from .debit import DebitItem, DebitRun, Mandate
from .dunning import Dunning, DunningLevel, dunning_pdf_path
from .households import HouseholdFeeRule, HouseholdPayer
from .incoming import IncomingInvoice, IncomingMail, IncomingMailbox, IncomingValidation
from .invoices import (
    Invoice,
    InvoiceAdvance,
    InvoiceArtifact,
    InvoiceDelivery,
    InvoiceHybridArtifact,
    InvoiceLine,
    Payment,
    electronic_file_path,
    hybrid_file_path,
    invoice_pdf_path,
)
from .partners import (
    BusinessPartner,
    PartnerAgreement,
    PartnerContact,
    PartnerDocument,
    PartnerField,
    PartnerFieldValue,
    partner_document_path,
)
from .settings import (
    PERIODS_PER_YEAR,
    PRO_RATA_MONTHS,
    ZERO,
    AgeRate,
    BillingSettings,
    FeeRate,
    FeeRun,
    ProRata,
    Rhythm,
    SizeRate,
    WorkHourRule,
)

__all__ = [
    "AgeRate",
    "BillingSettings",
    "BusinessPartner",
    "DebitItem",
    "DebitRun",
    "Dunning",
    "DunningLevel",
    "FeeRate",
    "FeeRun",
    "HouseholdFeeRule",
    "HouseholdPayer",
    "IncomingInvoice",
    "IncomingMail",
    "IncomingMailbox",
    "IncomingValidation",
    "Invoice",
    "InvoiceAdvance",
    "InvoiceArtifact",
    "InvoiceDelivery",
    "InvoiceHybridArtifact",
    "InvoiceLine",
    "Mandate",
    "PERIODS_PER_YEAR",
    "PRO_RATA_MONTHS",
    "PartnerAgreement",
    "PartnerContact",
    "PartnerDocument",
    "PartnerField",
    "PartnerFieldValue",
    "Payment",
    "ProRata",
    "Rhythm",
    "SizeRate",
    "WorkHourRule",
    "ZERO",
    "dunning_pdf_path",
    "electronic_file_path",
    "hybrid_file_path",
    "invoice_pdf_path",
    "partner_document_path",
]
