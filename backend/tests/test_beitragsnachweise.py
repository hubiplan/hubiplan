# ruff: noqa: F811
"""Ermäßigung mit Nachweis (docs/beitragsnachweise.md): Fristen, Beitragslauf, Einreichen über
Mitgliederbereich, Link und Mail, Prüfung, Vorprüfung, Erinnerungen, Online-Antrag."""

import datetime
import io
from decimal import Decimal
from email.message import EmailMessage

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from billing.models import Invoice
from core.tenancy import rls_bypass, tenant_context
from feeproofs import notify, precheck, services
from feeproofs.models import DiscountAssignment, FeeProof, ProofDiscount, ProofNotice
from portal.models import PortalAccess

from .factories import make_member, make_user
from .test_m9_billing import JSON, base, c, club, setup, start_run, zug  # noqa: F401

pytestmark = pytest.mark.django_db


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def pdf(*lines: str) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    page = canvas.Canvas(buf)
    y = 800
    for line in lines:
        page.drawString(50, y, line)
        y -= 20
    page.save()
    return buf.getvalue()


# Fester Stichtag: Fristen hängen am Datum (Januar 2026, Frist 28.02. läuft noch)
TAG = datetime.date(2026, 1, 20)
JAHR = 2026


@pytest.fixture
def stichtag(monkeypatch):
    import feeproofs.views
    import members.models

    monkeypatch.setattr(members.models, "today", lambda: TAG)
    monkeypatch.setattr(feeproofs.views, "today", lambda: TAG)
    return TAG


def bescheinigung(first="Anna", last="Muster", birth="17.05.1980") -> bytes:
    return pdf(
        "Universitaet Musterstadt",
        "Immatrikulationsbescheinigung",
        f"{first} {last}, geboren am {birth}",
        "ist im Wintersemester 2025/26 immatrikuliert.",
    )


@pytest.fixture
def rabatt(club, c, setup):  # noqa: F811
    data = ok(
        c.post(
            f"/api/orgs/{club.pk}/fee-proofs/discounts/",
            {"name": "Studierende", "discount_percent": "50"},
            content_type=JSON,
        )
    )
    return data


def zuordnen(c, club, membership, discount_id, valid_from="2015-01-01"):  # noqa: F811
    return ok(
        c.post(
            f"/api/orgs/{club.pk}/members/{membership.pk}/fee-discounts/",
            {"discount": discount_id, "valid_from": valid_from},
            content_type=JSON,
        )
    )


# --- Fristen ---


def test_frist_kulanz_und_spaeter_beginn(club):  # noqa: F811
    d = ProofDiscount(deadline_month=2, deadline_day=29, grace_days=14, late_join_days=28)
    dates = services.dates_for(club, d, 2027, None)
    assert dates.due == datetime.date(2027, 2, 28)  # kein Schaltjahr
    assert dates.final == datetime.date(2027, 3, 14)
    late = services.dates_for(club, d, 2027, datetime.date(2027, 6, 1))
    assert late.due == datetime.date(2027, 6, 29) and late.late_start
    # Wer im Januar beginnt, behält die normale Frist
    assert services.dates_for(club, d, 2027, datetime.date(2027, 1, 10)).due == datetime.date(
        2027, 2, 28
    )
    assert services.years_open(club, datetime.date(2026, 9, 30)) == [2026]
    assert services.years_open(club, datetime.date(2026, 10, 1)) == [2026, 2027]


def test_stand_je_jahr():
    dates = services.Dates(datetime.date(2027, 2, 28), datetime.date(2027, 3, 14), False)

    def proof(status, received):
        return FeeProof(pk=1, status=status, received_on=received)

    on_time = proof("received", datetime.date(2027, 2, 1))
    assert services.state_of(dates, [], datetime.date(2027, 3, 1))[0] == services.OPEN
    assert services.state_of(dates, [], datetime.date(2027, 3, 15))[0] == services.MISSING
    assert services.state_of(dates, [on_time], datetime.date(2027, 6, 1))[0] == services.PENDING
    late = proof("received", datetime.date(2027, 4, 1))
    assert services.state_of(dates, [late], datetime.date(2027, 6, 1))[0] == services.MISSING
    assert (
        services.state_of(
            dates, [proof("accepted", datetime.date(2027, 5, 1))], datetime.date(2027, 6, 1)
        )[0]
        == services.ACCEPTED
    )


# --- Einrichten ---


