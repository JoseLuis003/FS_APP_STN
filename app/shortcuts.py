"""Creación de accesos directos (.lnk) en el escritorio público.

Cuando termina de aplicarse la configuración de Shares (ver
`app/shares_config_apply.py` y `LtpCssWindow._run_shares_configuration()`),
hay que dejar 2 accesos directos en `C:\\Users\\Public\\Desktop` -- ahí (y
no en el escritorio del usuario que inició sesión) para que se vean sin
importar con qué cuenta se entre al equipo: uno para `LTPGUI32.exe` ("LTP
SHARES") y otro para `LTPHPS32.exe` ("LiteGUI").

Es el equivalente en Python del código VB.NET que ya existía (usaba
`WScript.Shell` vía COM, con `CreateObject`); acá se hace lo mismo con
`pywin32` (`win32com.client.Dispatch("WScript.Shell")`, el mismo objeto
COM, solo que invocado desde Python en vez de VB.NET).

El valor de CIUDAD se arma en los argumentos ya resuelto (viene del campo
CIUDAD del panel), pero "%COMPUTERNAME%" se deja tal cual, como texto
literal -- NO se reemplaza por el nombre real del equipo. Así lo hacía
también el original en VB.NET (esos "%COMPUTERNAME%" quedaban como texto
fijo dentro del string de Arguments, sin ninguna expansión de VB.NET de por
medio): es LTPGUI32.exe / LTPHPS32.exe quien expande esa variable de
entorno al arrancar, no el acceso directo ni quien lo crea.
"""
from __future__ import annotations

import shutil
from pathlib import Path

# Carpeta del escritorio público -- visible para cualquier usuario del
# equipo, sin importar con qué cuenta se inició sesión (a diferencia de
# `objShell.SpecialFolders("Desktop")` en el original, que apunta al
# escritorio del usuario actual; los accesos directos en sí se crean
# siempre en Public Desktop, igual que hacía el VB.NET original).
PUBLIC_DESKTOP = Path(r"C:\Users\Public\Desktop")

# Carpeta donde viven los ejecutables de Shares una vez instalado.
LTP_DIR = Path(r"C:\LTP")

# Definición de los 2 accesos directos, en el mismo orden y con los mismos
# valores que el código VB.NET original (CreateShortCut / CreateShortCutHPGUI).
_SHORTCUT_DEFS = [
    {
        "filename": "LTP SHARES.lnk",
        "description": "LTPGUI32",
        "target": LTP_DIR / "LTPGUI32.exe",
        "arguments": lambda ciudad: f" /ACM /CC{ciudad} /W%COMPUTERNAME% /SU%COMPUTERNAME%",
    },
    {
        "filename": "LiteGUI.lnk",
        "description": "LTPGUI32",
        "target": LTP_DIR / "LTPHPS32.exe",
        "arguments": lambda ciudad: f" /ACM /W%COMPUTERNAME% /SU%COMPUTERNAME% /CC{ciudad}",
    },
]


class ShortcutError(Exception):
    """Error esperado al crear un acceso directo (ej. no se pudo invocar
    COM, ruta inválida). El mensaje ya viene listo para mostrárselo tal
    cual al técnico."""


def _create_shortcut(
    shortcut_path: Path,
    target_path: Path,
    arguments: str,
    description: str,
    working_directory: Path,
    window_style: int = 1,
) -> None:
    """Crea UN acceso directo (.lnk) vía COM (`WScript.Shell`), igual que
    hacía el VB.NET original. Import perezoso de `win32com.client` -- ese
    módulo (parte de `pywin32`) solo existe en Windows, y esta app se
    desarrolla y prueba en Linux/Mac; importarlo recién adentro de la
    función (en vez de al tope del archivo) permite que el resto del
    módulo se pueda importar y probar sin pywin32 instalado, mockeando
    esta función directamente en los tests."""
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.Arguments = arguments
    shortcut.Description = description
    shortcut.WorkingDirectory = str(working_directory)
    shortcut.WindowStyle = window_style
    shortcut.Save()


