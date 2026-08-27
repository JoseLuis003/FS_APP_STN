"""Paso posterior a instalar "AppShell 4.00.0030" (ítem
`appshell_4_00_0030` del catálogo LTP / CSS), que reemplaza al paso
`CSS permision.bat` que se usaba antes.

Seguridad de Copa bloquea la ejecución de archivos `.bat` en los equipos,
así que en vez de correr ese script, esta misma lógica se porta
directamente a Python y se empaqueta dentro de la app (igual que se hizo
con "LTP setting.bat" -> `app/shares_setup.py`, ver
`installer_type: "python"` en `app/installer.py`).

En orden:

1. Da control total (Everyone) a `C:\\Program Files (x86)\\DXC Technology`
   -- carpeta y TODO su contenido ya existente (`icacls ... /grant
   Everyone:(OI)(CI)F /t /c`), igual que se hacía a mano desde el diálogo
   de Seguridad de Windows (Propiedades > Seguridad > Editar > Everyone >
   Control total). Hace falta porque AppShell necesita poder escribir sus
   propios archivos de configuración ahí en tiempo de ejecución.
2. Copia los 2 accesos directos que trae el propio instalador de AppShell
   dentro de la carpeta de instaladores (`DXC_GUI_RES\\PssAppShell 4.0\\`,
   junto al `.msi` y al `vcredist`) al escritorio público
   (`C:\\Users\\Public\\Desktop`), para que queden visibles para
   cualquier usuario que inicie sesión en el equipo:

   - "Start PSS AppShell PROD.lnk"
   - "Start PSS AppShell TEST.lnk"

Si cualquiera de los 2 pasos falla (carpeta/archivo no encontrado, icacls
termina con código de salida distinto de 0, etc.), se lanza
`AppShellPostInstallError` y el resto de la cola de instalación se
detiene ahí, igual que con cualquier otro paso del catálogo que falla."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Evita que Windows le abra su propia ventana de consola a `icacls`
# (quedaría en blanco y parecería colgado) -- ver la explicación
# completa en `NO_CONSOLE_WINDOW`, `app/installer.py`.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Carpeta donde el instalador de AppShell deja todo instalado -- necesita
# permisos abiertos para que la app pueda escribir su configuración.
DEFAULT_DXC_PATH = Path(r"C:\Program Files (x86)\DXC Technology")

# Escritorio público -- visible para cualquier usuario que inicie sesión.
DEFAULT_PUBLIC_DESKTOP = Path(r"C:\Users\Public\Desktop")

# Carpeta de instaladores (relativa a `installers_base_path`) donde viven
# el .msi, el vcredist y estos 2 accesos directos ya armados.
SHORTCUTS_SOURCE_REL = r"DXC_GUI_RES\PssAppShell 4.0"

SHORTCUT_NAMES = [
    "Start PSS AppShell PROD.lnk",
    "Start PSS AppShell TEST.lnk",
]


class AppShellPostInstallError(Exception):
    """Error esperado (carpeta/archivo no encontrado, icacls falló, etc.)
    en el post-instalación de AppShell 4.00.0030. El mensaje ya viene listo
    para mostrárselo tal cual al técnico."""


def grant_full_control_everyone(dxc_path: Path = DEFAULT_DXC_PATH) -> str:
    """Paso 1: `icacls <dxc_path> /grant Everyone:(OI)(CI)F /t /c` --
    `/t` para que también se aplique a los archivos/subcarpetas que ya
    existen ahí (no solo a los que se creen de ahora en adelante), `/c`
    para que siga aunque algún archivo individual falle. Equivalente a
    marcar "Full control" para "Everyone" a mano en el diálogo de
    Seguridad de Windows."""
    dxc_path = Path(dxc_path)
    if not dxc_path.exists():
        raise AppShellPostInstallError(f"No se encontró la carpeta '{dxc_path}'.")

    try:
        result = subprocess.run(
            ["icacls", str(dxc_path), "/grant", "Everyone:(OI)(CI)F", "/t", "/c"],
            capture_output=True,
            text=True,
            timeout=5 * 60,
            creationflags=_NO_CONSOLE_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise AppShellPostInstallError(f"icacls: tiempo de espera agotado (5 min) sobre '{dxc_path}'.")
    except OSError as exc:
        raise AppShellPostInstallError(f"icacls: no se pudo ejecutar sobre '{dxc_path}' -- {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"icacls: terminó con código de salida {result.returncode} sobre '{dxc_path}'"
        if detail:
            msg += f" -- {detail}"
        raise AppShellPostInstallError(msg)

    return f"permisos Everyone (control total) en {dxc_path}"


def copy_appshell_shortcuts(
    installers_base_path: str,
    shortcuts_source_rel: str = SHORTCUTS_SOURCE_REL,
    public_desktop: Path = DEFAULT_PUBLIC_DESKTOP,
) -> str:
    """Paso 2: copia los 2 accesos directos (`SHORTCUT_NAMES`), que ya
    vienen armados dentro de `installers_base_path / shortcuts_source_rel`
    (junto al resto de los instaladores de AppShell), al escritorio
    público. Sobrescribe si ya existían (de una instalación anterior).
    Lanza `AppShellPostInstallError` si la carpeta de origen o alguno de
    los 2 accesos directos no aparece donde se espera."""
    source_dir = Path(installers_base_path) / shortcuts_source_rel
    public_desktop = Path(public_desktop)

    if not source_dir.exists():
        raise AppShellPostInstallError(f"No se encontró la carpeta de accesos directos '{source_dir}'.")

    public_desktop.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for name in SHORTCUT_NAMES:
        source_file = source_dir / name
        if not source_file.exists():
            raise AppShellPostInstallError(f"No se encontró el acceso directo '{source_file}'.")
        try:
            shutil.copy2(source_file, public_desktop / name)
        except OSError as exc:
            raise AppShellPostInstallError(f"No se pudo copiar el acceso directo '{source_file}': {exc}")
        copied.append(name)

    return f"{len(copied)} acceso(s) directo(s) copiados a {public_desktop}"


def run_appshell_post_install(installers_base_path: str = "") -> str:
    """Corre los 2 pasos de arriba en orden, uno detrás del otro -- se
    detiene en el primero que falle, igual que cualquier secuencia de
    `extra_steps` del catálogo. Pensado para colgarse como paso
    `installer_type: "python"` del ítem `appshell_4_00_0030` en
    `ltp_css_apps.json` (ver `app/installer.py`, que le pasa
    `installers_base_path` a todo paso de este tipo).

    Devuelve un mensaje corto de éxito con el detalle de cada paso, listo
    para mostrar en el estado de la pantalla. Lanza
    `AppShellPostInstallError` si algún paso falla."""
    detail_permissions = grant_full_control_everyone()
    detail_shortcuts = copy_appshell_shortcuts(installers_base_path)
    return f"{detail_permissions}; {detail_shortcuts}"
