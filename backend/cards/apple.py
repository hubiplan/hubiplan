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

from . import passcontent
from .wallet import WalletError

# Schlüssel der festen Texte in pass.json; die Wallet ersetzt sie aus <Sprache>.lproj/pass.strings
KEY = "hubiplan."


def enabled():
    return bool(
        settings.APPLE_WALLET_PASS_TYPE_ID
        and settings.APPLE_WALLET_TEAM_ID
        and settings.APPLE_WALLET_CERTIFICATE_FILE
        and settings.APPLE_WALLET_WWDR_FILE
    )


def _rgb_tuple(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def _field(key: str, label: str, value: str) -> dict:
    return {"key": key, "label": KEY + label, "value": value}


def _payload(card, content) -> dict:
    secondary = [_field("club", "club", content.club)]
    auxiliary = []
    if content.member_type:
        auxiliary.append(_field("member_type", "member_type", content.member_type))
    if content.departments:
        auxiliary.append(_field("departments", "departments", ", ".join(content.departments)))
    if content.federation:
        secondary.append(_field("federation", "federation", content.federation))
    return {
        "formatVersion": 1,
        "passTypeIdentifier": settings.APPLE_WALLET_PASS_TYPE_ID,
        "teamIdentifier": settings.APPLE_WALLET_TEAM_ID,
        "serialNumber": hashlib.sha256(card.url.encode()).hexdigest(),
        "organizationName": content.club,
        "description": KEY + "description",
        "logoText": content.club,
        "backgroundColor": passcontent.rgb(content.background),
        "foregroundColor": passcontent.rgb(content.foreground),
        "labelColor": passcontent.rgb(content.foreground),
        "barcodes": [
            {
                "format": "PKBarcodeFormatQR",
                "message": content.url,
                "messageEncoding": "iso-8859-1",
            }
        ],
        "generic": {
            "primaryFields": [_field("name", "member", content.name)],
            "secondaryFields": secondary,
            "auxiliaryFields": auxiliary,
            "backFields": [
                _field("verification", "verify", KEY + "verify_body_static"),
                _field("url", "verify_page", content.url),
            ],
        },
    }


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _strings(content) -> dict[str, bytes]:
    """pass.strings je Sprache (UTF-16, wie Apple es verlangt)."""
    labels = {key: passcontent.texts(key) for key in passcontent.TEXTS}
    files = {}
    for language in passcontent.LANGUAGES:
        lines = [f'"{KEY}{key}" = "{_escape(values[language])}";' for key, values in labels.items()]
        lines.append(f'"{KEY}departments" = "{_escape(content.department_label[language])}";')
        files[f"{language}.lproj/pass.strings"] = ("\n".join(lines) + "\n").encode("utf-16")
    return files


def _logo(content) -> dict[str, bytes]:
    """Logo der Einheit in den drei Auflösungen (höchstens 160 × 50 Punkte)."""
    if not content.logo:
        return {}
    try:
        with content.logo.open("rb") as handle:
            source = Image.open(handle)
            source.load()
    except (OSError, ValueError):
        return {}
    source = source.convert("RGBA")
    files = {}
    for scale in (1, 2, 3):
        image = source.copy()
        image.thumbnail((160 * scale, 50 * scale))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        suffix = "" if scale == 1 else f"@{scale}x"
        files[f"logo{suffix}.png"] = buffer.getvalue()
    return files


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
        content = passcontent.build(card)
        files = {"pass.json": json.dumps(_payload(card, content), ensure_ascii=False).encode()}
        files.update(_strings(content))
        files.update(_logo(content))
        # Eigenes schlichtes Ausweissymbol in den von Apple vorgesehenen Auflösungen.
        for scale in (1, 2, 3):
            size = 29 * scale
            image = Image.new("RGB", (size, size), _rgb_tuple(content.background))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle(
                (4 * scale, 7 * scale, 25 * scale, 22 * scale),
                radius=2 * scale,
                outline=content.foreground,
                width=scale,
            )
            draw.ellipse((7 * scale, 10 * scale, 12 * scale, 15 * scale), fill=content.foreground)
            draw.line(
                (15 * scale, 11 * scale, 22 * scale, 11 * scale),
                fill=content.foreground,
                width=scale,
            )
            draw.line(
                (15 * scale, 16 * scale, 22 * scale, 16 * scale),
                fill=content.foreground,
                width=scale,
            )
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
