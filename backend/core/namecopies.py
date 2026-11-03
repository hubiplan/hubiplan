"""Umfang des Bestandslaufs für strukturierte Namenskopien (Issue 112, PR 5).

Felder mit automatisch erzeugten Namenstexten und vollständige Namens-Snapshots
gehören dazu. Benutzerkonten, öffentliches Impressum und allgemeine Freitexte nicht.
"""

FIELDS = {
    "access.RoleAssignment": ("name",),
    "billing.Invoice": ("recipient_name",),
    "billing.InvoiceLine": ("text", "detail"),
    "circulars.CircularRecipient": ("first_name", "last_name"),
    "competitions.Starter": ("name",),
    "competitions.ShootOffEntry": ("name",),
    "competitions.Prize": ("winner_name",),
    "competitions.Shot": ("name",),
    "competitions.AwardGrant": ("name",),
    "competitions.CertificateTemplate": ("signers",),
    "entries.EntryPerson": ("name",),
    "honors.Reign": ("name",),
    "honors.Companion": ("name",),
    "finance.Booking": ("counterparty", "text"),
    "finance.YearClosing": ("purged_by_name", "retention_hold_by_name"),
    "finance.ReopenedClosing": ("closed_by_name", "reopened_by_name"),
    "finance.CashReceipt": ("counterparty_name", "treasurer_name"),
    "finance.DonationStatement": ("donor_name", "signer_name", "items"),
    "finance.Donation": ("donor_name",),
    "finance.BankLine": ("name", "details"),
    "finance.CashCount": ("counted_by", "witness"),
    "finance.ReserveMovement": ("created_by_name",),
    "website.HeldMessage": ("recipient_name", "sender_name"),
}
