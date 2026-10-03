"""Prepare app/build-template: Flet's own build template, patched for scheduled notifications.

flet-android-notifications wraps flutter_local_notifications, which needs its
broadcast receivers in AndroidManifest.xml and Gradle core-library desugaring.
Flet's stock template has neither and is re-rendered on every build, so the
build uses this patched copy instead ([tool.flet.template] in pyproject.toml).

    uv run python scripts/notifications_template.py      # from app/, before `flet build apk`

Run it again after upgrading Flet (and `flet clean`).
"""

from __future__ import annotations

import io
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

import flet.version
from flet_android_notifications.patcher import patch_gradle_file, patch_manifest_file

URL = "https://github.com/flet-dev/flet/releases/download/v{version}/flet-build-template.zip"
OUT = Path(__file__).resolve().parents[1] / "build-template"
ANDROID = "{{cookiecutter.out_dir}}/android/app"


def main() -> None:
    version = flet.version.flet_version
    with urllib.request.urlopen(URL.format(version=version), timeout=60) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))

    shutil.rmtree(OUT, ignore_errors=True)
    for name in archive.namelist():
        if not name.startswith("build/") or name.endswith("/"):
            continue
        target = OUT / name.removeprefix("build/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))

    manifest = OUT / ANDROID / "src/main/AndroidManifest.xml"
    patch_manifest_file(manifest)
    # Reminders need the receivers only; a foreground service would need its own permission and a Play declaration.
    text = manifest.read_text(encoding="utf-8")
    text = re.sub(
        r"\s*<service android:name=\"com\.dexterous\.flutterlocalnotifications\.ForegroundService\".*?/>", "", text, flags=re.S
    )
    manifest.write_text(text, encoding="utf-8")
    patch_gradle_file(OUT / ANDROID / "build.gradle.kts")
    print(f"Flet {version} build template, patched for scheduled notifications, in {OUT}")


if __name__ == "__main__":
    main()
