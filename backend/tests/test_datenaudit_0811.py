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
            starts = list(self._membership(a).type_assignments.values_list("valid_from", flat=True))
            assert starts == [datetime.date(2014, 1, 1)]

    def test_patch_nur_fuer_bemerkung(self, ausgetreten):
        a = ausgetreten
        url = _member_url(a["org"], a["m"], f"periods/{a['period']}/")
        resp = a["cl"].patch(url, {"exit_date": "2026-06-30"}, content_type=JSON)
        assert resp.status_code == 400
        resp = a["cl"].patch(url, {"note": "Erfundene Bemerkung"}, content_type=JSON)
        assert resp.status_code == 200, resp.json()


# --- Schritt 5: Beiträge, Mahnungen, Lastschrift ---


class TestEhrungVerteuertNie:
    def _title(self, **kw):
        from members.models import HonoraryTitle

        return HonoraryTitle(name="Ehrenmitglied", **kw)

    def test_fester_ehrenbeitrag_ueber_normalem_gilt_nicht(self):
        from members.honorary import adjusted_fee

        title = self._title(fee_mode="amount", fee_amount=Decimal("20.00"))
        assert adjusted_fee([title], Decimal("12.00")) is None
        assert adjusted_fee([title], Decimal("30.00")) == (Decimal("20.00"), "Ehrenmitglied")

    def test_frei_und_rabatt_unveraendert(self):
        from members.honorary import adjusted_fee

        free = self._title(fee_mode="free")
        assert adjusted_fee([free], Decimal("12.00")) == (Decimal("0.00"), "Ehrenmitglied")
        half = self._title(fee_mode="discount", fee_discount_percent=Decimal("50"))
        assert adjusted_fee([half], Decimal("12.00")) == (Decimal("6.00"), "Ehrenmitglied")


class TestSepaFeiertage:
    @pytest.mark.parametrize(
        "day",
        [
            datetime.date(2027, 1, 1),
            datetime.date(2027, 3, 26),  # Karfreitag
            datetime.date(2027, 3, 29),  # Ostermontag
            datetime.date(2027, 5, 1),
            datetime.date(2026, 12, 25),
            datetime.date(2026, 12, 26),
        ],
    )
    def test_target2_feiertage(self, day):
        from billing.sepa import bank_day, target2_holiday

        assert target2_holiday(day) and not bank_day(day)

    def test_naechster_bankarbeitstag(self):
        from billing.sepa import next_bank_day

        # Karfreitag 2027 → Dienstag nach Ostermontag
        assert next_bank_day(datetime.date(2027, 3, 26)) == datetime.date(2027, 3, 30)
        assert next_bank_day(datetime.date(2026, 12, 24)) == datetime.date(2026, 12, 24)
        assert next_bank_day(datetime.date(2026, 12, 25)) == datetime.date(2026, 12, 28)


class TestMahnabstand:
    def test_naechste_stufe_erst_nach_frist(self, club):
        from billing.models import Dunning, DunningLevel, Invoice
        from billing.services import dunning_proposals

        from .factories import make_member

        today = timezone.localdate()
        with tenant_context(club.pk):
            member = make_member(club, "Erika", "Muster", "erika@example.org")
            for level, days in ((1, 0), (2, 1)):
                DunningLevel.objects.create(
                    organization=club, level=level, name=f"Stufe {level}", days=days
                )
            invoice = Invoice.objects.create(
                organization=club,
                recipient_kind="member",
                membership=member,
                recipient_name="Erika Muster",
                date=today - datetime.timedelta(days=40),
                due_date=today - datetime.timedelta(days=30),
                status="open",
                year=today.year,
                number=1,
                total=Decimal("60.00"),
                dunning_level=1,
            )
            last = Dunning.objects.create(
                organization=club,
                invoice=invoice,
                level=1,
                name="Stufe 1",
                date=today - datetime.timedelta(days=5),
                due_date=today + datetime.timedelta(days=9),
            )
            assert dunning_proposals(club, today) == []
            # Am Fristtag noch nicht, am Tag danach schon
            assert dunning_proposals(club, last.due_date) == []
            [(found, level)] = dunning_proposals(club, last.due_date + datetime.timedelta(days=1))
            assert found.pk == invoice.pk and level.level == 2


# --- Schritt 6: Import, Export, Eingaben ---