def test_ermaessigung_anlegen_und_pruefen(club, c, setup, rabatt):  # noqa: F811
    url = f"/api/orgs/{club.pk}/fee-proofs/discounts/"
    assert rabatt["deadline_month"] == 2 and rabatt["deadline_day"] == 28
    assert rabatt["kinds"][0] == "Immatrikulationsbescheinigung"
    assert (
        c.post(url, {"name": "studierende", "amount": "10"}, content_type=JSON).status_code == 400
    )
    assert c.post(url, {"name": "X"}, content_type=JSON).status_code == 400
    assert (
        c.post(
            url,
            {"name": "X", "amount": "1", "deadline_day": 31, "deadline_month": 2},
            content_type=JSON,
        ).status_code
        == 400
    )
    anna = make_member(club, "Anna", "Muster")
    zuordnen(c, club, anna, rabatt["id"])
    assert c.delete(f"{url}{rabatt['id']}/").status_code == 409


def test_ohne_beitragsmodul_unsichtbar(club, c):  # noqa: F811
    club.enabled_modules = [m for m in club.enabled_modules if m != "billing"]
    club.save()
    assert c.get(f"/api/orgs/{club.pk}/fee-proofs/discounts/").status_code == 404


# --- Beitragslauf ---


def test_beitragslauf_mit_und_ohne_nachweis(club, c, base, setup, rabatt):  # noqa: F811
    anna = make_member(club, "Anna", "Muster", email="anna@example.org")
    bert = make_member(club, "Bert", "Ohne", email="bert@example.org")
    make_member(club, "Carl", "Normal", email="carl@example.org")
    for m in (anna, bert):
        zuordnen(c, club, m, rabatt["id"])
    # Anna: Einsichtsvermerk für 2025 (Papier gesehen), Bert: nichts
    ok(
        c.post(
            f"/api/orgs/{club.pk}/members/{anna.pk}/fee-proofs/",
            {"discount": rabatt["id"], "year": 2025, "received_on": "2025-02-10"},
            content_type=JSON,
        )
    )
    preview = ok(c.post(f"{base}/runs/preview/", {"year": 2025, "period": 1}, content_type=JSON))
    assert preview["checks"]["proofs_regular"] == 1
    assert ok(start_run(c, base)) is not None
    with tenant_context(club.pk):
        totals = {i.recipient_name.splitlines()[0]: i.total for i in Invoice.objects.all()}
        detail = {
            i.recipient_name.splitlines()[0]: " ".join(line.detail for line in i.lines.all())
            for i in Invoice.objects.all()
        }
    assert totals["Anna Muster"] == totals["Carl Normal"] / 2
    assert totals["Bert Ohne"] == totals["Carl Normal"]
    assert "kein Nachweis" in detail["Bert Ohne"]


def test_vorlaeufig_waehrend_der_frist(club, rabatt):  # noqa: F811
    with tenant_context(club.pk):
        anna = make_member(club, "Anna", "Muster")
        discount = ProofDiscount.objects.get(pk=rabatt["id"])
        DiscountAssignment.objects.create(
            organization=club,
            membership=anna,
            discount=discount,
            valid_from=datetime.date(2015, 1, 1),
        )
        spans = list(anna.periods.all())
        ctx = services.BillingContext(club, [anna.pk], 2027, datetime.date(2027, 1, 20))
        amount, note = ctx.adjust(
            anna,
            spans,
            datetime.date(2027, 1, 1),
            anna.current_type().member_type_id,
            Decimal("60"),
        )
        assert amount == Decimal("30.00") and "offen" in note
        assert ctx.provisional == 1 and ctx.regular == 0
        late = services.BillingContext(club, [anna.pk], 2027, datetime.date(2027, 3, 1))
        amount, _note = late.adjust(
            anna,
            spans,
            datetime.date(2027, 1, 1),
            anna.current_type().member_type_id,
            Decimal("60"),
        )
        assert amount == Decimal("60") and late.regular == 1


# --- Mitgliederbereich, Prüfung, Vorprüfung ---


@pytest.fixture
def anna_portal(club, c, setup, rabatt, settings, tmp_path, stichtag):  # noqa: F811
    settings.PRIVATE_ROOT = tmp_path / "private"
    anna = make_member(club, "Anna", "Muster", email="anna@example.org")
    zuordnen(c, club, anna, rabatt["id"])
    user = make_user("anna-konto@example.org")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(organization=club, membership=anna, user=user)
    member = Client()
    member.force_login(user)
    return {"anna": anna, "member": member, "url": f"/api/portal/{access.pk}/fee-proofs/"}


def hochladen(s, rabatt, data, name="bescheinigung.pdf", content_type="application/pdf"):
    return s["member"].post(
        s["url"],
        {
            "discount": rabatt["id"],
            "year": JAHR,
            "file": SimpleUploadedFile(name, data, content_type=content_type),
        },
    )


