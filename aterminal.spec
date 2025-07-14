# TeltonikaToolkit.spec

# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.json', '.'),
    ],
    hiddenimports=[
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtPrintSupport',
        'pandas',
        'folium',
        'openpyxl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # EXCLUDE UNUSED MODULES TO REDUCE SIZE
    excludes=[
        'QtQuick', 'QtQml', 'QtNetwork', 'pytest', 'numpy', 'matplotlib',
        'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtNetwork', 'PySide6.QtBluetooth'
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TeltonikaToolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # USE UPX FOR COMPRESSION
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Optional: Add an icon file here
    # icon='assets/icon.ico'
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TeltonikaToolkit',
)