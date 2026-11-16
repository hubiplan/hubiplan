"""Auslagen erstatten (docs/auslagen.md): einreichen, freigeben, auszahlen, Storno."""

import datetime
import json
import uuid
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.tenancy import tenant_context
from expenses.models import ExpenseClaim, ExpenseLink
from finance.models import Account, Booking, Category

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
IBAN = "DE89370400440532013000"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def key():
    return {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}


def beleg(name="beleg.png"):
    return SimpleUploadedFile(name, PNG, content_type="image/png")


@pytest.fixture
def s(orgs, api):
    from portal.models import PortalAccess

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "expenses", "finance", "portal"})
    org.member_portal_enabled = True
    org.save()
    with tenant_context(org.pk):
        bank = Account.objects.create(
            organization=org,
            name="Girokonto",
            kind="bank",
            iban="DE02120300000000202051",
            bic="BYLADEM1001",
            opening_date=datetime.date(2020, 1, 1),
        )
        cat = Category.objects.create(organization=org, name="Jugendarbeit", kind="expense")
    kasse = make_user("kasse@example.org")
    give_role(
        kasse,
        org,
        permissions=["finance.view", "finance.edit", "expenses.view", "expenses.edit"],
        name="Kasse",
    )
    zweite = make_user("zweite@example.org")
    give_role(zweite, org, permissions=["expenses.view", "expenses.edit"], name="Prüfung")
    anna = make_member(org, "Anna", "Muster", email="anna@example.org")
    user = make_user("anna-konto@example.org")
    access = PortalAccess.objects.create(organization=org, membership=anna, user=user)
    give_role(user, org, permissions=["members.view"], name="Jugendwartin")
    return {
        "org": org,
        "bank": bank,
        "cat": cat,
        "kasse_user": kasse,
        "kasse": api(kasse),
        "zweite": api(zweite),
        "anna": api(user),
        "anna_user": user,
        "portal": f"/api/portal/{access.pk}/expenses/",
        "url": f"/api/orgs/{org.pk}/expenses/",
    }


def einreichen(s, amount="45.90", **extra):
    data = {
        "purpose": "Uniformteile für die Jugend",
        "purchase_date": (timezone.localdate() - datetime.timedelta(days=2)).isoformat(),
        "lines": json.dumps([{"amount": amount, "text": "Hemden"}]),
        "payout": "bank",
        "payee": json.dumps({"holder": "Anna Muster", "iban": IBAN}),
        "submit": "true",
        "file": beleg(),
        **extra,
    }
    return ok(s["anna"].post(s["portal"], data, **key()), 201)


def test_mitglied_reicht_mit_foto_ein_und_bekommt_nummer(s):
    claim = einreichen(s)
    assert claim["status"] == "submitted"
    assert claim["number"].startswith(f"A{timezone.localdate().year}-")
    assert len(claim["files"]) == 1
    rows = ok(s["kasse"].get(s["url"] + "?ansicht=review"))
    assert [r["id"] for r in rows["claims"]] == [claim["id"]]


def test_ohne_beleg_kein_einreichen(s):
    data = {
        "purpose": "Getränke",
        "purchase_date": timezone.localdate().isoformat(),
        "lines": '[{"amount": "12.00"}]',
        "payout": "cash",
        "submit": "true",
    }
    r = s["anna"].post(s["portal"], data, **key())
    assert r.status_code == 400
    assert "files" in r.json()


def test_gleicher_schluessel_legt_nur_einmal_an(s):
    data = {"purpose": "Entwurf ohne Netz", "lines": '[{"amount": "5"}]'}
    headers = key()
    a = ok(s["anna"].post(s["portal"], data, **headers), (200, 201))
    b = ok(s["anna"].post(s["portal"], data, **headers), (200, 201))
    assert a["id"] == b["id"]
    with tenant_context(s["org"].pk):
        assert ExpenseClaim.objects.filter(organization=s["org"]).count() == 1


