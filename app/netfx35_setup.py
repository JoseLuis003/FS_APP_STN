"""Puerto a Python de `NetFX35\\INSTALL.cmd`. Usado en 2 lugares del
catálogo (ver `config/apps.json`):

1. Ítem independiente "NetFX35" (3ra columna) -- para correrlo a mano
   si hace falta, sin depender de otro ítem.
2. 1er paso (ahora el instalador PRINCIPAL) del ítem "bfirst" (2da
   columna) -- confirmado en una VM de prueba real que
   `BFirst\\setupbolapp.exe` exige tener .NET Framework 3.5 SP1
   instalado ANTES de poder instalarse (si no está, muestra el diálogo
   "Microsoft .NET Framework 3.5 SP1 needs to be installed for this
   installation to continue." y aborta con código de salida 1603).

El `.cmd` original:

    @echo off
    DISM /Online /Enable-Feature /FeatureName:NetFx3 /All /LimitAccess /Source:"C:\\CM APPS\\APPS\\NetFX35\\sources\\sxs"
    echo ========= PROCESO TERMINADO =========
    echo ===== CERRANDO AUTOMATICAMENTE ======
    ping -n 5 127.0.0.1 > nul
    Exit 0

.NET Framework 3.5 viene DESHABILITADO por defecto en instalaciones
limpias de Windows 10/11 (a diferencia de .NET 4.x, que sí viene
integrado de fábrica) -- es una "característica opcional de Windows"
que hay que habilitar explícitamente. El `.cmd` usa `/LimitAccess` +
`/Source:"...\\NetFX35\\sources\\sxs"` para instalarla SIEMPRE desde los
archivos locales que vienen junto a los demás instaladores, sin tocar
Windows Update -- necesario porque las estaciones de Copa muchas veces
no tienen salida a internet. `ensure_netfx35_installed()` arma el mismo
comando, resolviendo esa ruta de origen a partir de
`installers_base_path` (a diferencia de la mayoría de los pasos
"python" de este proyecto, este SÍ necesita ese argumento: sin él no
hay forma de ubicar la carpeta `sources\\sxs`).

Diferencia deliberada con el `.cmd` original: el `.cmd` siempre
terminaba con `Exit 0` sin mirar el código de salida real de DISM -- un
error real (ej. la carpeta `sources\\sxs` no viene junto a los demás
instaladores, o viene incompleta) quedaba enmascarado como "éxito", y
recién se notaba más tarde cuando `BFirst\\setupbolapp.exe` fallaba con
el críptico 1603 de siempre. Esta versión sí revisa el código de salida
de DISM y lanza `NetFx35SetupError` con el detalle si falla -- fail
loud, como el resto de la app (ver `SUCCESS_CODES` en
`app/installer.py`): el objetivo de correr esto automáticamente antes
de BFirst es justamente detectar el problema ACÁ, con un mensaje claro,
no dejar que se propague."""
from __future__ import annotations

import ntpath
import subprocess
import sys

# DISM puede tardar bastante si la fuente local está en un disco lento o
# si igual necesita revisar/completar archivos.
_TIMEOUT_SECONDS = 600

# Mismo criterio que el resto de la app para este código (ver
# SUCCESS_CODES en app/installer.py): 3010 = éxito, pide reiniciar para
# terminar de aplicarse.
_SUCCESS_CODES = {0, 3010}

# Carpeta de origen (relativa a `installers_base_path`) con los archivos
# de la característica NetFx3, igual que el `.cmd` original.
_SOURCE_SUBPATH_PARTS = ("NetFX35", "sources", "sxs")


class NetFx35SetupError(Exception):
    """Error esperado si no se pudo habilitar .NET Framework 3.5. El
    mensaje ya viene listo para mostrárselo tal cual al técnico."""


# Registro de un caso real de campo (log de instalación, 2026-08-19): en
# la MISMA corrida, "Windows-Updates-w11" instaló actualizaciones reales
# de Windows y terminó apenas 15 segundos antes de que "BFirst" (que
# depende de este módulo) intentara correr DISM -- DISM se quedó colgado
# los 10 minutos completos de `_TIMEOUT_SECONDS` hasta que
# `subprocess.run` lo mató por timeout. Volvió a pasar más tarde en la
# misma corrida con el ítem independiente "NetFX35" (36 minutos después,
# sin que nada más se hubiera instalado de por medio) -- descartando que
# fuera una finalización breve en curso: el equipo había quedado en
# **reinicio pendiente** por la actualización de Windows, y DISM
# `/Online /Enable-Feature` no puede tomar el lock del almacén de
# componentes (CBS) hasta que ese reinicio se complete, así que se queda
# esperando en vez de fallar rápido con un error claro.
#
# `_is_reboot_pending()` revisa los 3 indicadores estándar de Windows de
# que hay un reinicio pendiente (cualquiera de los 3 alcanza) ANTES de
# llamar a DISM, para fallar al instante con un mensaje claro en vez de
# colgarse otra vez 10 minutos con el mismo resultado:
#
# - `...\\Component Based Servicing\\RebootPending`: existe SOLO si una
#   operación de CBS (la misma que usa DISM para /Enable-Feature) dejó al
#   equipo esperando un reinicio para completarse -- si esta clave existe,
#   DISM se queda esperando el lock del CBS hasta que el equipo reinicia.
# - `...\\WindowsUpdate\\Auto Update\\RebootRequired`: existe cuando
#   Windows Update instaló algo que requiere reiniciar para terminar de
#   aplicarse -- justo el caso real de arriba.
# - `...\\Session Manager\\PendingFileRenameOperations`: un VALOR (no solo
#   la existencia de la clave) con archivos pendientes de renombrar o
#   borrar al reiniciar.
#
# Fuente: "Determine Pending Reboot Status -- PowerShell Style!"
# (Microsoft Scripting Blog/DevBlogs), que documenta estos mismos 3
# indicadores como la forma estándar de detectar un reinicio pendiente en
# Windows: https://devblogs.microsoft.com/scripting/determine-pending-reboot-statuspowershell-style-part-1/
_REBOOT_PENDING_KEY_CHECKS = (
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending", None),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired", None),
)
_PENDING_FILE_RENAME_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager"
_PENDING_FILE_RENAME_VALUE = "PendingFileRenameOperations"


