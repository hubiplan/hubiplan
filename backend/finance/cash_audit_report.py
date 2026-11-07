"""Prüfbericht der Kassenprüfer als PDF (Konzept vereinskasse-steuern, S6)."""

from __future__ import annotations

from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from organizations.theme import effective_theme

from . import cash_audit
from .project_report import _build
from .report import _euro, _styles, _table

RESULT = {"": "offen", "ok": "in Ordnung", "issue": "Rückfrage", "na": "entfällt"}


def render(audit) -> bytes:
    org = audit.organization
    st = _styles()
    r = st["right"]
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    label = org.fiscal_label(audit.year)
    start, last = org.fiscal_range(audit.year)
    facts = cash_audit.facts(org, audit.year)

    def p(text: str, style="normal"):
        return Paragraph(text, st[style])

    story: list = [
        p(f"<b>Bericht der Kassenprüfer {escape(label)}</b>", "title"),
        p(
            f"{escape(org.name)} · Geschäftsjahr {start:%d.%m.%Y} bis {last:%d.%m.%Y}",
        ),
    ]
    if audit.auditors:
        story.append(p(f"Kassenprüfer: {escape(audit.auditors)}"))
    if audit.status == audit.Status.DONE and audit.closed_at:
        story.append(p(f"Prüfung abgeschlossen am {timezone.localtime(audit.closed_at):%d.%m.%Y}"))
    else:
        story.append(p("<b>Entwurf:</b> Die Prüfung ist noch nicht abgeschlossen."))
    if audit.meeting_id:
        when = timezone.localdate(audit.meeting.event.starts_at)
        story.append(p(f"Für: {escape(audit.meeting.event.title)} am {when:%d.%m.%Y}"))
    story.append(Spacer(1, 4 * mm))
    story.append(
        p(
            f"Geprüft wurden {facts['bookings']} Buchungen des Geschäftsjahres. "
            f"Ohne Beleg: {facts['without_receipt']}. Nummernlücken: {facts['gap_count']}. "
            f"Jahresabschluss {'erstellt' if facts['closed'] else 'noch nicht erstellt'}."
        )
    )

    # Kontenabgleich
    story.append(p("<b>Kontenabgleich zum Jahresende</b>", "h2"))
    balances = cash_audit.book_balances(audit)
    rows = [
        [
            p("<b>Konto</b>"),
            p("<b>Kassenbuch</b>", "right"),
            p("<b>Nachweis</b>", "right"),
            p("<b>Differenz</b>", "right"),
            p("<b>Anmerkung</b>"),
        ]
    ]
    for row in audit.accounts.select_related("account"):
        book = balances.get(row.account_id, Decimal("0"))
        stated = row.statement_balance
        rows.append(
            [
                p(escape(row.account.name)),
                Paragraph(_euro(book), r),
                Paragraph(_euro(stated) if stated is not None else "–", r),
                Paragraph(_euro(stated - book) if stated is not None else "–", r),
                p(escape(row.note)),
            ]
        )
    story.append(_table(rows, [42 * mm, 28 * mm, 28 * mm, 24 * mm, 50 * mm], primary, False))

    # Prüfpunkte
    story.append(p("<b>Prüfpunkte</b>", "h2"))
    rows = [[p("<b>Prüfpunkt</b>"), p("<b>Ergebnis</b>"), p("<b>Anmerkung</b>")]]
    for key, text in cash_audit.CHECKS:
        entry = audit.checks.get(key) or {}
        rows.append(
            [
                p(escape(text)),
                p(RESULT.get(entry.get("result", ""), "offen")),
                p(escape(entry.get("note", ""))),
            ]
        )
    story.append(_table(rows, [80 * mm, 24 * mm, 68 * mm], primary, False))

    # Stichproben
    samples = list(audit.samples.select_related("booking__organization"))
    issues = sum(1 for s in samples if s.result == "issue")
    story.append(p(f"<b>Stichproben ({len(samples)}, davon {issues} mit Rückfrage)</b>", "h2"))
    rows = [
        [
            p("<b>Buchung</b>"),
            p("<b>Datum</b>"),
            p("<b>Text</b>"),
            p("<b>Betrag</b>", "right"),
            p("<b>Ergebnis</b>"),
        ]
    ]
    for s in samples:
        b = s.booking
        result = RESULT.get(s.result, "offen")
        if s.note:
            result += f": {escape(s.note)}"
        rows.append(
            [
                p(escape(b.display_number)),
                p(f"{b.date:%d.%m.%Y}"),
                p(escape(b.text)),
                Paragraph(_euro(b.amount), r),
                p(result),
            ]
        )
    story.append(_table(rows, [26 * mm, 20 * mm, 60 * mm, 24 * mm, 42 * mm], primary, False))

    if audit.findings:
        story.append(p("<b>Feststellungen</b>", "h2"))
        for line in audit.findings.splitlines():
            story.append(p(escape(line) or "&nbsp;"))

    story.append(p("<b>Empfehlung</b>", "h2"))
    story.append(
        p(
            escape(str(audit.get_recommendation_display()))
            if audit.recommendation
            else "Noch keine Empfehlung."
        )
    )
    story += [
        Spacer(1, 16 * mm),
        p("_______________________________&nbsp;&nbsp;&nbsp;&nbsp;_______________________________"),
        p("Ort, Datum, Unterschrift" + "&nbsp;" * 30 + "Ort, Datum, Unterschrift", "small"),
    ]
    return _build(org, f"Prüfbericht Kasse {label}", story)
