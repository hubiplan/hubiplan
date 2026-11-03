import base64
import datetime
import hashlib
import io
import json
import zipfile
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs7, pkcs12
from cryptography.x509.oid import NameOID
from django.db import connection

from cards import apple, services, wallet
from cards.models import MemberCard
from core.tenancy import tenant_context
from members.models import MembershipPeriod
from portal.models import PortalAccess

from .test_cards import club as club
from .test_cards import erika as erika
from .test_cards import zug as zug

pytestmark = pytest.mark.django_db


def test_old_code_can_insert_card_without_wallet_column(club, erika):
    # Beim Code-Rollback bleibt die Migration bestehen: ältere INSERTs kennen die Spalte nicht.
    with tenant_context(club.pk), connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO cards_membercard "
            "(organization_id, membership_id, token, created_at, issued_at) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            [club.pk, erika.pk, "old-code-card"],
        )
        assert MemberCard.objects.get(membership=erika).wallet_passes == {}


@pytest.fixture
def google(settings, tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    credentials = tmp_path / "google.json"
    credentials.write_text(
        json.dumps(
            {
                "client_email": "wallet@example.iam.gserviceaccount.com",
                "private_key": key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ).decode(),
            }
        )
    )
    settings.GOOGLE_WALLET_ISSUER_ID = "123456"
    settings.GOOGLE_WALLET_CREDENTIALS_FILE = str(credentials)
    settings.FRONTEND_URL = "https://verein.example"
    return key


@pytest.fixture
def own_access(club, erika, api, board_a):
    api(board_a).post(f"/api/orgs/{club.pk}/members/{erika.pk}/access/")
    access = PortalAccess.objects.get(membership=erika)
    api(access.user).get(f"/api/portal/{access.pk}/card/")
    return access


