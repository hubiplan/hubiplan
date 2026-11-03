"""Synthetic archive corruption regressions, run only by scripts/test.sh."""

import gzip
import hashlib
import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


def archive(members):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w:gz") as output:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(data) if kind == tarfile.REGTYPE else 0
            if kind == tarfile.SYMTYPE:
                info.linkname = "../../outside"
            output.addfile(info, io.BytesIO(data) if info.isfile() else None)
    return result.getvalue()


class ArchiveTest(unittest.TestCase):
    def check(self, stream, manifest=None, copy=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest"
            path.write_text(
                manifest
                or hashlib.sha256(b"original").hexdigest() + "  ./private/file\n"
            )
            return subprocess.run(
                ["archive-check.py", str(path), *(["--copy"] if copy else [])],
                check=False,
                input=stream,
                capture_output=True,
            )

    def test_positive_and_copy(self):
        stream = archive([("./private/file", b"original", tarfile.REGTYPE)])
        result = self.check(stream, copy=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, stream)

    def test_actual_file_corruption_is_not_just_name_check(self):
        stream = archive([("./private/file", b"modified", tarfile.REGTYPE)])
        self.assertNotEqual(self.check(stream).returncode, 0)

    def test_missing_extra_duplicate_link_and_traversal(self):
        original = ("./private/file", b"original", tarfile.REGTYPE)
        for members in (
            [],
            [original, original],
            [original, ("extra", b"x", tarfile.REGTYPE)],
            [("../private/file", b"original", tarfile.REGTYPE)],
            [("./private/file", b"", tarfile.SYMTYPE)],
        ):
            with self.subTest(members=members):
                self.assertNotEqual(self.check(archive(members)).returncode, 0)

    def test_gzip_crc_and_truncation(self):
        stream = archive([("./private/file", b"original", tarfile.REGTYPE)])
        self.assertEqual(gzip.decompress(stream)[:2], b"./")
        for broken in (stream[:-4], stream[:-8] + b"xxxxxxxx"):
            self.assertNotEqual(self.check(broken).returncode, 0)

    def test_hidden_data_after_tar_terminator(self):
        stream = archive([("./private/file", b"original", tarfile.REGTYPE)])
        hidden = gzip.compress(gzip.decompress(stream) + b"hidden content")
        self.assertNotEqual(self.check(hidden).returncode, 0)


if __name__ == "__main__":
    unittest.main()
