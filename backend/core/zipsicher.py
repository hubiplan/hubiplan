"""Fehler beim Lesen fremder ZIP-Dateien an einer Stelle benannt.

``zipfile`` meldet beschädigte oder bösartige Archive nicht nur mit ``BadZipFile``: Je nach
Stelle kommen auch ``zlib.error``, ``EOFError``, ``ValueError`` (auch ``UnicodeDecodeError``
bei Dateinamen), ``NotImplementedError`` (unbekanntes Packverfahren, zu neue ZIP-Fassung),
``RuntimeError`` (Kennwort) oder ``OSError``. Wer ein fremdes Archiv öffnet oder daraus
liest, fängt ``ZIP_FEHLER`` und lehnt mit seiner eigenen Meldung ab (Härtung C3,
``tests/test_zufall_dateileser.py``).
"""

import lzma
import struct
import zipfile
import zlib

ZIP_FEHLER = (
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    zlib.error,
    lzma.LZMAError,
    struct.error,
    EOFError,
    ValueError,
    NotImplementedError,
    RuntimeError,
    OSError,
)