def test_einreichen_pruefen_datei_weg(
    club, c, rabatt, anna_portal, mailoutbox, django_capture_on_commit_callbacks
):  # noqa: F811
    s = anna_portal
    data = ok(s["member"].get(s["url"]))
    assert [st["state"] for st in data["states"]][0] == "open"
    res = ok(hochladen(s, rabatt, bescheinigung()))
    proof = res["proofs"][0]
    assert proof["status"] == "received" and proof["has_file"]
    assert "precheck" not in proof  # Vorprüfung sieht nur der Vorstand
    queue = ok(c.get(f"/api/orgs/{club.pk}/fee-proofs/"))
    assert len(queue) == 1 and queue[0]["precheck"]["level"] == "green"
    assert queue[0]["precheck"]["valid_until"].endswith("-03-31")
    pid = queue[0]["id"]
    assert c.get(f"/api/orgs/{club.pk}/fee-proofs/{pid}/file/").status_code == 200
    decide = f"/api/orgs/{club.pk}/fee-proofs/{pid}/decide/"
    assert c.post(decide, {"action": "reject"}, content_type=JSON).status_code == 400
    # Ungültig zu Beginn des Beitragsjahres und am Eingangstag
    old = datetime.date(JAHR - 1, 3, 31).isoformat()
    assert (
        c.post(decide, {"action": "accept", "valid_until": old}, content_type=JSON).status_code
        == 400
    )
    mailoutbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        done = ok(
            c.post(
                decide,
                {"action": "accept", "valid_until": queue[0]["precheck"]["valid_until"]},
                content_type=JSON,
            )
        )
    assert done["status"] == "accepted" and not done["has_file"] and done["file_deleted"]
    assert any("anerkannt" in m.subject for m in mailoutbox)
    assert c.get(f"/api/orgs/{club.pk}/fee-proofs/{pid}/file/").status_code == 404
    data = ok(s["member"].get(s["url"]))
    assert data["states"][0]["state"] == "accepted"


def test_falsche_datei_und_fremdes_jahr(rabatt, anna_portal):  # noqa: F811
    s = anna_portal
    assert hochladen(s, rabatt, b"kein pdf").status_code == 400
    assert hochladen(s, rabatt, b"GIF89a", "x.gif", "image/gif").status_code == 400
    res = s["member"].post(
        s["url"],
        {
            "discount": rabatt["id"],
            "year": JAHR - 3,
            "file": SimpleUploadedFile("a.pdf", bescheinigung(), content_type="application/pdf"),
        },
    )
    assert res.status_code == 400


def test_automatisch_anerkennen(club, c, rabatt, anna_portal):  # noqa: F811
    ok(
        c.patch(
            f"/api/orgs/{club.pk}/fee-proofs/settings/", {"auto_accept": True}, content_type=JSON
        )
    )
    s = anna_portal
    res = ok(hochladen(s, rabatt, bescheinigung()))
    assert res["proofs"][0]["status"] == "accepted"
    # Falscher Name: bleibt beim Vorstand
    res = ok(hochladen(s, rabatt, bescheinigung(first="Otto", last="Anders")))
    statuses = sorted(p["status"] for p in res["proofs"])
    assert statuses == ["accepted", "received"]
    queue = ok(c.get(f"/api/orgs/{club.pk}/fee-proofs/"))
    assert queue[0]["precheck"]["level"] == "red"


def test_vorpruefung_einzeln():
    needed = datetime.date(JAHR, 1, 1)
    text = precheck._fold("Sommersemester 2026 · gültig bis 30.09.2026 · Müller")
    assert precheck.suggested_until(text) == datetime.date(2026, 9, 30)
    assert "mueller" in text
    res = precheck.check(
        b"", "image/jpeg", first_name="A", last_name="B", birth_date=None, needed_until=needed
    )
    assert res["level"] == "yellow" and res["reasons"] == ["photo"]
    res = precheck.check(
        pdf(""),
        "application/pdf",
        first_name="A",
        last_name="B",
        birth_date=None,
        needed_until=needed,
    )
    assert res["level"] == "red"
    assert precheck.signature_info(bescheinigung()) is None


# --- Link und Antwort per Mail ---


