# aterminal.spec

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

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
        'numpy',       # Added numpy as it's required by pandas/folium
        'folium',
        'openpyxl',
        'branca',      # Required by folium
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # EXCLUDE UNUSED MODULES TO REDUCE SIZE
    excludes=[
        'QtQuick', 'QtQml', 'QtNetwork', 'pytest', 'matplotlib',
        'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtNetwork', 'PySide6.QtBluetooth',
        'tk', 'tcl', 'tkinter', 'ipython', 'jupyter', 'sphinx', 'docutils', 'jedi', 'PIL',
        'tornado', 'cryptography', 'nbconvert', 'nbformat', 'notebook'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Manually exclude any PySide6 modules that aren't needed to reduce size
# This helps with the "exclude_binaries" approach later
a.binaries = [x for x in a.binaries if not x[0].startswith('PySide6.Qt') or 
               any(needed in x[0] for needed in ['Core', 'Gui', 'Widgets', 'PrintSupport', 'WebEngine'])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Create a single-file EXE to avoid directory structure problems
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,       # Include binaries in the EXE
    a.zipfiles,       # Include zipfiles in the EXE
    a.datas,          # Include data files in the EXE
    [],
    name='aterminal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # USE UPX FOR COMPRESSION
    upx=True,
    # Exclude problematic files from UPX compression
    upx_exclude=['vcruntime140.dll', 'msvcp140.dll', 'python*.dll'],
    runtime_tmpdir=None,
    console=False,    # Set to True for debugging, False for production
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Optional: Add an icon file here
    # icon='assets/icon.ico'
)