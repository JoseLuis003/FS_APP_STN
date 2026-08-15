"""Paso extra de "SAP GUI 7.8" del catálogo APPS (2da columna, id
`sap_gui`), portado de `SAP_GUI_7.80\\Win32\\copy.bat` (el ÚLTIMO de los 4
pasos extra de ese ítem, después de `NwSapSetup.exe`, el parche
`GUI800_4-80006341.EXE` y `SAPSetupSLC.exe`).

A diferencia de todos los pasos "python" anteriores (que trabajan sobre
carpetas de sistema o Public Desktop), este toca el PERFIL DEL USUARIO
ACTUAL (`C:\\Users\\<usuario>\\...`), resuelto vía la variable de entorno
`%USERNAME%` -- igual que hacía el `.bat` original. En orden:

1. Crea `AppData\\Roaming\\SAP\\Common` dentro del perfil del usuario
   (si no existe).
2. Copia `SAPUILandscape.xml` y `SAPUILandscapeGlobal.xml` (la
   configuración de conexiones SAP con los servidores de Copa) a esa
   carpeta.
3. Borra `SAP Logon.lnk` del escritorio DEL USUARIO (el que arma el
   propio instalador de SAP GUI ahí) -- en modo "mejor esfuerzo": si no
   existe (o no se puede borrar por algún motivo), no se considera un
   error. El `.bat` original tampoco revisaba el resultado de `del` en
   ningún momento, así que ese archivo ausente (o cualquier falla al
   borrarlo) nunca detenía el resto del script.
4. Copia el `SAP Logon.lnk` "oficial" (con branding/config de Copa) a
   Public Desktop, para que se vea sin importar la cuenta con la que se
   entre al equipo -- mismo criterio que "Shortcuts"/"ShortCut-MTO"/
   "BFirst".

Los pasos 1, 2 y 4 sí son fail-loud (paran la cola y marcan error si
fallan) -- son la parte que de verdad deja SAP GUI usable. Solo el
borrado del acceso directo viejo del paso 3 es best-effort, por ser una
limpieza cosmética sin impacto funcional si no se logra."""
from __future__ import annotations

import getpass
import os
import shutil
from pathlib import Path

# Carpeta de instaladores (relativa a `installers_base_path`) donde viven
# los 3 archivos que copia este paso.
SOURCE_DIR_REL = r"SAP_GUI_7.80\Win32"

# Subcarpeta dentro del perfil del usuario donde SAP GUI busca su
# configuración de conexiones.
SAP_COMMON_SUBDIR_REL = r"AppData\Roaming\SAP\Common"

LANDSCAPE_FILE_NAME = "SAPUILandscape.xml"
LANDSCAPE_GLOBAL_FILE_NAME = "SAPUILandscapeGlobal.xml"
SHORTCUT_FILE_NAME = "SAP Logon.lnk"

# Raíz de perfiles de usuario -- se une a `_current_username()` para
# armar `C:\Users\<usuario>`, igual que el `.bat` original.
USERS_DIR = Path(r"C:\Users")

# Escritorio público -- ver `app/shortcuts.py` y
# `app/appshell_post_install.py`: cada módulo define su propia constante
# en vez de importarla de otro, por precedente del proyecto.
SAP_PUBLIC_DESKTOP_DIR = Path(r"C:\Users\Public\Desktop")


class SapGuiSetupError(Exception):
    """Error esperado al aplicar el paso extra de "SAP GUI 7.8". El
    mensaje ya viene listo para mostrárselo tal cual al técnico."""


def _current_username() -> str:
    """Resuelve %USERNAME%: en Windows, `os.environ["USERNAME"]` es la
    variable de entorno equivalente. `getpass.getuser()` es un respaldo
    para cuando esa variable no está definida (como al desarrollar/probar
    este módulo en Linux/Mac)."""
    return os.environ.get("USERNAME") or getpass.getuser()


def apply_sap_gui_setup(
    installers_base_path: str,
    users_dir: Path = USERS_DIR,
    public_desktop: Path = SAP_PUBLIC_DESKTOP_DIR,
) -> str:
    """Corre los 4 pasos de `SAP_GUI_7.80\\Win32\\copy.bat`, en el mismo
    orden que el original. Pensado para colgarse como paso
    `installer_type: "python"` (extra step) del ítem `sap_gui` en
    `apps.json` (ver `app/installer.py`).

    Devuelve un mensaje corto de éxito para el estado de la pantalla.
    Lanza `SapGuiSetupError` si falla la carpeta de configuración SAP o el
    acceso directo de Public Desktop -- el borrado del acceso directo
    viejo del usuario nunca lanza error (ver docstring del módulo)."""
    source_dir = Path(installers_base_path) / SOURCE_DIR_REL
    user_home = Path(users_dir) / _current_username()
    sap_common_dir = user_home / SAP_COMMON_SUBDIR_REL

    sap_common_dir.mkdir(parents=True, exist_ok=True)

    for file_name in (LANDSCAPE_FILE_NAME, LANDSCAPE_GLOBAL_FILE_NAME):
        src = source_dir / file_name
        if not src.exists():
            raise SapGuiSetupError(f"No se encontró '{src}'.")
        try:
            shutil.copy2(src, sap_common_dir / file_name)
        except OSError as exc:
            raise SapGuiSetupError(f"No se pudo copiar '{src}' a '{sap_common_dir}': {exc}")

    user_shortcut = user_home / "Desktop" / SHORTCUT_FILE_NAME
    try:
        user_shortcut.unlink()
        user_shortcut_removed = True
    except OSError:
        # No existía, o no se pudo borrar por el motivo que sea -- ninguno
        # de los 2 casos detiene la acción (ver docstring del módulo).
        user_shortcut_removed = False

    shortcut_src = source_dir / SHORTCUT_FILE_NAME
    if not shortcut_src.exists():
        raise SapGuiSetupError(f"No se encontró el acceso directo '{shortcut_src}'.")
    public_desktop = Path(public_desktop)
    public_desktop.mkdir(parents=True, exist_ok=True)
    shortcut_dst = public_desktop / SHORTCUT_FILE_NAME
    try:
        shutil.copy2(shortcut_src, shortcut_dst)
    except OSError as exc:
        raise SapGuiSetupError(f"No se pudo copiar el acceso directo '{shortcut_src}' a '{shortcut_dst}': {exc}")

    detail = f"Configuración SAP copiada a {sap_common_dir}; acceso directo copiado a {shortcut_dst}"
    if user_shortcut_removed:
        detail += f" (se eliminó el acceso directo previo en {user_shortcut})"
    return detail
