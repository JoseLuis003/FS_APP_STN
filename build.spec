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
    # `upx=False`: UPX comprime/empaqueta el .exe -- lo que también hace
    # que se parezca, a nivel de bytes, a como muchos malware empaquetan
    # el suyo para evadir firmas. Es una de las causas más comunes de
    # falso positivo en antivirus para binarios de PyInstaller; se
    # desactiva a propósito, aunque el .exe quede más pesado.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # sin consola, como una app de escritorio normal
    icon=None,       # ej: 'assets/icon.ico'
    uac_admin=True,  # exige privilegios de administrador (UAC) al abrir el .exe
    # Metadatos de versión de Windows (CompanyName, FileDescription,
    # ProductName, etc. -- ver version_info.txt) para que el .exe se vea
    # como software real y no una app "en blanco" sin publisher/versión,
    # otra señal que revisan antivirus/SmartScreen. No reemplaza la firma
    # digital (ver README, sección "Falsos positivos de antivirus").
    version='version_info.txt',
)
