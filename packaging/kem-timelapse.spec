# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent

# PyInstaller's Qt and OpenCV hooks collect the required frameworks/plugins.  Do not
# collect the whole PySide6 tree: that includes unrelated SQL/QML plugins and makes
# the unsigned local bundle needlessly large.
datas = []
binaries = []
hiddenimports = [
    *collect_submodules("kem_timelapse"),
    *collect_submodules("cv2"),
    *collect_submodules("pydantic"),
    *collect_submodules("PySide6.QtMultimedia"),
]
try:
    hiddenimports.extend(collect_submodules("df"))
except ImportError:
    pass

analysis = Analysis(
    [str(ROOT / "src/kem_timelapse/ui/app.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
    target_arch="arm64",
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    name="Kem Timelapse Studio",
    console=True,
    exclude_binaries=True,
)
bundle_files = COLLECT(
    executable,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    name="Kem Timelapse Studio",
)
app = BUNDLE(
    bundle_files,
    name="Kem Timelapse Studio.app",
    bundle_identifier="com.kem12032024.timelapse",
    icon=None,
)
