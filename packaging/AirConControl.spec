# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


PACKAGING_DIR = Path(SPECPATH).resolve()
PROJECT_DIR = PACKAGING_DIR.parent
WEB_DIR = PROJECT_DIR / "react-webview-app"

hiddenimports = ["keyring.backends.Windows"]
def include_runtime_module(name):
    return ".test" not in name and not name.endswith(".cli")


for package in ("midea_beautiful", "midealocal", "msmart"):
    hiddenimports.extend(collect_submodules(package, filter=include_runtime_module))

a = Analysis(
    [str(WEB_DIR / "backend.py")],
    pathex=[str(PROJECT_DIR), str(WEB_DIR)],
    binaries=[],
    datas=[
        (str(WEB_DIR / "dist"), "dist"),
        (str(PACKAGING_DIR / "DISTRIBUTION_README.txt"), "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AirConControl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PACKAGING_DIR / "AirConControl.ico"),
    version=str(PACKAGING_DIR / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AirConControl",
)
