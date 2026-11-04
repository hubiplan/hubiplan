"""Beim Image-Bau offizielle Prüfarbeitsmittel mit SHA-256 installieren."""

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ASSETS = [
    (
        "https://github.com/itplr-kosit/validator/releases/download/v1.6.3/validator-1.6.3-standalone.jar",
        "799e64befca97d4080e03608c80b85dd5a5ecc5f4ae4f35d1116ec2855b9a7c9",
        "validator.jar",
    ),
    (
        "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/v2026-08-31/xrechnung-3.0.2-validator-configuration-2026-08-31.zip",
        "2530cd107c414511c5d0462ec10f886910395abfca820db82e83d70bf01221a8",
        "config.zip",
    ),
]


def install(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for url, expected, name in ASSETS:
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - feste HTTPS-URLs
            data = response.read(60 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("Prüfsumme des KoSIT-Downloads stimmt nicht.")
        if name.endswith(".jar"):
            (destination / name).write_bytes(data)
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if (
                        not (destination / member.filename)
                        .resolve()
                        .is_relative_to(destination.resolve())
                    ):
                        raise RuntimeError("Unzulässiger Pfad im Regelpaket.")
                archive.extractall(destination)


if __name__ == "__main__":
    install(Path(sys.argv[1]))