def test_issue_only_after_post_and_signature(google, own_access, api):
    access = own_access
    client = api(access.user)
    endpoint = f"/api/portal/{access.pk}/card/wallet/google/"
    with patch.object(wallet.GoogleWallet, "request", return_value={}) as remote:
        assert client.get(endpoint).status_code == 404
        assert remote.call_count == 0
        response = client.post(endpoint, {}, content_type="application/json")
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        encoded = response.json()["url"].split("/save/")[1]
        header, payload, signature = encoded.split(".")
        google.public_key().verify(
            base64.urlsafe_b64decode(signature + "=="),
            (header + "." + payload).encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        assert claims["typ"] == "savetowallet"
        assert claims["origins"] == ["verein.example"]
        assert list(claims["payload"]["genericObjects"][0]) == ["id"]
        issued = remote.call_args_list[1].args[2]
        assert issued["header"]["defaultValue"]["value"] == "Erika Muster"
        assert issued["barcode"]["value"].startswith("https://verein.example/ausweis/")
        assert "photo" not in json.dumps(issued)


def test_disabled_foreign_revoked_inactive(google, own_access, api, board_a, settings):
    access = own_access
    client = api(access.user)
    endpoint = f"/api/portal/{access.pk}/card/wallet/google/"
    with patch.object(wallet.GoogleWallet, "request") as remote:
        assert api(board_a).post(endpoint).status_code == 404
        assert client.post(endpoint.replace("google", "apple")).status_code == 404
        with tenant_context(access.organization_id):
            card = MemberCard.objects.get(membership_id=access.membership_id)
            services.renew(card)
            from django.utils import timezone

            card.revoked_at = timezone.now()
            card.save()
        assert client.post(endpoint).status_code == 404
        settings.GOOGLE_WALLET_ISSUER_ID = ""
        assert client.post(endpoint).status_code == 404
        remote.assert_not_called()


def test_renewal_does_not_reactivate_old_wallet(google, own_access):
    with tenant_context(own_access.organization_id):
        card = MemberCard.objects.get(membership_id=own_access.membership_id)
        with patch.object(wallet.GoogleWallet, "request", return_value={}) as remote:
            wallet.issue_google(card.pk)
            old_id = remote.call_args_list[1].args[2]["id"]
            card.refresh_from_db()
            services.renew(card)
            remote.reset_mock()
            wallet.issue_google(card.pk)
            old_updates = [
                call.args[2]
                for call in remote.call_args_list
                if call.args[1] == "genericObject/" + old_id
            ]
            assert old_updates == [
                {
                    "state": "INACTIVE",
                    "header": {"defaultValue": {"language": "de", "value": "Ungültiger Ausweis"}},
                }
            ]
            remote.reset_mock()
            wallet.sync_google(card.pk)
            remote.assert_not_called()


def test_upstream_failure_keeps_reference_for_retry(google, own_access, api):
    access = own_access
    with patch.object(wallet.GoogleWallet, "request", side_effect=wallet.WalletError("secret")):
        response = api(access.user).post(f"/api/portal/{access.pk}/card/wallet/google/")
        assert response.status_code == 503
        assert b"secret" not in response.content
    with tenant_context(access.organization_id):
        assert MemberCard.objects.get(membership_id=access.membership_id).wallet_passes["google"]


def test_membership_end_marks_existing_pass_inactive(google, own_access):
    from django.utils import timezone

    with tenant_context(own_access.organization_id):
        card = MemberCard.objects.get(membership_id=own_access.membership_id)
        with patch.object(wallet.GoogleWallet, "request", return_value={}) as remote:
            wallet.issue_google(card.pk)
            MembershipPeriod.objects.filter(membership=card.membership).update(
                exit_date=timezone.localdate() - datetime.timedelta(days=1)
            )
            remote.reset_mock()
            wallet.sync_google(card.pk)
            assert remote.call_args.args[2]["state"] == "INACTIVE"
            with pytest.raises(wallet.WalletError):
                wallet.issue_google(card.pk)


def test_apple_download_package_and_access(own_access, api, board_a, settings, tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Test Pass"),
            x509.NameAttribute(NameOID.USER_ID, "pass.example.membership"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "TESTTEAM"),
        ]
    )
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_file = tmp_path / "apple.p12"
    cert_file.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"pass", key, certificate, None, serialization.NoEncryption()
        )
    )
    wwdr_file = tmp_path / "wwdr.pem"
    wwdr_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    settings.APPLE_WALLET_PASS_TYPE_ID = "pass.example.membership"
    settings.APPLE_WALLET_TEAM_ID = "TESTTEAM"
    settings.APPLE_WALLET_CERTIFICATE_FILE = str(cert_file)
    settings.APPLE_WALLET_WWDR_FILE = str(wwdr_file)
    access = own_access
    url = f"/api/portal/{access.pk}/card/wallet/apple/"
    assert api(board_a).get(url).status_code == 404
    response = api(access.user).get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/vnd.apple.pkpass"
    assert response["Cache-Control"] == "private, no-store"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for name, digest in manifest.items():
            assert hashlib.sha1(archive.read(name)).hexdigest() == digest  # noqa: S324
        payload = json.loads(archive.read("pass.json"))
        assert payload["passTypeIdentifier"] == "pass.example.membership"
        assert payload["generic"]["primaryFields"][0]["value"] == "Erika Muster"
        assert "webServiceURL" not in payload
        certificates = pkcs7.load_der_pkcs7_certificates(archive.read("signature"))
        assert certificate.fingerprint(hashes.SHA256()) in [
            cert.fingerprint(hashes.SHA256()) for cert in certificates
        ]
    settings.APPLE_WALLET_CERTIFICATE_FILE = ""
    assert not apple.enabled()
    assert api(access.user).get(url).status_code == 404
    settings.APPLE_WALLET_CERTIFICATE_FILE = str(cert_file)
    settings.APPLE_WALLET_TEAM_ID = "WRONGTEAM"
    assert api(access.user).get(url).status_code == 503
