"""Signierter Apple-Wallet-Dateiexport, ohne Geräte-/Pushregistrierung."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7, pkcs12
from cryptography.x509.oid import NameOID
from django.conf import settings
from PIL import Image, ImageDraw

from .wallet import WalletError


def enabled():
    return bool(
        settings.APPLE_WALLET_PASS_TYPE_ID
        and settings.APPLE_WALLET_TEAM_ID
        and settings.APPLE_WALLET_CERTIFICATE_FILE
        and settings.APPLE_WALLET_WWDR_FILE
    )


def render_pass(card):
    if not enabled():
        raise WalletError("Apple Wallet ist nicht eingerichtet.")
    try:
        password = settings.APPLE_WALLET_CERTIFICATE_PASSWORD
        key, certificate, chain = pkcs12.load_key_and_certificates(
            Path(settings.APPLE_WALLET_CERTIFICATE_FILE).read_bytes(),
            password.encode() if password else None,
        )
        intermediate = x509.load_pem_x509_certificate(
            Path(settings.APPLE_WALLET_WWDR_FILE).read_bytes()
        )
        if key is None or certificate is None:
            raise ValueError("missing signing identity")
        identifiers = certificate.subject.get_attributes_for_oid(NameOID.USER_ID)
        teams = certificate.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)
        now = datetime.now(UTC)
        if (
            not identifiers
            or identifiers[0].value != settings.APPLE_WALLET_PASS_TYPE_ID
            or not teams
            or teams[0].value != settings.APPLE_WALLET_TEAM_ID
            or not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc
        ):
            raise ValueError("certificate identity or validity mismatch")
        person = card.membership.person
        payload = {
            "formatVersion": 1,
            "passTypeIdentifier": settings.APPLE_WALLET_PASS_TYPE_ID,
            "teamIdentifier": settings.APPLE_WALLET_TEAM_ID,
            "serialNumber": hashlib.sha256(card.url.encode()).hexdigest(),
            "organizationName": card.organization.name,
            "description": "Mitgliedsausweis",
            "logoText": card.organization.name,
            "backgroundColor": "rgb(25, 55, 90)",
            "foregroundColor": "rgb(255, 255, 255)",
            "labelColor": "rgb(230, 235, 240)",
            "barcodes": [
                {
                    "format": "PKBarcodeFormatQR",
                    "message": card.url,
                    "messageEncoding": "iso-8859-1",
                }
            ],
            "generic": {
                "primaryFields": [
                    {
                        "key": "name",
                        "label": "MITGLIED",
                        "value": f"{person.first_name} {person.last_name}".strip(),
                    }
                ],
                "secondaryFields": [
                    {"key": "club", "label": "VEREIN", "value": card.organization.name}
                ],
                "backFields": [
                    {
                        "key": "verification",
                        "label": "Gültigkeit prüfen",
                        "value": "Bitte den QR-Code scannen. Die aktuelle Gültigkeit "
                        "wird online geprüft. Dieser Pass wird nicht "
                        "automatisch aktualisiert.",
                    },
                    {"key": "url", "label": "Prüfseite", "value": card.url},
                ],
            },
        }
        files = {"pass.json": json.dumps(payload, ensure_ascii=False).encode()}
        # Eigenes schlichtes Ausweissymbol in den von Apple vorgesehenen Auflösungen.
        for scale in (1, 2, 3):
            size = 29 * scale
            image = Image.new("RGB", (size, size), (25, 55, 90))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle(
                (4 * scale, 7 * scale, 25 * scale, 22 * scale),
                radius=2 * scale,
                outline="white",
                width=scale,
            )
            draw.ellipse((7 * scale, 10 * scale, 12 * scale, 15 * scale), fill="white")
            draw.line((15 * scale, 11 * scale, 22 * scale, 11 * scale), fill="white", width=scale)
            draw.line((15 * scale, 16 * scale, 22 * scale, 16 * scale), fill="white", width=scale)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            suffix = "" if scale == 1 else f"@{scale}x"
            files[f"icon{suffix}.png"] = buffer.getvalue()
        manifest = json.dumps(
            {
                name: hashlib.sha1(data).hexdigest()  # noqa: S324 -- Apple-Passformat verlangt SHA-1
                for name, data in files.items()
            }
        ).encode()
        signer = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(manifest)
            .add_signer(certificate, key, hashes.SHA256())
            .add_certificate(intermediate)
        )
        for extra in chain or []:
            if extra.fingerprint(hashes.SHA256()) != intermediate.fingerprint(hashes.SHA256()):
                signer = signer.add_certificate(extra)
        files["manifest.json"] = manifest
        files["signature"] = signer.sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return output.getvalue()
    except (OSError, ValueError, TypeError) as exc:
        raise WalletError("Apple-Wallet-Zertifikate sind nicht verfügbar.") from exc
