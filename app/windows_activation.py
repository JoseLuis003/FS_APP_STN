"""Lógica de la acción "Activar Windows" del catálogo APPS (segunda
columna).

Porta el botón `btnCheckDomain_Click` del VB.NET original: antes de tocar
nada, confirma que el equipo esté unido al dominio `copaair.com` (la
licencia por volumen que usa Copa solo aplica a equipos corporativos
unidos al dominio) y, si lo está, configura la clave de producto y activa
Windows contra el KMS interno de Copa mediante `slmgr.vbs`:

    slmgr.vbs /ipk <PRODUCT_KEY>
    slmgr.vbs /ato

A diferencia del original, acá:

- El chequeo de dominio (`is_domain_joined()`) se hace vía PowerShell
  (`Get-CimInstance Win32_ComputerSystem` -> `PartOfDomain`), reutilizando
  el mismo patrón que `app/domain_join.py` (que ya invoca PowerShell para
  todo lo relacionado al dominio) en vez de una llamada P/Invoke o WMI
  directa desde .NET.
- Si el chequeo de dominio en sí no se puede completar (PowerShell no
  está disponible, se agota el tiempo de espera, etc.), se lanza un error
  aparte en vez de asumir silenciosamente "no está unido al dominio" — no
  queremos que un problema para verificar el estado se confunda con un
  equipo que de verdad no está unido.
- Si el equipo NO está unido al dominio, el VB.NET original cerraba toda
  la aplicación (`Application.Exit()`). Acá, en cambio, se lanza
  `WindowsActivationError` con un mensaje claro — se marca como error en
  la casilla, igual que cualquier otro ítem del catálogo, sin cerrar el
  resto de la pantalla (que puede tener otras casillas marcadas en la
  misma corrida).
- `slmgr.vbs` se invoca con `cscript.exe //nologo` (no con `wscript.exe`,
  que es lo que usaría un `Process.Start` sin más en .NET) para que la
  salida quede disponible como texto normal (stdout) en vez de aparecer
  como cuadros de diálogo emergentes -- igual de "desatendido" que el
  resto de esta app.
- Si `/ipk` falla, `/ato` nunca se intenta (a diferencia de un posible
  "seguir de largo" silencioso); el mensaje de error incluye la salida de
  `slmgr.vbs` tal cual, para que el técnico vea el motivo real (ej. una
  clave de producto rechazada, o sin conexión al KMS interno)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.domain_join import DOMAIN_NAME

# Ruta del script, relativa a `installers_base_path` -- mismo criterio que
# `CONTINGENCIA_SCRIPT_REL` en `app/shares_config_apply.py`. El VB.NET
# original apuntaba a una copia propia en la carpeta de instaladores
# ("C:\CM APPS\APPS\Scripts\slmgr.vbs") en vez del `slmgr.vbs` que ya trae
# Windows en `%WINDIR%\System32` -- se mantiene esa misma copia propia acá,
# por fidelidad con la infraestructura ya armada en esa carpeta.
SLMGR_SCRIPT_REL = r"Scripts\slmgr.vbs"

# Clave de activación por volumen configurada para las estaciones de Copa
# (KMS interno) -- la misma que usaba el VB.NET original.
PRODUCT_KEY = "KJ377-NTFV4-TT6DJ-7MC63-Y4G44"

_DOMAIN_CHECK_TIMEOUT_SECONDS = 30
_SLMGR_TIMEOUT_SECONDS = 60


class WindowsActivationError(Exception):
    """Error esperado al activar Windows (equipo no unido al dominio,
    script no encontrado, `slmgr.vbs` rechazó la clave o no pudo contactar
    al KMS interno, etc.). El mensaje ya viene listo para mostrárselo tal
    cual al técnico."""


def is_domain_joined(timeout: int = _DOMAIN_CHECK_TIMEOUT_SECONDS) -> bool:
    """Verifica si el equipo está unido al dominio `copaair.com` (en
    realidad, si está unido a CUALQUIER dominio -- igual que el
    `IsDomainJoined()` del VB.NET original, esta función no valida que sea
    específicamente ese dominio, solo que el equipo participe de uno).

    Lanza `WindowsActivationError` si el chequeo en sí no se pudo
    completar (PowerShell no disponible, tiempo de espera agotado, salida
    inesperada) -- eso es distinto de "no está unido", y no debe
    confundirse con ese caso."""
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "(Get-CimInstance -ClassName Win32_ComputerSystem).PartOfDomain",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise WindowsActivationError("No se encontró PowerShell en este equipo.") from exc
    except subprocess.TimeoutExpired as exc:
        raise WindowsActivationError("Tiempo de espera agotado al verificar si el equipo está unido al dominio.") from exc
    except OSError as exc:
        raise WindowsActivationError(f"No se pudo verificar si el equipo está unido al dominio: {exc}") from exc

    output = (result.stdout or "").strip()
    if output not in ("True", "False"):
        detail = (result.stderr or result.stdout or "").strip()
        raise WindowsActivationError(
            f"No se pudo determinar si el equipo está unido al dominio (salida inesperada: {detail!r})."
        )
    return output == "True"


def _run_slmgr_step(installers_base_path: str, args: list[str], timeout: int = _SLMGR_TIMEOUT_SECONDS) -> str:
    """Corre `slmgr.vbs <args>` vía `cscript //nologo` y devuelve su salida
    (stdout) si el proceso termina con código 0. Lanza `WindowsActivationError`
    si el script no existe, se agota el tiempo de espera, no se pudo
    ejecutar, o termina con un código de salida distinto de 0 -- en ese
    último caso, el mensaje incluye la salida real de `slmgr.vbs` (por
    ejemplo, el motivo por el que rechazó la clave de producto o no pudo
    contactar al KMS)."""
    script_path = Path(installers_base_path) / SLMGR_SCRIPT_REL
    if not script_path.exists():
        raise WindowsActivationError(f"No se encontró '{script_path}'.")

    cmd = ["cscript", "//nologo", str(script_path), *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise WindowsActivationError(f"Tiempo de espera agotado ejecutando 'slmgr.vbs {' '.join(args)}'.")
    except OSError as exc:
        raise WindowsActivationError(f"No se pudo ejecutar 'slmgr.vbs {' '.join(args)}': {exc}")

    if result.returncode != 0:
        detail = (result.stdout or result.stderr or "").strip()
        msg = f"'slmgr.vbs {' '.join(args)}' terminó con código de salida {result.returncode}"
        if detail:
            msg += f" -- {detail}"
        raise WindowsActivationError(msg)

    return result.stdout or ""


def run_windows_activation(installers_base_path: str) -> str:
    """Handler registrado como paso `installer_type: "python"`
    (`app/installer.py`, clave `"windows_activation"`). Confirma que el
    equipo esté unido al dominio y, si lo está, configura la clave de
    producto y activa Windows contra el KMS interno de Copa.

    Lanza `WindowsActivationError` si el equipo no está unido al dominio,
    o si cualquiera de los dos pasos de `slmgr.vbs` falla -- el llamador
    decide cómo mostrarlo (igual que el resto de errores de instalación)."""
    if not is_domain_joined():
        raise WindowsActivationError(
            f"Este equipo no está unido al dominio '{DOMAIN_NAME}' — la activación con la licencia "
            "por volumen de Copa solo aplica a equipos corporativos unidos al dominio."
        )

    _run_slmgr_step(installers_base_path, ["/ipk", PRODUCT_KEY])
    ato_output = _run_slmgr_step(installers_base_path, ["/ato"])

    detail = ato_output.strip() or "sin salida de slmgr.vbs"
    return f"Windows activado con la licencia por volumen de Copa (slmgr /ato: {detail})"