def test_freigeben_auszahlen_mit_beleg_und_storno(s):
    claim = einreichen(s)
    url = f"{s['url']}{claim['id']}/"
    ok(
        s["kasse"].patch(
            url, {"categories": {str(claim["lines"][0]["id"]): s["cat"].pk}}, content_type=JSON
        )
    )
    ok(s["kasse"].post(url + "approve/", {}, content_type=JSON))
    paid = ok(s["kasse"].post(url + "pay/", {"account": s["bank"].pk}, content_type=JSON, **key()))
    assert paid["status"] == "paid"
    with tenant_context(s["org"].pk):
        c = ExpenseClaim.objects.get(pk=claim["id"])
        booking = c.booking
        assert booking.kind == Booking.Kind.EXPENSE
        assert booking.amount == Decimal("45.90")
        assert booking.receipts.count() == 1
        assert c.payee == {}
    from finance.services import cancel_booking

    with tenant_context(s["org"].pk):
        cancel_booking(booking, s["kasse_user"], "Falsches Konto")
        c.refresh_from_db()
        assert c.status == ExpenseClaim.Status.APPROVED
        assert c.booking_id is None


def test_eigene_auslage_der_kasse_bis_200_selbst_dann_sichten(s, api):
    from members.models import Membership

    with tenant_context(s["org"].pk):
        kasse = make_member(s["org"], "Karl", "Kasse", email="karl@example.org")
    from portal.models import PortalAccess

    access = PortalAccess.objects.create(
        organization=s["org"], membership=kasse, user=s["kasse_user"]
    )
    portal = f"/api/portal/{access.pk}/expenses/"
    small = ok(
        s["kasse"].post(
            portal,
            {
                "purpose": "Briefmarken",
                "purchase_date": timezone.localdate().isoformat(),
                "lines": '[{"amount": "180.00"}]',
                "payout": "cash",
                "submit": "true",
                "file": beleg(),
            },
            **key(),
        ),
        201,
    )
    big = ok(
        s["kasse"].post(
            portal,
            {
                "purpose": "Zelt",
                "purchase_date": timezone.localdate().isoformat(),
                "lines": '[{"amount": "250.00"}]',
                "payout": "cash",
                "submit": "true",
                "file": beleg(),
            },
            **key(),
        ),
        201,
    )
    done = ok(s["kasse"].post(f"{s['url']}{small['id']}/approve/", {}, content_type=JSON))
    assert done["status"] == "approved" and done["self_approved"]
    r = s["kasse"].post(f"{s['url']}{big['id']}/approve/", {}, content_type=JSON)
    assert r.status_code == 400
    # Die Kasse sichtet ihre eigene nicht nach; eine zweite Person schon
    assert (
        s["kasse"].post(s["url"] + "review/", {"ids": [small["id"]]}, content_type=JSON).status_code
        == 400
    )
    ok(s["zweite"].post(s["url"] + "review/", {"ids": [small["id"]]}, content_type=JSON))
    ok(s["zweite"].post(f"{s['url']}{big['id']}/approve/", {}, content_type=JSON))
    assert Membership  # genutzt für den Import


def test_kuerzen_braucht_grund_und_rueckfrage(s):
    claim = einreichen(s, amount="100.00")
    url = f"{s['url']}{claim['id']}/"
    r = s["kasse"].post(url + "approve/", {"amount": "80.00"}, content_type=JSON)
    assert r.status_code == 400
    ok(
        s["kasse"].post(
            url + "ask/", {"text": "Bitte den Kassenbon nachreichen."}, content_type=JSON
        )
    )
    mine = ok(s["anna"].get(f"{s['portal']}{claim['id']}/"))
    assert mine["status"] == "question"
    ok(
        s["anna"].post(
            f"{s['portal']}{claim['id']}/answer/", {"text": "Liegt bei."}, content_type=JSON
        )
    )
    done = ok(
        s["kasse"].post(url + "approve/", {"amount": "80.00", "reason": "Pfand"}, content_type=JSON)
    )
    assert done["status"] == "approved"


