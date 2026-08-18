"""Instala el Microsoft ".NET Desktop Runtime" (el ".NET" moderno, NO
".NET Framework 3.5" -- ver app/netfx35_setup.py, que es un requisito
distinto para BFirst) que Dell Command Update exige como dependencia
DURA desde su serie 5.x ("Windows Universal Application"): si falta, o
si la única versión instalada queda fuera del rango que DCU acepta, el
instalador de DCU termina con el código de salida 4 -- "hard
dependency error" en el esquema estándar de Dell Update Package (DUP),
el mismo esquema que documenta que ese código no se puede forzar con
`/f`: no hay forma de "saltárselo", hay que cumplir el requisito antes.

Confirmado en una prueba real de campo: un Dell Latitude 5280 genuino
(no una VM) con Dell Command Update 5.7.1
(`DellCommandUpdate\\Dell-Command-Update-Windows-Universal-Application_
P0P70_WIN64_5.7.1_A00.EXE`) terminó con código de salida 4 pese a ser
hardware Dell soportado -- descartando así un problema de hardware o
de sistema operativo no soportado (las otras causas típicas de ese
código). Reportes de la comunidad de Dell sobre esta misma serie 5.x
confirman el motivo real: el instalador de DCU exige tener ya instalado
el Microsoft .NET Desktop Runtime dentro de un rango de versión
específico (ver `_MIN_VERSION`/`_MAX_VERSION`) -- ni versiones
anteriores a ese rango ni versiones más nuevas (ej. la 8.0.18, que
Microsoft ya liberó y excede el máximo que DCU revisa) sirven, aunque
esté "instalado algún .NET".

Usado como PRIMER paso (instalador PRINCIPAL) del ítem "dell_command"
en config/apps.json, con el EXE real de Dell Command Update como
`extra_step` después -- mismo patrón ya usado para "bfirst"/NetFX35
(ver app/netfx35_setup.py): asegurar el prerequisito ACÁ, con un
mensaje claro si falla, en vez de dejar que DCU se estrelle más
adelante con el críptico código 4 de siempre."""
from __future__ import annotations

import ntpath
import re
import subprocess
from pathlib import Path

# Rango de versión de Microsoft.WindowsDesktop.App que reportes de la
# comunidad de Dell confirman que acepta el instalador de Dell Command
# Update serie 5.x: entre 8.0.8 y 8.0.17 (x64). Por eso no alcanza con
# detectar "algún" runtime instalado -- tiene que caer en este rango.
_MIN_VERSION = (8, 0, 8)
_MAX_VERSION = (8, 0, 17)

# Carpeta estándar donde Windows registra cada "shared framework" de
# .NET instalado, una subcarpeta por versión (ej.
# "...\\Microsoft.WindowsDesktop.App\\8.0.17\\").
_SHARED_FRAMEWORK_DIR = r"C:\Program Files\dotnet\shared\Microsoft.WindowsDesktop.App"

# Instalador offline que hay que colocar junto a los demás, en
# "<installers_base_path>\\DotNetDesktopRuntime\\..." (ver
# installers_base_path) -- no se descarga nada en el momento porque
# muchas estaciones de Copa no tienen salida a internet (mismo
# criterio que NetFX35). Se eligió a propósito la versión 8.0.17 (tope
# superior que acepta DCU 5.x): sirve tanto si no hay NINGÚN runtime
# instalado como si ya hay uno más nuevo que DCU no acepta (ej.
# 8.0.18) -- los runtimes de .NET conviven instalados en paralelo
# (side-by-side), así que agregar este no reemplaza ni afecta ningún
# otro que ya esté.
_INSTALLER_SUBPATH_PARTS = ("DotNetDesktopRuntime", "windowsdesktop-runtime-8.0.17-win-x64.exe")

_TIMEOUT_SECONDS = 300

# Mismo criterio que el resto de la app para este código (ver
# SUCCESS_CODES en app/installer.py): 3010 = éxito, pide reiniciar.
_SUCCESS_CODES = {0, 3010}

_VERSION_DIR_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


class DotNetDesktopRuntimeError(Exception):
    """Error esperado si no se pudo confirmar/instalar el .NET Desktop
    Runtime que necesita Dell Command Update. El mensaje ya viene listo
    para mostrárselo tal cual al técnico."""


def _parse_version(folder_name: str) -> tuple[int, int, int] | None:
    match = _VERSION_DIR_RE.match(folder_name)
    if not match:
        return None
    a, b, c = match.groups()
    return (int(a), int(b), int(c))


def _list_installed_versions(shared_framework_dir: str) -> list[tuple[int, int, int]]:
    """Lista las versiones de Microsoft.WindowsDesktop.App ya instaladas,
    a partir de las subcarpetas de `shared_framework_dir` (una por
    versión) -- devuelve lista vacía si la carpeta no existe (ej. no
    hay NINGÚN .NET Desktop Runtime instalado, o se está corriendo esto
    fuera de Windows, como en desarrollo/pruebas en Linux/Mac)."""
    base = Path(shared_framework_dir)
    if not base.is_dir():
        return []
    versions = []
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        parsed = _parse_version(entry.name)
        if parsed is not None:
            versions.append(parsed)
    return versions


def _find_compatible_version(versions: list[tuple[int, int, int]]) -> tuple[int, int, int] | None:
    for version in versions:
        if _MIN_VERSION <= version <= _MAX_VERSION:
            return version
    return None


def ensure_dotnet_desktop_runtime_installed(installers_base_path: str) -> str:
    """Confirma que haya un Microsoft .NET Desktop Runtime dentro del
    rango que acepta Dell Command Update serie 5.x (ver
    `_MIN_VERSION`/`_MAX_VERSION`); si no lo hay, lo instala desde el
    instalador offline local en
    `<installers_base_path>\\DotNetDesktopRuntime\\...` (nunca lo
    descarga de internet -- mismo criterio que NetFX35, ver
    `app/netfx35_setup.py`). Es idempotente: si ya hay una versión
    compatible instalada, no hace nada más que reportarlo.

    Pensado para colgarse como paso `installer_type: "python"`, como
    instalador PRINCIPAL del ítem "dell_command" (el EXE real de DCU
    queda como `extra_step` después, ver `config/apps.json`).

    Lanza `DotNetDesktopRuntimeError` si no se pudo instalar -- por
    ejemplo, si el instalador offline no vino junto a los demás
    instaladores, o si el instalador en sí falló."""
    installed = _list_installed_versions(_SHARED_FRAMEWORK_DIR)
    compatible = _find_compatible_version(installed)
    if compatible is not None:
        version_str = ".".join(str(part) for part in compatible)
        return f".NET Desktop Runtime {version_str} ya estaba instalado (compatible con Dell Command Update)"

    installer_path = Path(ntpath.join(installers_base_path, *_INSTALLER_SUBPATH_PARTS))
    command = [str(installer_path), "/install", "/quiet", "/norestart"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise DotNetDesktopRuntimeError(".NET Desktop Runtime: tiempo de espera agotado.")
    except OSError as exc:
        raise DotNetDesktopRuntimeError(
            f".NET Desktop Runtime: no se pudo ejecutar el instalador ({installer_path}) -- {exc}"
        )

    if result.returncode not in _SUCCESS_CODES:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"No se pudo instalar .NET Desktop Runtime (código de salida {result.returncode})"
        if detail:
            msg += f" -- {detail}"
        raise DotNetDesktopRuntimeError(msg)

    if result.returncode == 3010:
        return ".NET Desktop Runtime instalado (pide reiniciar para terminar de aplicarse)"
    return ".NET Desktop Runtime instalado correctamente"