class TestImportExport:
    def test_ungueltiges_datum_im_zusatzfeld_ist_zeilenfehler(self, orgs):
        from types import SimpleNamespace

        from customfields.models import FieldDefinition
        from exchange import importer

        org = orgs["a"]
        with tenant_context(org.pk):
            d = FieldDefinition.objects.create(
                organization=org, label="Ehrennadel am", key="ehrennadel", field_type="date"
            )
        g = importer.PersonGroup(rows=[2])
        lookups = SimpleNamespace(definitions={d.pk: d})
        importer._read_fields(g, ["31.02.2020"], {"0": f"field:{d.pk}"}, lookups, 2)
        assert len(g.errors) == 1 and "Zeile 2" in g.errors[0]

    def test_widerspruechliche_zusatzfelder(self, orgs):
        from types import SimpleNamespace

        from customfields.models import FieldDefinition
        from exchange import importer

        org = orgs["a"]
        with tenant_context(org.pk):
            d = FieldDefinition.objects.create(
                organization=org, label="Schuhgröße", key="schuh", field_type="text"
            )
        g = importer.PersonGroup(rows=[2, 3])
        lookups = SimpleNamespace(definitions={d.pk: d})
        importer._read_fields(g, ["42"], {"0": f"field:{d.pk}"}, lookups, 2)
        importer._read_fields(g, ["42"], {"0": f"field:{d.pk}"}, lookups, 3)
        assert g.errors == []
        importer._read_fields(g, ["44"], {"0": f"field:{d.pk}"}, lookups, 4)
        assert len(g.errors) == 1 and "Zeile 4" in g.errors[0]

    def test_excel_ohne_sichtbares_apostroph(self, orgs):
        import io

        from openpyxl import load_workbook

        from exchange.export import render_xlsx

        content = render_xlsx(
            orgs["a"],
            "Liste",
            [["Telefon", "Bemerkung", "Text"], ["+49 2131 123456", "-", "=1+1"]],
        )
        ws = load_workbook(io.BytesIO(content)).active
        assert ws["A2"].value == "+49 2131 123456"
        assert ws["B2"].value == "-"
        assert ws["C2"].value == "=1+1" and ws["C2"].data_type == "s"

    def test_import_entfernt_apostroph_alter_exporte(self):
        from exchange.reading import _cell

        assert _cell("'+49 2131 123456") == "+49 2131 123456"
        assert _cell("'-") == "-"
        assert _cell("O'Neill") == "O'Neill"

    def test_tausenderpunkt_wird_abgelehnt(self):
        from django.core.exceptions import ValidationError

        from customfields.models import clean_scalar

        for text in ("1.000", "2.500", "1.000.000"):
            with pytest.raises(ValidationError):
                clean_scalar("number", text)
        assert clean_scalar("number", "1000") == 1000
        assert clean_scalar("number", "1,5") == 1.5
        assert clean_scalar("number", "1.5") == 1.5
        assert clean_scalar("number", "1234.567") == 1234.567

    @pytest.mark.parametrize(
        "country,code,expected",
        [("", "1067", "01067"), ("Deutschland", "1067", "01067"), ("Österreich", "1010", "1010")],
    )
    def test_plz_mit_fuehrender_null(self, country, code, expected):
        from exchange import importer

        g = importer.PersonGroup(rows=[2], data={"postal_code": code, "country": country})
        importer._pad_postal_code(g, 2)
        assert g.data["postal_code"] == expected
        assert bool(g.notes) is (expected != code)


# --- Schritt 7: Würden ---


class TestOrdnungszahlVorname:
    def test_bindestrich_und_schreibweise(self):
        from types import SimpleNamespace

        from honors import numbering

        def reign(pk, name, year):
            return SimpleNamespace(
                pk=pk,
                person=None,
                person_id=None,
                name=name,
                ordinal=None,
                sort_year=year,
                valid_from=None,
            )

        reigns = [
            reign(1, "Hans-Peter Muster", 2001),
            reign(2, "hans peter Beispiel", 2002),
            reign(3, "Hans Probe", 2003),
        ]
        assert numbering.ordinals(reigns) == {1: 1, 2: 2, 3: 1}


class TestArtwechselMitSpaetererArt:
    def test_spaetere_art_sperrt(self, orgs):
        from members.models import MemberTypeAssignment
        from members.workflows import change_type

        from .factories import make_member
        from .test_m2_members import make_types

        org = orgs["a"]
        with tenant_context(org.pk):
            types = make_types(org)
            membership = make_member(org, "Erika", "Muster", "erika@example.org")
            MemberTypeAssignment.objects.filter(membership=membership).delete()
            MemberTypeAssignment.objects.create(
                organization=org,
                membership=membership,
                member_type=types["passiv"],
                valid_from=timezone.localdate() + datetime.timedelta(days=30),
            )
            from rest_framework.exceptions import ValidationError

            with pytest.raises(ValidationError, match="spätere Art"):
                change_type(membership, types["aktiv"], timezone.localdate())
