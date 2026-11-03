"""Filename compatibility of actual startup/retention paths; local test image only."""

import os
import re
import subprocess
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        binary = work / "bin"
        binary.mkdir()
        for name, content in {
            "backup.sh": 'touch "$CALLED"',
            "sleep": "exit 77",
        }.items():
            target = binary / name
            target.write_text("#!/bin/sh\n" + content + "\n")
            target.chmod(0o755)
        root = Path("/backups")
        root.mkdir(exist_ok=True)
        called = work / "unexpected-backup"
        # BusyBox ash may run sleep as an internal applet despite a PATH shim.
        # Override only this command in the isolated source copy; production
        # startup-selection and status-writing control flow remain unchanged.
        timer = work / "run-test.sh"
        timer.write_text(
            Path("/usr/local/bin/run.sh")
            .read_text()
            .replace("set -eu", "sleep() { exit 77; }\nset -eu", 1)
        )
        timer.chmod(0o755)
        for stamp in ("2020-01-02_0304", "2020-01-02_030405_abcdef012345"):
            for extension in ("enc", "age"):
                candidate = root / f"db_{stamp}.sql.gz.{extension}"
                candidate.touch()
                result = subprocess.run(
                    ["/bin/sh", str(timer)],
                    env={
                        **os.environ,
                        "PATH": f"{binary}:{os.environ['PATH']}",
                        "BACKUP_PUBLIC_KEY": "synthetic-nonempty-only",
                        "BACKUP_HMAC_KEY": "synthetic-nonempty-only",
                        "BACKUP_TIME": "99:99",
                        "CALLED": str(called),
                    },
                    check=False,
                    capture_output=True,
                    timeout=3,
                )
                assert result.returncode == 77 and not called.exists(), result.stderr
                candidate.unlink()
        retention = work / "retention"
        retention.mkdir()
        # Run the actual shipped retention fragment in an isolated test directory.
        source = Path("/usr/local/bin/backup.sh").read_text()
        command = re.search(
            r'find "\$DIR" -maxdepth 1.*? -delete', source, re.DOTALL
        ).group()
        expired = []
        for stamp in ("2000-01-02_0304", "2000-01-02_030405_abcdef012345"):
            for filename in (
                f"db_{stamp}.sql.gz.age",
                f"db_{stamp}.sql.gz.age.hmac",
                f"files_{stamp}.tar.gz.enc",
                f"datenschluessel_{stamp}.age",
                f"datenschluessel_{stamp}.sha256",
                f"datenschluessel_{stamp}.sha256.hmac",
            ):
                path = retention / filename
                path.touch()
                os.utime(path, (946684800, 946684800))
                expired.append(path)
        alias = retention / "datenschluessel.age"
        alias.touch()
        os.utime(alias, (946684800, 946684800))
        fresh = retention / "db_2020-01-02_030405_123456abcdef.sql.gz.age"
        fresh.touch()  # retention uses mtime, not a date parsed from the filename
        subprocess.run(
            ["/bin/sh", "-c", command],
            env={**os.environ, "DIR": str(retention), "KEEP_DAYS": "30"},
            check=True,
        )
        assert all(not path.exists() for path in expired)
        assert alias.exists() and fresh.exists()
    print("Backup: old/new names, startup detection and per-set retention checked")


if __name__ == "__main__":
    main()
