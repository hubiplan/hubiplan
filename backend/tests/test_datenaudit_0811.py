"""Datenaudit 08.11.2026: Regressionstests zu den Befunden (nur erfundene Daten)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from finance import services as finance_services
from finance.models import Account, Booking, Donation
from peering.models import RemoteInvoice

from .test_m9_billing import JSON, base, c, club, setup, zug  # noqa: F401
from .test_verbund_kopplung import VEREIN, _setup, api, couple, net, world  # noqa: F401
from .test_verbund_rechnungen import category, coupled, fed_settings, members  # noqa: F401
from .test_verbund_rechnungen import issue as fed_issue
from .test_zuwendung_quellbuchung import issue, source  # noqa: F401
from .test_zuwendungen import _private, ev, ready  # noqa: F401

pytestmark = pytest.mark.django_db


# --- DA-03: Zuwendung folgt ihrer Buchung ---


class TestZuwendungFolgtBuchung:
    def test_betrag_und_datum_ziehen_mit(self, source, ready, c, club):
        day = timezone.localdate() - datetime.timedelta(days=1)
        url = f"{ready}/bookings/{source['booking']['id']}/"
        response = c.patch(url, {"amount": "50.00", "date": day.isoformat()}, content_type=JSON)
        assert response.status_code == 200, response.json()
        with tenant_context(club.pk):
            donation = Donation.objects.get(pk=source["donation"])
        assert donation.amount == Decimal("50.00") and donation.date == day

    def test_rueckgaengig_setzt_beides_zurueck(self, source, ready, c, club):
        url = f"{ready}/bookings/{source['booking']['id']}/"
        response = c.patch(url, {"amount": "50.00"}, content_type=JSON)
        assert response.status_code == 200, response.json()
        undo = c.post(
            f"{ready.removesuffix('/finance')}/changes/{response['X-Change-Set']}/undo/",
            {},
            content_type=JSON,
        )
        assert undo.status_code == 200, undo.json()
        with tenant_context(club.pk):
            assert Booking.objects.get(pk=source["booking"]["id"]).amount == Decimal("100.00")
            assert Donation.objects.get(pk=source["donation"]).amount == Decimal("100.00")

    def test_loeschen_entfernt_unbestaetigte_zuwendung(self, source, ready, c, club):
        assert c.delete(f"{ready}/bookings/{source['booking']['id']}/").status_code == 204
        with tenant_context(club.pk):
            assert not Donation.objects.filter(pk=source["donation"]).exists()

    def test_storno_entfernt_unbestaetigte_zuwendung(self, source, ready, c, club):
        response = c.post(
            f"{ready}/bookings/{source['booking']['id']}/storno/",
            {"reason": "Erfundene Korrektur"},
            content_type=JSON,
        )
        assert response.status_code == 201, response.json()
        with tenant_context(club.pk):
            assert not Donation.objects.filter(pk=source["donation"]).exists()

    def test_zuwendung_betrag_nur_wie_buchung(self, source, ready, c, club):
        url = f"{ready}/donations/{source['donation']}/"
        response = c.patch(url, {"amount": "70.00"}, content_type=JSON)
        assert response.status_code == 400
        assert "Buchung" in str(response.json())
        # Abgleich auf den Betrag der Buchung bleibt möglich
        with tenant_context(club.pk):
            Donation.objects.filter(pk=source["donation"]).update(amount=Decimal("70.00"))
        response = c.patch(url, {"amount": "100.00"}, content_type=JSON)
        assert response.status_code == 200, response.json()

    def test_ausstellen_prueft_abgleich(self, source, ready, c, club):
        with tenant_context(club.pk):
            Donation.objects.filter(pk=source["donation"]).update(amount=Decimal("70.00"))
        year = timezone.localdate().year
        checks = c.get(f"{ready}/donations/checks/?jahr={year}").json()
        assert checks["booking_mismatch"] == 1
        response = c.post(
            f"{ready}/donation-statements/",
            {"donations": [source["donation"]]},
            content_type=JSON,
        )
        assert response.status_code == 400
        assert "Buchung" in str(response.json())
        with tenant_context(club.pk):
            Donation.objects.filter(pk=source["donation"]).update(amount=Decimal("100.00"))
        assert c.get(f"{ready}/donations/checks/?jahr={year}").json()["booking_mismatch"] == 0
        issue(c, ready, source)

    def test_bestaetigte_zuwendung_sperrt_aenderung(self, source, ready, c, club):
        issue(c, ready, source)
        url = f"{ready}/bookings/{source['booking']['id']}/"
        assert c.patch(url, {"amount": "50.00"}, content_type=JSON).status_code == 400
        with tenant_context(club.pk):
            assert Donation.objects.get(pk=source["donation"]).amount == Decimal("100.00")


class TestQuittungMitZuwendung:
    @pytest.fixture
    def quittung(self, settings, tmp_path, ready, c, club, setup):
        """Abgeschlossene Einnahme-Quittung, deren Buchung als Zuwendung erfasst ist."""
        import uuid

        from .test_quittung import LINE

        settings.PRIVATE_ROOT = tmp_path / "private"
        category = c.post(
            f"{ready}/categories/",
            {"name": "Erfundene Barspenden", "kind": "income", "donations": True},
            content_type=JSON,
        ).json()["id"]
        url = f"{ready}/cash-receipts/"
        draft = c.post(
            url,
            {
                "direction": "in",
                "counterparty_name": "Paula Prüfperson",
                "amount": "40.00",
                "purpose": "Erfundene Spende",
                "account": setup["cash"],
                "category": category,
            },
            content_type=JSON,
        )
        assert draft.status_code == 201, draft.json()
        rid = draft.json()["id"]
        for role in ("treasurer", "counterparty"):
            c.put(f"{url}{rid}/signatures/{role}/", LINE, content_type=JSON)
        done = c.post(
            f"{url}{rid}/finalize/",
            {"confirmed": True},
            content_type=JSON,
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert done.status_code == 200, done.json()
        imported = c.post(
            f"{ready}/donations/import/", {"year": timezone.localdate().year}, content_type=JSON
        )
        assert imported.status_code == 200 and imported.json()["created"] == 1
        with tenant_context(club.pk):
            donation = Donation.objects.get(booking_id=done.json()["booking"])
        return {"url": f"{url}{rid}/", "donation": donation.pk}

    def test_storno_entfernt_unbestaetigte_zuwendung(self, quittung, c, club):
        response = c.post(
            quittung["url"] + "cancel/", {"reason": "Erfundene Korrektur"}, content_type=JSON
        )
        assert response.status_code == 200, response.json()
        with tenant_context(club.pk):
            assert not Donation.objects.filter(pk=quittung["donation"]).exists()

    def test_bestaetigte_zuwendung_sperrt_storno(self, quittung, ready, c, club):
        c.patch(
            f"{ready}/donations/{quittung['donation']}/",
            {"donor_address": "Erfundener Weg 1\n12345 Musterstadt"},
            content_type=JSON,
        )
        issue(c, ready, {"donation": quittung["donation"]})
        response = c.post(
            quittung["url"] + "cancel/", {"reason": "Erfundene Korrektur"}, content_type=JSON
        )
        assert response.status_code == 400
        assert "Bestätigung" in str(response.json())
        with tenant_context(club.pk):
            assert Donation.objects.get(pk=quittung["donation"]).statement_id is not None


# --- DA-02: Barkasse im Verbund ---


class TestVerbundBarkasse:
    def test_barkasse_faellt_nicht_unter_null(self, net, world, members):
        fed, club_ = world["fed"], world["club"]
        lower, upper = coupled(net, world)
        fed_settings(fed)
        fed_issue(net, world, upper)
        incoming = RemoteInvoice.objects.get(coupling=lower)
        with tenant_context(club_.pk):
            kasse = Account.objects.create(
                organization=club_,
                name="Barkasse",
                kind=Account.Kind.CASH,
                opening_date=datetime.date(2026, 1, 1),
            )
        cat = category(club_, "expense")
        with net.on(VEREIN):
            resp = api(world["club_board"]).post(
                f"/api/orgs/{club_.pk}/peering/couplings/{lower.pk}/invoices/{incoming.pk}/paid/",
                {"date": timezone.localdate().isoformat(), "account": kasse.pk, "category": cat.pk},
                content_type=JSON,
            )
        assert resp.status_code == 400
        assert "Barkasse" in str(resp.json()) or "Kasse" in str(resp.json())
        with tenant_context(club_.pk):
            assert finance_services.balance(kasse) == Decimal("0")
        incoming.refresh_from_db()
        assert incoming.paid_reported_on is None


# --- DR-01/DR-02, FD-11: festgeschriebene Rechnungen ---


class TestRechnungSchutz:
    @pytest.fixture
    def rechnung(self, club, c, base):
        from .factories import make_member

        member = make_member(club, "Erika", "Prüfmuster", "erfunden@example.org")
        response = c.post(
            f"{base}/invoices/",
            {
                "recipient_kind": "member",
                "membership": member.pk,
                "date": timezone.localdate().isoformat(),
                "due_date": timezone.localdate().isoformat(),
                "subject": "Erfundene Rechnung",
                "lines": [{"text": "Erfundener Beitrag", "amount": "60.00"}],
            },
            content_type=JSON,
        )
        assert response.status_code == 201, response.json()
        pk = response.json()["id"]
        assert c.post(f"{base}/invoices/{pk}/finalize/").status_code == 200
        return pk

    def test_loeschen_in_der_datenbank_gesperrt(self, club, rechnung):
        from django.db import IntegrityError, transaction

        from billing.models import Invoice

        with tenant_context(club.pk):
            with pytest.raises(IntegrityError), transaction.atomic():
                Invoice.objects.filter(pk=rechnung).delete()
            for change in (
                {"number": 999},
                {"date": datetime.date(2020, 1, 1)},
                {"status": "draft"},
            ):
                with pytest.raises(IntegrityError), transaction.atomic():
                    Invoice.objects.filter(pk=rechnung).update(**change)
            assert Invoice.objects.filter(pk=rechnung).exists()

    def test_mahnstufe_und_storno_bleiben_moeglich(self, club, rechnung):
        from billing.models import Invoice

        with tenant_context(club.pk):
            Invoice.objects.filter(pk=rechnung).update(dunning_level=1)
            Invoice.objects.filter(pk=rechnung).update(status="cancelled")
            assert Invoice.objects.get(pk=rechnung).status == "cancelled"

    def test_einheit_loeschen_bleibt_moeglich(self, club, rechnung):
        from django.db import transaction

        from billing.models import Invoice
        from finance import gobd

        with tenant_context(club.pk), transaction.atomic():
            gobd.release_unit(club.pk)
            Invoice.objects.filter(pk=rechnung).delete()
            assert not Invoice.objects.filter(pk=rechnung).exists()
            transaction.set_rollback(True)


# --- DA-01, FD-01: Ein-/Austritt korrigieren ---


def _member_url(org, member, suffix=""):
    return f"/api/orgs/{org.pk}/members/{member['id']}/{suffix}"


class TestEinAustrittKorrigieren:
    @pytest.fixture
    def ausgetreten(self, api, orgs, board_a):
        from .test_m2_members import admit, make_types

        org = orgs["a"]
        with tenant_context(org.pk):
            types = make_types(org)
        cl = api(board_a)
        m = admit(cl, org, types["aktiv"], last_name="Korrektur", entry_date="2015-03-01").json()
        resp = cl.post(
            _member_url(org, m, "exit/"),
            {"exit_date": "2025-12-31", "exit_reason": "exit"},
            content_type=JSON,
        )
        assert resp.status_code in (200, 201), resp.json()
        rows = cl.get(_member_url(org, m, "periods/")).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        return {"org": org, "cl": cl, "m": m, "period": rows[0]["id"]}

    def _membership(self, a):
        from members.models import Membership

        return Membership.objects.get(pk=a["m"]["id"])

    def test_austritt_spaeter_art_zieht_mit(self, ausgetreten):
        a = ausgetreten
        resp = a["cl"].post(
            _member_url(a["org"], a["m"], "correct-period/"),
            {
                "period": a["period"],
                "entry_date": "2015-03-01",
                "exit_date": "2026-06-30",
                "exit_reason": "exit",
            },
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        with tenant_context(a["org"].pk):
            membership = self._membership(a)
            assert membership.current_type(datetime.date(2026, 3, 1)) is not None
            ends = list(membership.type_assignments.values_list("valid_until", flat=True))
            assert ends == [datetime.date(2026, 6, 30)]

    def test_austritt_aufheben_oeffnet_art_und_leert_grund(self, ausgetreten):
        a = ausgetreten
        resp = a["cl"].post(
            _member_url(a["org"], a["m"], "correct-period/"),
            {"period": a["period"], "entry_date": "2015-03-01", "exit_date": None},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        with tenant_context(a["org"].pk):
            membership = self._membership(a)
            period = membership.periods.get()
            assert period.exit_date is None and period.exit_reason == ""
            assert membership.current_type(datetime.date(2026, 3, 1)) is not None

    def test_eintritt_frueher_art_zieht_mit(self, ausgetreten):
        a = ausgetreten
        resp = a["cl"].post(
            _member_url(a["org"], a["m"], "correct-period/"),
            {
                "period": a["period"],
                "entry_date": "2014-01-01",
                "exit_date": "2025-12-31",
                "exit_reason": "exit",
            },
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        with tenant_context(a["org"].pk):
            starts = list(
                self._membership(a).type_assignments.values_list("valid_from", flat=True)
            )
            assert starts == [datetime.date(2014, 1, 1)]

    def test_patch_nur_fuer_bemerkung(self, ausgetreten):
        a = ausgetreten
        url = _member_url(a["org"], a["m"], f"periods/{a['period']}/")
        resp = a["cl"].patch(url, {"exit_date": "2026-06-30"}, content_type=JSON)
        assert resp.status_code == 400
        resp = a["cl"].patch(url, {"note": "Erfundene Bemerkung"}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