def create_ltp_shares_shortcuts(ciudad: str, public_desktop: Path = PUBLIC_DESKTOP) -> str:
    """Crea los 2 accesos directos de Shares ("LTP SHARES" y "LiteGUI") en
    `public_desktop` (por defecto `C:\\Users\\Public\\Desktop`), con el
    valor de CIUDAD ya resuelto en sus argumentos.

    Devuelve un mensaje corto de éxito para el estado de la pantalla.
    Lanza `ShortcutError` si algo falla -- el llamador decide cómo
    mostrarlo (igual que el resto de errores de esta pantalla)."""
    ciudad = (ciudad or "").strip()
    if not ciudad:
        raise ShortcutError(
            "El campo CIUDAD está vacío -- hace falta un valor para armar los accesos directos de Shares."
        )

    created: list[str] = []
    for shortcut_def in _SHORTCUT_DEFS:
        shortcut_path = Path(public_desktop) / shortcut_def["filename"]
        try:
            _create_shortcut(
                shortcut_path=shortcut_path,
                target_path=shortcut_def["target"],
                arguments=shortcut_def["arguments"](ciudad),
                description=shortcut_def["description"],
                working_directory=LTP_DIR,
            )
        except Exception as exc:  # COM puede lanzar varios tipos de error distintos
            raise ShortcutError(f"No se pudo crear el acceso directo '{shortcut_path}': {exc}") from exc
        created.append(str(shortcut_path))

    return f"Accesos directos creados: {', '.join(created)}"


# --------------------------------------------------------------------------
# "Shortcuts" del catálogo APPS (2da columna, id `shortcuts`), portado de
# `Scripts\Shortcut STN.bat`. A diferencia de los accesos directos de
# Shares de arriba (que se ARMAN vía COM, con el valor de CIUDAD resuelto
# en sus argumentos), estos ya vienen armados de antemano dentro de la
# carpeta de instaladores -- este paso solo los COPIA, igual que
# `app/appshell_post_install.py` hace con los 2 accesos directos de
# AppShell.
# --------------------------------------------------------------------------

# Carpeta de instaladores (relativa a `installers_base_path`) donde vive
# todo lo que copia este paso.
STN_SOURCE_DIR_REL = "Scripts"

# Dentro de esa carpeta: una subcarpeta con recursos compartidos que se
# copian tal cual a `C:\copaair` (no son accesos directos -- ej. archivos
# de configuración/recursos que otras apps de esa carpeta esperan
# encontrar ahí), y otra con los accesos directos en sí.
STN_COPAAIR_SUBDIR = "Copaair"
STN_SHORTCUTS_SUBDIR = "Shortcut"

# Carpeta destino de la copia de "Copaair" -- FUERA de Public Desktop,
# directo en la raíz de C:.
COPAAIR_DEST_DIR = Path(r"C:\copaair")

# Nombres que traía el .bat original (algunos ".lnk", dos ".url" -- Excel
# y Word, que en este equipo apuntan a atajos web en vez de a la app de
# escritorio). `copy_stn_assets_and_shortcuts()` YA NO filtra por esta
# lista -- copia TODO archivo que encuentre suelto en `Shortcut\` (ver
# `_copy_folder_and_shortcuts()`), para que agregar/quitar/renombrar un
# acceso directo ahí no requiera tocar código. Esta constante queda solo
# de referencia (y la usan los tests para armar los archivos de prueba).
STN_SHORTCUT_FILES = [
    "WorldTracer.lnk",
    "AIMS.lnk",
    "COPA ACADEMY.lnk",
    "CORREO WEB.lnk",
    "LOPA.lnk",
    "RED.lnk",
    "SABRE.lnk",
    "Flight Radar24.lnk",
    "EXCEL.url",
    "WORD.url",
]


