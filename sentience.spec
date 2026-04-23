# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas_pyside = collect_data_files('PySide6')
datas_shiboken = collect_data_files('shiboken6')

a = Analysis(
    ['sentience.py'],
    pathex=[],
    binaries=[],
    datas=datas_pyside + datas_shiboken + [
        ('ui', 'ui'),
    ],
    hiddenimports=[
        'anthropic',
        'openai', 
        'groq',
        'dotenv',
        'lz4', 'lz4.frame',
        'yaml',
        'playwright', 'playwright.sync_api',
        'flask', 'flask_cors', 'werkzeug',
        'sqlite3', 'json', 'uuid', 'hashlib',
        'urllib', 'urllib.request', 'urllib.error',
        'http', 'http.client',
        'concurrent', 'concurrent.futures',
        'threading', 'multiprocessing',
    ],
    hookspath=[],
    hooksconfig={},
    key=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zir_data, cipher=block_cipher, hook_menu=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Sentience',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zip SafeFileCollection(a.datas, a.zipSafe),
    strip=False,
    upx=True,
    name='Sentience',
)