def test_sammelueberweisung_bucht_beim_export(s):
    claim = einreichen(s)
    url = f"{s['url']}{claim['id']}/"
    ok(
        s["kasse"].patch(
            url, {"categories": {str(claim["lines"][0]["id"]): s["cat"].pk}}, content_type=JSON
        )
    )
    ok(s["kasse"].post(url + "approve/", {}, content_type=JSON))
    listing = ok(s["kasse"].get(s["url"] + "transfers/"))
    assert [r["id"] for r in listing["ready"]] == [claim["id"]]
    run = ok(
        s["kasse"].post(
            s["url"] + "transfers/",
            {
                "bank_account": s["bank"].pk,
                "execution_date": timezone.localdate().isoformat(),
                "claims": [claim["id"]],
            },
            content_type=JSON,
            **key(),
        ),
        201,
    )
    r = s["kasse"].post(
        f"{s['url']}transfers/{run['id']}/", {"action": "export"}, content_type=JSON
    )
    assert r.status_code == 200
    assert b"pain.001" in r.content and IBAN.encode() in r.content
    with tenant_context(s["org"].pk):
        assert ExpenseClaim.objects.get(pk=claim["id"]).status == ExpenseClaim.Status.PAID
    again = ok(s["kasse"].get(s["url"] + "transfers/"))
    assert again["ready"] == []


def test_link_fuer_person_ohne_zugang(s, client):
    from expenses.services import settings_for

    with tenant_context(s["org"].pk):
        cfg = settings_for(s["org"])
        cfg.links_enabled = True
        cfg.save()
    link = ok(
        s["kasse"].post(
            s["url"] + "links/",
            {"name": "Erika Helferin", "email": "erika@example.org"},
            content_type=JSON,
        ),
        201,
    )
    token = link["url"].rsplit("/", 1)[1]
    info = ok(client.get(f"/api/public/expense/{token}/"))
    assert info["name"] == "Erika Helferin" and info["claims"] == []
    sent = ok(
        client.post(
            f"/api/public/expense/{token}/",
            {
                "purpose": "Kuchen fürs Sommerfest",
                "purchase_date": timezone.localdate().isoformat(),
                "lines": '[{"amount": "18.50"}]',
                "payout": "bank",
                "payee": json.dumps({"holder": "Erika Helferin", "iban": IBAN}),
                "file": beleg(),
            },
        ),
        201,
    )
    assert sent["claims"][0]["status"] == "submitted"
    assert "payee" not in sent["claims"][0]
    ok(s["kasse"].delete(f"{s['url']}links/{link['id']}/"))
    assert client.get(f"/api/public/expense/{token}/").status_code == 404
    with tenant_context(s["org"].pk):
        assert ExpenseLink.objects.get(pk=link["id"]).revoked_at


def test_andere_sehen_fremde_auslagen_nicht(s, orgs, api):
    claim = einreichen(s)
    fremd = make_user("fremd@example.org")
    give_role(fremd, orgs["b"], permissions=["expenses.view", "expenses.edit"], name="Kasse")
    c = api(fremd)
    assert c.get(f"/api/orgs/{s['org'].pk}/expenses/{claim['id']}/").status_code in (403, 404)


def test_modul_aus_keine_auslagen(s):
    s["org"].enabled_modules = [m for m in s["org"].enabled_modules if m != "expenses"]
    s["org"].save()
    assert s["anna"].get(s["portal"]).status_code == 404


def test_freigegebene_auslage_ist_verbindlichkeit(s):
    from finance import net_assets

    claim = einreichen(s, amount="30.00")
    ok(s["kasse"].post(f"{s['url']}{claim['id']}/approve/", {}, content_type=JSON))
    year = timezone.localdate().year
    with tenant_context(s["org"].pk):
        s["org"].refresh_from_db()
        data = net_assets.report(s["org"], year)
    rows = [r for r in data["liabilities"]["items"] if r["number"] == claim["number"]]
    assert len(rows) == 1 and rows[0]["amount"] == Decimal("30.00")
    assert rows[0]["seller"] == "Muster, Anna"
