"""Paso extra de "VPN" del catálogo APPS (2da columna, id `anyconnect`),
portado de `VPN\\copy.bat`. Deja lista la configuración de conexión de
Cisco AnyConnect (rebautizado "Cisco Secure Client" en versiones más
recientes -- de ahí el nombre del acceso directo) después de instalar el
`.msi` principal. En el mismo orden que el `.bat` original:

1. Copia `preferences.xml` al perfil del USUARIO actual
   (`AppData\\Local\\Cisco\\Cisco AnyConnect Secure Mobility Client\\`,
   resuelto vía la variable de entorno `%USERNAME%` -- mismo mecanismo
   que "SAP GUI 7.8", ver `app/sap_gui_setup.py`).
2. Copia `preferences_global.xml` a
   `C:\\ProgramData\\Cisco\\Cisco AnyConnect Secure Mobility Client\\`
   (configuración a nivel de equipo, no de usuario).
3. Copia la carpeta `Profile` COMPLETA (recursiva, con subcarpetas si
   las tuviera) a `...\\Profile\\` dentro de esa misma carpeta de
   ProgramData -- a diferencia de los 2 archivos sueltos de arriba, acá
   el origen sí es una carpeta, así que las banderas recursivas del
   `xcopy` original (`/S /E`) sí tenían efecto real.
4. Copia el acceso directo `Cisco Secure Client.lnk` a Public Desktop.

El `.bat` original agregaba `/A` a los 3 `xcopy` (copiar solo si el
archivo tiene el atributo "archive" activo, sin resetearlo) -- se ignora
acá: ese atributo está activo por defecto en prácticamente cualquier
archivo recién extraído de un paquete de instalación, así que en la
práctica nunca filtraba nada; replicarlo tal cual requeriría leer
atributos de archivo específicos de Windows sin ganar ningún
comportamiento real distinto.

A diferencia de "SAP GUI 7.8" (que tenía un paso de limpieza
best-effort), acá los 4 pasos son igual de necesarios para que la VPN
funcione, así que los 4 son fail-loud: cualquiera que falle detiene el
resto y se marca como error."""
from __future__ import annotations

import getpass
import os
import shutil
from pathlib import Path

# Carpeta de instaladores (relativa a `installers_base_path`) donde viven
# los 4 archivos/carpeta que copia este paso.
SOURCE_DIR_REL = "VPN"

PREFERENCES_FILE_NAME = "preferences.xml"
PREFERENCES_GLOBAL_FILE_NAME = "preferences_global.xml"
PROFILE_SUBDIR_NAME = "Profile"
SHORTCUT_FILE_NAME = "Cisco Secure Client.lnk"

# Subcarpeta dentro del perfil del usuario donde AnyConnect busca sus
# preferencias personales.
CISCO_USER_SUBDIR_REL = r"AppData\Local\Cisco\Cisco AnyConnect Secure Mobility Client"

# Raíz de perfiles de usuario -- se une a `_current_username()`, igual
# que `app/sap_gui_setup.py` (cada módulo define su propia constante en
# vez de importarla de otro, por precedente del proyecto).
USERS_DIR = Path(r"C:\Users")

# Carpeta de configuración a nivel de equipo (preferences_global.xml y la
# carpeta Profile viven acá, no en el perfil de un usuario en particular).
CISCO_PROGRAMDATA_DIR = Path(r"C:\ProgramData\Cisco\Cisco AnyConnect Secure Mobility Client")

VPN_PUBLIC_DESKTOP_DIR = Path(r"C:\Users\Public\Desktop")


class VpnSetupError(Exception):
    """Error esperado al aplicar el paso extra de "VPN". El mensaje ya
    viene listo para mostrárselo tal cual al técnico."""


def _current_username() -> str:
    """Resuelve %USERNAME% -- ver la misma función en
    `app/sap_gui_setup.py` (duplicada a propósito, no importada de ahí,
    por el mismo precedente de helpers self-contained por módulo)."""
    return os.environ.get("USERNAME") or getpass.getuser()


def _copy_file(src: Path, dst: Path, step_label: str) -> None:
    if not src.exists():
        raise VpnSetupError(f"{step_label}: no se encontró '{src}'.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        raise VpnSetupError(f"{step_label}: no se pudo copiar '{src}' a '{dst}': {exc}")


def apply_vpn_setup(
    installers_base_path: str,
    users_dir: Path = USERS_DIR,
    programdata_dir: Path = CISCO_PROGRAMDATA_DIR,
    public_desktop: Path = VPN_PUBLIC_DESKTOP_DIR,
) -> str:
    """Corre los 4 pasos de `VPN\\copy.bat`, en el mismo orden que el
    original. Pensado para colgarse como paso `installer_type: "python"`
    (extra step) del ítem `anyconnect` en `apps.json` (ver
    `app/installer.py`).

    Devuelve un mensaje corto de éxito para el estado de la pantalla.
    Lanza `VpnSetupError` si falla cualquiera de los 4 pasos."""
    source_dir = Path(installers_base_path) / SOURCE_DIR_REL
    programdata_dir = Path(programdata_dir)
    public_desktop = Path(public_desktop)

    user_prefs_dst = Path(users_dir) / _current_username() / CISCO_USER_SUBDIR_REL / PREFERENCES_FILE_NAME
    _copy_file(source_dir / PREFERENCES_FILE_NAME, user_prefs_dst, "preferences.xml (perfil de usuario)")

    global_prefs_dst = programdata_dir / PREFERENCES_GLOBAL_FILE_NAME
    _copy_file(source_dir / PREFERENCES_GLOBAL_FILE_NAME, global_prefs_dst, "preferences_global.xml (ProgramData)")

    profile_src = source_dir / PROFILE_SUBDIR_NAME
    profile_dst = programdata_dir / PROFILE_SUBDIR_NAME
    if not profile_src.exists():
        raise VpnSetupError(f"No se encontró la carpeta '{profile_src}'.")
    try:
        shutil.copytree(profile_src, profile_dst, dirs_exist_ok=True)
    except OSError as exc:
        raise VpnSetupError(f"No se pudo copiar '{profile_src}' a '{profile_dst}': {exc}")

    shortcut_dst = public_desktop / SHORTCUT_FILE_NAME
    _copy_file(source_dir / SHORTCUT_FILE_NAME, shortcut_dst, "acceso directo Cisco Secure Client")

    return (
        f"Preferencias copiadas a {user_prefs_dst} y {global_prefs_dst}; "
        f"perfil VPN copiado a {profile_dst}; acceso directo copiado a {shortcut_dst}"
    )