def _copy_folder_and_shortcuts(
    installers_base_path: str,
    source_dir_rel: str,
    copaair_subdir: str,
    shortcuts_subdir: str,
    shortcut_files: list[str] | None,
    public_desktop: Path,
    copaair_dest_dir: Path,
) -> str:
    """Generaliza el patrón común a "Shortcuts" (`Scripts\\Shortcut STN.bat`)
    y "ShortCut-MTO" (`MTO\\ShortCut_MTO.bat`): copia una carpeta `Copaair`
    (recursiva, con subcarpetas) a `copaair_dest_dir`, y después los
    accesos directos ya armados a `public_desktop`. `shortcuts_subdir`
    puede ser `""` si los accesos directos viven sueltos directo en
    `source_dir_rel` (caso MTO) en vez de en una subcarpeta propia (caso
    STN, que los tiene en una subcarpeta "Shortcut").

    `shortcut_files`: lista fija de nombres exactos a copiar (falla con
    `ShortcutError` si falta alguno -- caso MTO, cuya carpeta de origen
    comparte espacio con otros instaladores de esa misma columna, así que
    no se puede copiar "todo lo que haya ahí" sin arrastrar también esos
    instaladores). O `None` para copiar TODO archivo que haya suelto
    DIRECTO dentro de `shortcuts_src` (sin bajar a subcarpetas),
    cualquiera sea su nombre -- pensado para "Shortcuts" (STN), cuya
    carpeta `Shortcut\\` es exclusiva de accesos directos y nada más, así
    que agregar/quitar/renombrar uno ahí ya no requiere tocar el código
    (antes, con una lista fija de 10 nombres, un archivo renombrado o
    ausente -- visto en pruebas reales con `LOPA.lnk` -- hacía fallar
    todo el paso).

    Siempre sobrescribe -- ninguno de los 2 `.bat` originales pasaba `/Y`
    en los `xcopy` de los accesos directos individuales (así que en teoría
    preguntaban antes de sobrescribir); acá se sobrescribe sin preguntar,
    sin cambio de comportamiento real ya que un `xcopy` sin entrada
    interactiva disponible nunca llegaba a sobrescribir nada de todos
    modos.

    Lanza `ShortcutError` si la carpeta `Copaair` o la de accesos
    directos no aparece donde se espera, si la carpeta de accesos
    directos existe pero está vacía (con `shortcut_files=None`), si falta
    alguno de los nombres exactos esperados (con `shortcut_files` como
    lista), o si alguna copia falla."""
    source_dir = Path(installers_base_path) / source_dir_rel
    copaair_src = source_dir / copaair_subdir
    shortcuts_src = source_dir / shortcuts_subdir if shortcuts_subdir else source_dir
    public_desktop = Path(public_desktop)
    copaair_dest_dir = Path(copaair_dest_dir)

    if not copaair_src.exists():
        raise ShortcutError(f"No se encontró la carpeta '{copaair_src}'.")
    try:
        shutil.copytree(copaair_src, copaair_dest_dir, dirs_exist_ok=True)
    except OSError as exc:
        raise ShortcutError(f"No se pudo copiar '{copaair_src}' a '{copaair_dest_dir}': {exc}")

    if not shortcuts_src.exists():
        raise ShortcutError(f"No se encontró la carpeta de accesos directos '{shortcuts_src}'.")
    public_desktop.mkdir(parents=True, exist_ok=True)

    if shortcut_files is None:
        names = sorted(entry.name for entry in shortcuts_src.iterdir() if entry.is_file())
        if not names:
            raise ShortcutError(f"No se encontró ningún acceso directo en '{shortcuts_src}'.")
    else:
        names = shortcut_files

    copied: list[str] = []
    for name in names:
        source_file = shortcuts_src / name
        if not source_file.exists():
            raise ShortcutError(f"No se encontró el acceso directo '{source_file}'.")
        try:
            shutil.copy2(source_file, public_desktop / name)
        except OSError as exc:
            raise ShortcutError(f"No se pudo copiar el acceso directo '{source_file}': {exc}")
        copied.append(name)

    return f"Copaair copiado a {copaair_dest_dir}; {len(copied)} acceso(s) directo(s) copiados a {public_desktop}"


def copy_stn_assets_and_shortcuts(
    installers_base_path: str,
    public_desktop: Path = PUBLIC_DESKTOP,
    copaair_dest_dir: Path = COPAAIR_DEST_DIR,
) -> str:
    """Copia la carpeta `Copaair` (dentro de `Scripts\\`) y TODO archivo
    que haya suelto directo en `Scripts\\Shortcut\\`, sin importar su
    nombre -- antes se exigía que coincidieran exactamente los 10 nombres
    de `STN_SHORTCUT_FILES` (esa constante queda solo de referencia /
    para armar los datos de prueba, ya no filtra nada acá). Ver
    `_copy_folder_and_shortcuts()`."""
    return _copy_folder_and_shortcuts(
        installers_base_path,
        STN_SOURCE_DIR_REL,
        STN_COPAAIR_SUBDIR,
        STN_SHORTCUTS_SUBDIR,
        None,
        public_desktop,
        copaair_dest_dir,
    )


# --------------------------------------------------------------------------
# "ShortCut-MTO" del catálogo APPS (3ra columna, id `shortcut_mto`),
# portado de `MTO\ShortCut_MTO.bat`. Mismo patrón que "Shortcuts" (STN)
# arriba, pero con su PROPIA carpeta `Copaair` (distinta de la de
# `Scripts\Copaair` -- son 2 carpetas separadas, cada una junto a su
# propio `.bat` original) y sus accesos directos sueltos directo en `MTO\`
# (sin una subcarpeta "Shortcut" propia, a diferencia de STN).
# --------------------------------------------------------------------------

MTO_SOURCE_DIR_REL = "MTO"
MTO_COPAAIR_SUBDIR = "Copaair"

