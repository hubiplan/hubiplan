"""Install the pinned official veraPDF CLI; invoices are validated locally."""

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

VERSION = "1.30.3"
URL = f"https://software.verapdf.org/releases/1.30/verapdf-greenfield-{VERSION}-installer.zip"
SHA256 = "b512bf24945503a33fc10738ecffc1f2dccaaf8593a448e94ee9ac86a9559a59"


def install():
    with urlopen(URL, timeout=60) as response:
        data = response.read(50 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("veraPDF archive checksum mismatch")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with ZipFile(io.BytesIO(data)) as archive:
            installer = archive.read(
                f"verapdf-greenfield-{VERSION}/verapdf-izpack-installer-{VERSION}.jar"
            )
        (root / "installer.jar").write_bytes(installer)
        (root / "install.xml").write_text("""<AutomatedInstallation langpack="eng">
<com.izforge.izpack.panels.htmlhello.HTMLHelloPanel id="welcome"/>
<com.izforge.izpack.panels.target.TargetPanel id="install_dir">
<installpath>/opt/verapdf</installpath>
</com.izforge.izpack.panels.target.TargetPanel>
<com.izforge.izpack.panels.packs.PacksPanel id="sdk_pack_select">
<pack index="0" name="veraPDF GUI" selected="false"/>
<pack index="1" name="veraPDF CLI" selected="true"/>
<pack index="2" name="veraPDF Documentation" selected="false"/>
<pack index="3" name="veraPDF Sample Plugins" selected="false"/>
</com.izforge.izpack.panels.packs.PacksPanel>
<com.izforge.izpack.panels.install.InstallPanel id="install"/>
<com.izforge.izpack.panels.finish.FinishPanel id="finish"/>
</AutomatedInstallation>""")
        subprocess.run(  # noqa: S603 -- fixed installer, verified archive digest
            [
                shutil.which("java") or "/usr/bin/java",
                "-jar",
                str(root / "installer.jar"),
                str(root / "install.xml"),
            ],
            check=True,
            timeout=120,
        )


if __name__ == "__main__":
    install()
