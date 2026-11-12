"""Adresszusatz (z. B. c/o) der Vereinsanschrift: Impressum, Briefkopf, E-Rechnung."""

import xml.etree.ElementTree as ET

from billing import einvoice_xml
from letterhead import data as letterhead
from organizations.imprint import details, ensure
from organizations.imprint_generator import _address


def _anschrift(org, extra="c/o Musterfirma GmbH (erfunden)"):
    org.address_extra = extra
    org.street = "Musterweg 1"
    org.postal_code = "12345"
    org.city = "Musterstadt"
    org.save()


def test_impressum_uebernimmt_zusatz_vom_verein(orgs):
    _anschrift(orgs["a"])
    d = details(orgs["a"], ensure(orgs["a"]))
    assert d["address"]["address_extra"] == "c/o Musterfirma GmbH (erfunden)"
    assert _address(d).startswith(f"{d['name']}, c/o Musterfirma GmbH (erfunden), Musterweg 1")


def test_eigene_strasse_im_impressum_ersetzt_den_zusatz(orgs):
    _anschrift(orgs["a"])
    imprint = ensure(orgs["a"])
    imprint.street = "Andere Straße 2"
    imprint.save()
    assert details(orgs["a"], imprint)["address"]["address_extra"] == ""
    imprint.address_extra = "Gebäude B"
    imprint.save()
    assert details(orgs["a"], imprint)["address"]["address_extra"] == "Gebäude B"


def test_briefkopf_zeigt_zusatz_ueber_der_strasse(orgs):
    _anschrift(orgs["a"])
    address = letterhead.letter_data(orgs["a"]).address
    assert address[1:3] == ["c/o Musterfirma GmbH (erfunden)", "Musterweg 1"]


def test_ohne_zusatz_keine_leere_zeile(orgs):
    _anschrift(orgs["a"], extra="")
    address = letterhead.letter_data(orgs["a"]).address
    assert "" not in address
    assert address[1] == "Musterweg 1"


def _party(**extra):
    root = ET.Element("Invoice")
    data = {
        "name": "Verein A",
        "street": "Musterweg 1",
        "postcode": "12345",
        "city": "Musterstadt",
        "country": "DE",
        "email": "info@verein-a.example.org",
        # Verkäuferangaben braucht party(..., seller=True) für cac:Contact
        "contact": "Erika Muster",
        "phone": "0123 456789",
        **extra,
    }
    einvoice_xml.party(root, "AccountingSupplierParty", data, seller=True)
    ns = {"cac": einvoice_xml.NS["cac"], "cbc": einvoice_xml.NS["cbc"]}
    return root.find(".//cac:PostalAddress", ns), ns


def test_e_rechnung_zweite_adresszeile():
    address, ns = _party(address_extra="c/o Musterfirma GmbH (erfunden)")
    names = [child.tag.split("}")[1] for child in address]
    assert names[:3] == ["StreetName", "AdditionalStreetName", "CityName"]
    assert address.find("cbc:AdditionalStreetName", ns).text == "c/o Musterfirma GmbH (erfunden)"


def test_e_rechnung_ohne_zusatz_ohne_element():
    address, ns = _party()
    assert address.find("cbc:AdditionalStreetName", ns) is None