def _is_reboot_pending() -> bool:
    """Revisa si Windows quedó en "reinicio pendiente" (ver el comentario
    de arriba) -- devuelve `False` sin lanzar nada fuera de Windows (no
    hay `winreg`) o si no se pudo leer alguna de las claves por cualquier
    motivo (mismo criterio conservador que el resto de la app para datos
    "informativos" del equipo, ver `app/report.py`: mejor asumir que no
    hay reinicio pendiente y dejar que DISM lo intente, que bloquear la
    instalación por un error al leer el registro)."""
    if sys.platform != "win32":
        return False
    import winreg

    for key_path, _unused in _REBOOT_PENDING_KEY_CHECKS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path):
                return True
        except OSError:
            continue

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _PENDING_FILE_RENAME_KEY) as key:
            value, _value_type = winreg.QueryValueEx(key, _PENDING_FILE_RENAME_VALUE)
            if value:
                return True
    except OSError:
        pass

    return False


def _build_dism_command(installers_base_path: str) -> list[str]:
    # `ntpath.join` (no `os.path.join`/`pathlib.Path`) a propósito: arma
    # SIEMPRE una ruta con separador "\\", sin importar en qué SO corra
    # este código -- necesario porque `installers_base_path` es una ruta
    # de Windows (ej. "C:\\CM APPS\\APPS") aunque se desarrolle y pruebe
    # en Linux/Mac, donde `pathlib.Path` la trataría como ruta POSIX.
    source_dir = ntpath.join(installers_base_path, *_SOURCE_SUBPATH_PARTS)
    return [
        "dism.exe",
        "/Online",
        "/Enable-Feature",
        "/FeatureName:NetFx3",
        "/All",
        "/LimitAccess",
        f"/Source:{source_dir}",
    ]


def ensure_netfx35_installed(installers_base_path: str) -> str:
    """Habilita ".NET Framework 3.5 (incluye .NET 2.0 y 3.0)" vía DISM,
    usando como fuente los archivos locales en
    `<installers_base_path>\\NetFX35\\sources\\sxs` (nunca Windows
    Update) -- es idempotente: si ya estaba habilitada, DISM lo reporta
    como éxito igual, sin reinstalar nada.

    Pensado para colgarse como paso `installer_type: "python"`, ya sea
    como instalador principal (ítems "NetFX35" y "bfirst") o como
    `extra_step` de algún otro ítem que también dependa de .NET 3.5.

    Lanza `NetFx35SetupError` si DISM falla -- por ejemplo, si la
    carpeta `NetFX35\\sources\\sxs` no vino junto a los demás
    instaladores, o si el equipo tampoco tiene acceso a Windows Update
    como alternativa (DISM necesita alguna de las 2 fuentes) -- o, ANTES
    de intentar correrlo siquiera, si el equipo quedó con un reinicio
    pendiente (ver `_is_reboot_pending` y el caso real documentado ahí):
    correr DISM en ese estado no falla rápido, se queda colgado hasta
    agotar `_TIMEOUT_SECONDS` (10 minutos) esperando el lock del CBS que
    no se libera hasta que el equipo reinicia -- caso real de campo
    confirmado dos veces en la misma corrida (BFirst y NetFX35
    independiente), justo después de que "Windows-Updates-w11" instalara
    actualizaciones reales de Windows."""
    if _is_reboot_pending():
        raise NetFx35SetupError(
            "Reinicio Pendiente: hay un reinicio de Windows pendiente (probablemente por una "
            "actualización que se acaba de instalar) -- DISM no puede habilitar .NET Framework 3.5 "
            "hasta que el equipo reinicie. Reinicia el equipo y vuelve a marcar esta casilla."
        )

    command = _build_dism_command(installers_base_path)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise NetFx35SetupError("DISM (.NET Framework 3.5): tiempo de espera agotado.")
    except OSError as exc:
        raise NetFx35SetupError(f"DISM (.NET Framework 3.5): no se pudo ejecutar -- {exc}")

    if result.returncode not in _SUCCESS_CODES:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"No se pudo habilitar .NET Framework 3.5 (DISM terminó con código {result.returncode})"
        if detail:
            msg += f" -- {detail}"
        raise NetFx35SetupError(msg)

    if result.returncode == 3010:
        return ".NET Framework 3.5 habilitado vía DISM (pide reiniciar para terminar de aplicarse)"
    return ".NET Framework 3.5 ya estaba habilitado (o se habilitó correctamente) vía DISM"