MTO_SHORTCUT_FILES = [
    "MXI.lnk",
    "ToolBox Remote.url",
    "TOOLBOX.lnk",
]


def copy_mto_assets_and_shortcuts(
    installers_base_path: str,
    public_desktop: Path = PUBLIC_DESKTOP,
    copaair_dest_dir: Path = COPAAIR_DEST_DIR,
) -> str:
    """Copia la carpeta `Copaair` (dentro de `MTO\\`) y los 3 accesos
    directos de `MTO_SHORTCUT_FILES` (sueltos directo en `MTO\\`, sin
    subcarpeta). Ver `_copy_folder_and_shortcuts()`."""
    return _copy_folder_and_shortcuts(
        installers_base_path,
        MTO_SOURCE_DIR_REL,
        MTO_COPAAIR_SUBDIR,
        "",
        MTO_SHORTCUT_FILES,
        public_desktop,
        copaair_dest_dir,
    )


# --------------------------------------------------------------------------
# Paso extra de "BFirst" del catálogo APPS (2da columna, id `bfirst`),
# portado de `BFirst\copy.bat`. A diferencia de los 2 casos de arriba (que
# copian una carpeta `Copaair` entera, de forma recursiva), acá el origen
# no es una carpeta -- es un único archivo de ícono suelto en `BFirst\`.
# El `.bat` original usaba `xcopy /S /I /E /Y` sobre ese archivo suelto:
# como el origen no es un directorio, `/S` y `/E` (recursivos) no tienen
# ningún efecto real -- lo único que importa es `/I` (crea `C:\Copaair`
# como carpeta si no existe, en vez de preguntar si el destino es archivo
# o carpeta) y `/Y` (sobrescribe sin preguntar). El segundo `xcopy` (el
# acceso directo `BFIRST.url` a Public Desktop) tampoco pasaba `/Y` en el
# original -- mismo caso sin efecto real que STN/MTO arriba.
# --------------------------------------------------------------------------

BFIRST_SOURCE_DIR_REL = "BFirst"
BFIRST_ICON_NAME = "bytemaster_logoprincipalqqq.ico"
BFIRST_SHORTCUT_NAME = "BFIRST.url"


def copy_bfirst_assets_and_shortcut(
    installers_base_path: str,
    public_desktop: Path = PUBLIC_DESKTOP,
    copaair_dest_dir: Path = COPAAIR_DEST_DIR,
) -> str:
    """Portado de `BFirst\\copy.bat`: copia el ícono
    `bytemaster_logoprincipalqqq.ico` a `C:\\copaair` (crea la carpeta si
    no existe) y el acceso directo `BFIRST.url` a
    `C:\\Users\\Public\\Desktop`. Comparte destino con
    `copy_stn_assets_and_shortcuts()`/`copy_mto_assets_and_shortcuts()`
    (ambas también dejan cosas en `C:\\copaair`), pero el origen acá es un
    único archivo, no una carpeta -- por eso no reutiliza
    `_copy_folder_and_shortcuts()`.

    Devuelve un mensaje corto de éxito con ambos destinos. Lanza
    `ShortcutError` si falta el ícono o el acceso directo de origen, o si
    alguna copia falla."""
    source_dir = Path(installers_base_path) / BFIRST_SOURCE_DIR_REL
    public_desktop = Path(public_desktop)
    copaair_dest_dir = Path(copaair_dest_dir)

    icon_src = source_dir / BFIRST_ICON_NAME
    if not icon_src.exists():
        raise ShortcutError(f"No se encontró el ícono '{icon_src}'.")
    copaair_dest_dir.mkdir(parents=True, exist_ok=True)
    icon_dst = copaair_dest_dir / BFIRST_ICON_NAME
    try:
        shutil.copy2(icon_src, icon_dst)
    except OSError as exc:
        raise ShortcutError(f"No se pudo copiar '{icon_src}' a '{icon_dst}': {exc}")

    shortcut_src = source_dir / BFIRST_SHORTCUT_NAME
    if not shortcut_src.exists():
        raise ShortcutError(f"No se encontró el acceso directo '{shortcut_src}'.")
    public_desktop.mkdir(parents=True, exist_ok=True)
    shortcut_dst = public_desktop / BFIRST_SHORTCUT_NAME
    try:
        shutil.copy2(shortcut_src, shortcut_dst)
    except OSError as exc:
        raise ShortcutError(f"No se pudo copiar el acceso directo '{shortcut_src}': {exc}")

    return f"Ícono copiado a {icon_dst}; acceso directo copiado a {shortcut_dst}"