def test_link_und_antwort_per_mail(club, rabatt, anna_portal, settings):  # noqa: F811
    from billing.incoming_mail import process_message

    settings.EINVOICE_IMAP_HOST = "imap.example.org"
    settings.EINVOICE_IMAP_ADDRESS = "rechnung@example.org"
    anna = anna_portal["anna"]
    with tenant_context(club.pk):
        discount = ProofDiscount.objects.get(pk=rabatt["id"])
        link, token = notify.new_link(anna, discount, JAHR, datetime.date(2099, 1, 1))
    public = Client()
    data = ok(public.get(f"/api/public/fee-proof/{token}/"))
    assert data["first_name"] == "Anna" and data["state"]["state"] == "open"
    res = public.post(
        f"/api/public/fee-proof/{token}/",
        {"file": SimpleUploadedFile("a.pdf", bescheinigung(), content_type="application/pdf")},
    )
    assert ok(res)["state"]["state"] == "pending"
    assert public.get("/api/public/fee-proof/falsch/").status_code == 404

    reply = notify.reply_address(link.mail_key)
    assert reply.startswith("rechnung+nw") and reply.endswith("@example.org")
    msg = EmailMessage()
    msg["From"] = "anna@example.org"
    msg["To"] = reply
    msg["Subject"] = "Re: Nachweis"
    msg["Message-ID"] = "<1@example.org>"
    msg.set_content("Anbei")
    msg.add_attachment(bescheinigung(), maintype="application", subtype="pdf", filename="b.pdf")
    assert process_message(msg.as_bytes()) == "move"
    with rls_bypass():
        channels = sorted(
            FeeProof.objects.filter(membership=anna).values_list("channel", flat=True)
        )
    assert channels == ["link", "mail"]
    # Unbekannte Kennung: bleibt liegen, gehört keinem Verein
    msg.replace_header("To", "rechnung+nwunbekannt99@example.org")
    assert process_message(msg.as_bytes()) == "keep"


# --- Erinnerungen ---


def test_erinnerungen_und_mitteilung(club, c, rabatt, mailoutbox):  # noqa: F811
    anna = make_member(club, "Anna", "Muster", email="anna@example.org")
    zuordnen(c, club, anna, rabatt["id"])

    def at(day):
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time(10)))

    mailoutbox.clear()
    assert notify.run(at(datetime.date(2026, 1, 10))) == 0
    assert notify.run(at(datetime.date(2026, 1, 20))) == 1
    assert notify.run(at(datetime.date(2026, 1, 21))) == 0
    assert "/nachweis/" in mailoutbox[-1].body
    assert notify.run(at(datetime.date(2026, 2, 15))) == 1
    assert "Erinnerung" in mailoutbox[-1].subject
    assert notify.run(at(datetime.date(2026, 3, 2))) == 1
    assert "normaler Beitrag" in mailoutbox[-1].subject
    assert notify.run(at(datetime.date(2026, 3, 3))) == 0
    with rls_bypass():
        assert sorted(ProofNotice.objects.values_list("kind", flat=True)) == [
            "after",
            "first",
            "second",
        ]


def test_zu_erledigen_und_zwei_jahre(club, c, rabatt, anna_portal):
    def kinds():
        tasks = ok(c.get(f"/api/orgs/{club.pk}/open-tasks/"))
        items = tasks["items"] if isinstance(tasks, dict) else tasks
        return [t["kind"] for t in items]

    # Seit 2015 zugeordnet, ohne anerkannten Nachweis in den beiden Vorjahren
    assert "fee_proofs_stale" in kinds()
    stale = ok(c.get(f"/api/orgs/{club.pk}/fee-proofs/overview/", {"stand": "zwei-jahre"}))
    assert [r["last_name"] for r in stale["stale"]] == ["Muster"]
    # Für das laufende Jahr eingereicht: zu prüfen, kein Vorschlag mehr
    ok(hochladen(anna_portal, rabatt, bescheinigung()))
    assert "fee_proofs_review" in kinds() and "fee_proofs_stale" not in kinds()
    overview = ok(c.get(f"/api/orgs/{club.pk}/fee-proofs/overview/"))
    assert overview["counts"]["pending"] == 1


def test_mitgliederbereich_zeigt_menuepunkt(club, rabatt, anna_portal):  # noqa: F811
    from portal.views import portal_summary

    access = PortalAccess.objects.get(membership=anna_portal["anna"])
    data = portal_summary(access)
    assert data["fee_proofs_enabled"] is True and data["fee_proofs_due"] == 1
    ok(hochladen(anna_portal, rabatt, bescheinigung()))
    assert portal_summary(access)["fee_proofs_due"] == 0  # eingereicht, Vorstand prüft
    other = make_member(club, "Ohne", "Ermäßigung")
    with tenant_context(club.pk):
        access2 = PortalAccess.objects.create(
            organization=club, membership=other, user=make_user("ohne@example.org")
        )
    assert portal_summary(access2)["fee_proofs_enabled"] is False
