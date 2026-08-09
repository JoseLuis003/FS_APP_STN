# -*- mode: python ; coding: utf-8 -*-
# Generar el .exe: correr `pyinstaller build.spec` en una máquina Windows
# (con Python y las dependencias de requirements.txt instaladas).

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),  # se copian junto al .exe la primera vez
        ('assets', 'assets'),  # iconos (checkmark del checkbox, etc.) empaquetados dentro del .exe
        ('scripts', 'scripts'),  # scripts de PowerShell (unión al dominio) empaquetados dentro del .exe
    ],
    # `win32com.client` (pywin32, usado en app/shortcuts.py para crear los
    # accesos directos de Shares) normalmente lo detecta solo PyInstaller
    # gracias a los hooks de pyinstaller-hooks-contrib -- si el .exe
    # generado falla al crear un acceso directo con un error de import,
    # agregar aquí "win32com", "win32com.client" y "win32timezone".
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
