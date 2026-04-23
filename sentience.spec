# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from PyInstaller.building.build_main import Analysis, PYZ, EXE

a = Analysis(
    ['sentience_app.py'],
    pathex=[],
    binaries=[],
    datas=collect_all('PySide6')[1] + [('ui', 'ui')],
    hiddenimports=['anthropic', 'openai', 'groq', 'flask', 'flask_cors', 'paramiko', 'pytesseract', 'whisper', 'PyPDF2', 'docx', 'openpyxl', 'reportlab', 'lark', 'duckduckgo_search'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
)
pyz = PYZ(a.pyz, cipher=None)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Sentience', debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name='Sentience')
