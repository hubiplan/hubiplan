#!/usr/bin/env python3
"""Check actual gzip/tar member bytes against a SHA256 manifest, without extraction.

--copy forwards the original compressed stream to encryption. A nonzero status
must abort the complete pipeline; no verified backup may be published on failure.
Memory is bounded by the manifest and a single 1 MiB data chunk.
"""

import argparse
import gzip
import hashlib
import re
import sys
import tarfile


def path(name):
    if name in (".", "./"):
        return "."
    name = name.removeprefix("./").removesuffix("/")
    if (
        not name
        or name.startswith("/")
        or any(p in ("", ".", "..") for p in name.split("/"))
    ):
        raise ValueError("unsafe archive path")
    if any(ord(c) < 32 for c in name) or "\\" in name:
        raise ValueError("unsupported filename")
    return name


class Stream:
    def __init__(self, copy):
        self.copy = copy

    def read(self, size=-1):
        data = sys.stdin.buffer.read(size)
        if self.copy:
            sys.stdout.buffer.write(data)
        return data


def check(manifest, copy=False):
    expected = {}
    with open(manifest, encoding="utf-8") as source:
        for line in source:
            if not re.fullmatch(r"[0-9a-f]{64}  [^\n]+\n", line):
                raise ValueError("invalid checksum manifest")
            name = path(line[66:-1])
            if name in expected:
                raise ValueError("duplicate manifest path")
            expected[name] = line[:64]
    seen = set()
    stream = Stream(copy)
    with gzip.GzipFile(fileobj=stream) as compressed:
        with tarfile.open(fileobj=compressed, mode="r|") as archive:
            for member in archive:
                name = path(member.name)
                if member.isdir():
                    continue
                if not member.isfile() or name in seen or name not in expected:
                    raise ValueError("unexpected, duplicate or linked archive member")
                digest = hashlib.sha256()
                with archive.extractfile(member) as data:
                    while chunk := data.read(1024 * 1024):
                        digest.update(chunk)
                if digest.hexdigest() != expected[name]:
                    raise ValueError("archive content checksum mismatch")
                seen.add(name)
            # Tar readers normally stop at the first zero header. Reject hidden
            # members/data after that terminator, including buffered read-ahead.
            while trailing := archive.fileobj.read(1024 * 1024):
                if any(trailing):
                    raise ValueError("non-padding data after archive terminator")
        # Consume gzip trailer as well (CRC/truncation check), including padding.
        while compressed.read(1024 * 1024):
            pass
    if seen != set(expected):
        raise ValueError("manifest member missing from archive")
    if copy:
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args()
    try:
        check(args.manifest, args.copy)
    except (ValueError, OSError, EOFError, tarfile.TarError) as error:
        print(f"Archive verification failed: {error}", file=sys.stderr)
        sys.exit(1)
