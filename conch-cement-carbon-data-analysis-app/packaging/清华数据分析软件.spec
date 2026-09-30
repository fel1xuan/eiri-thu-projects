# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


APP_NAME = "清华数据分析软件"
APP_VERSION = "1.0.0"
BUNDLE_ID = "com.felix.tsinghua-data-analysis"

PROJECT_ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(PROJECT_ROOT / "assets" / "logo.png"), "assets"),
    (str(PROJECT_ROOT / "assets" / "app_icon.icns"), "assets"),
    (str(PROJECT_ROOT / "assets" / "mindmaps" / "physical_data_path.png"), "assets/mindmaps"),
    (str(PROJECT_ROOT / "assets" / "mindmaps" / "code_data_analysis_flow.png"), "assets/mindmaps"),
    (str(PROJECT_ROOT / "config" / "default_config.json"), "config"),
    (str(PROJECT_ROOT / "config" / "version.json"), "config"),
]
datas += collect_data_files("matplotlib")

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "openpyxl",
    "xlrd",
]
hiddenimports += collect_submodules("pandas._libs")

excludes = [
    "streamlit",
    "tests",
    "pytest",
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(PROJECT_ROOT / "assets" / "app_icon.icns"),
    bundle_identifier=BUNDLE_ID,
    version=APP_VERSION,
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": "True",
    },
)
