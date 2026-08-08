# -*- mode: python ; coding: utf-8 -*-
# Generar el .exe: correr `pyinstaller build.spec` en una máquina Windows
# (con Python y las dependencias de requirements.txt instaladas).

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),  # se copian junto al .exe la primera vez
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FS_APP_STN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # sin consola, como una app de escritorio normal
    icon=None,       # ej: 'assets/icon.ico'
    uac_admin=True,  # exige privilegios de administrador (UAC) al abrir el .exe
)
