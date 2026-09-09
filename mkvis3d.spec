# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

root = Path.cwd()

# Detect appropriate icon for host OS
if sys.platform == "win32":
    app_icon = str(root / "assets/icons/vaila.ico")
elif sys.platform == "darwin":
    app_icon = str(root / "assets/icons/vaila.icns")
else:
    app_icon = str(root / "assets/icons/vaila.png")

datas = [
    (str(root / "openbiomech/viewer.html"), "openbiomech"),
    (str(root / "openbiomech/viewer.js"), "openbiomech"),
    (str(root / "skeleton_templates"), "skeleton_templates"),
    (str(root / "data"), "data"),
    (str(root / "assets/icons"), "assets/icons"),
]

hiddenimports = [
    "openbiomech",
    "openbiomech.cli",
    "openbiomech.viewer",
    "openbiomech.trial_io",
    "openbiomech.c3d_io",
    "openbiomech.csv_io",
    "openbiomech.analysis_io",
    "openbiomech.marker_trial",
    "openbiomech.biomech_math",
    "openbiomech.biomech_math.lcs",
    "openbiomech.biomech_math.filtering",
    "openbiomech.model",
    "openbiomech.inverse_dynamics",
    "ezc3d",
    "numpy",
    "scipy",
    "scipy.interpolate",
    "scipy.spatial.transform",
    "scipy.signal",
    "pandas",
]

a = Analysis(
    ["mkvis3d.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="mkvis3d",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="mkvis3d.app",
        icon=str(root / "assets/icons/vaila.icns"),
        bundle_identifier="br.usp.openbiomech.mkvis3d",
    )
