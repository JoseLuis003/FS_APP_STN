"""Instala "RSAT: Active Directory Domain Services and Lightweight
Directory Services Tools" (el snap-in "Active Directory Users and
Computers", `dsa.msc`, y el módulo de PowerShell `ActiveDirectory`) vía
DISM, usando como fuente los archivos locales que vienen junto a los
demás instaladores -- nunca Windows Update, mismo criterio que
`app/netfx35_setup.py`: muchas estaciones de Copa no tienen salida a
internet, y RSAT normalmente NO viene instalado de fábrica en un equipo
recién provisionado (por eso `app/domain_join.py` usa ADSI en vez de
`Set-ADComputer`/`Get-ADOrganizationalUnit` para todo lo que hace la
pantalla DOMINIO -- este módulo es un ítem aparte del catálogo, para
dejar disponibles esas herramientas en el equipo por si el técnico las
necesita más adelante, no algo de lo que dependa DOMINIO).

Pedido explícito: la ruta de origen (`-Source`/`/Source:`) NO debe quedar
fija a `C:\\...` -- se arma en tiempo de ejecución a partir de
`installers_base_path` (la misma ruta que ya resuelve dinámicamente
`app/config.py` según desde dónde se abrió `FS_APP_STN.exe`, sea el
disco `C:` o una unidad extraíble/USB con otra letra), igual que
`netfx35_setup.py` arma la ruta de origen de NetFx3.

Los archivos de origen (los `.cab` de la capability "RSAT: Active
Directory DS/LDS Tools", del ISO oficial de Microsoft "Languages and
Optional Features") deben venir en
`<installers_base_path>\\RSAT-ActiveDirectory-Offline\\` -- una carpeta
más junto a las demás (`NetFX35\\`, `AdobeReader\\`, etc.), NO la carpeta
completa de 5GB del ISO: alcanza con el paquete base (`~amd64~~.cab` y
`~wow64~~.cab`) más el/los paquete(s) de idioma que coincidan con el
idioma de Windows de los equipos de Copa."""
from __future__ import annotations

import ntpath
import subprocess
import sys

# DISM puede tardar varios minutos revisando/copiando los .cab, aunque
# sean pocos MB -- mismo orden de magnitud que netfx35_setup.py.
_TIMEOUT_SECONDS = 600

# Mismo criterio que el resto de la app para este código (ver
# SUCCESS_CODES en app/installer.py): 3010 = éxito, pide reiniciar.
_SUCCESS_CODES = {0, 3010}

# Nombre de la "capability" que instala esto -- el mismo que usaría
# `Add-WindowsCapability -Name ...` en PowerShell, pero acá se usa DISM
# directo (sin depender de un módulo de PowerShell aparte), igual que
# `netfx35_setup.py` usa `dism.exe /Enable-Feature` en vez de un cmdlet.
_CAPABILITY_NAME = "Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0"

# Carpeta de origen (relativa a `installers_base_path`) con los .cab de
# esta capability -- ver el docstring de arriba para qué archivos debe
# tener (NO la carpeta completa de 5GB del ISO "Languages and Optional
# Features", solo el paquete base + los idiomas necesarios).
_SOURCE_SUBPATH_PARTS = ("RSAT-ActiveDirectory-Offline",)


class RsatSetupError(Exception):
    """Error esperado si no se pudo instalar RSAT (AD DS/LDS Tools). El
    mensaje ya viene listo para mostrárselo tal cual al técnico."""


def _is_reboot_pending() -> bool:
    """Mismo chequeo que `app/netfx35_setup.py` (ver ahí el caso real de
    campo que lo motivó) -- DISM usa el mismo almacén de componentes
    (CBS) tanto para `/Enable-Feature` como para `/Add-Capability`, así
    que corre el mismo riesgo de quedarse colgado hasta agotar
    `_TIMEOUT_SECONDS` si el equipo quedó en reinicio pendiente, en vez
    de fallar rápido con un mensaje claro."""
    if sys.platform != "win32":
        return False
    import winreg

    reboot_pending_keys = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    )
    for key_path in reboot_pending_keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path):
                return True
        except OSError:
            continue

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager"
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, "PendingFileRenameOperations")
            if value:
                return True
    except OSError:
        pass

    return False


def _build_dism_command(installers_base_path: str) -> list[str]:
    # `ntpath.join` (no `os.path.join`/`pathlib.Path`) a propósito: arma
    # SIEMPRE una ruta con separador "\\", sin importar en qué SO corra
    # este código -- mismo motivo que `netfx35_setup.py`: se desarrolla y
    # prueba en Linux/Mac, donde `pathlib.Path` trataría
    # `installers_base_path` (una ruta de Windows) como ruta POSIX.
    source_dir = ntpath.join(installers_base_path, *_SOURCE_SUBPATH_PARTS)
    return [
        "dism.exe",
        "/Online",
        "/Add-Capability",
        f"/CapabilityName:{_CAPABILITY_NAME}",
        f"/Source:{source_dir}",
        "/LimitAccess",
    ]


def ensure_rsat_ad_tools_installed(installers_base_path: str) -> str:
    """Instala "RSAT: Active Directory DS/LDS Tools" vía DISM, usando
    como fuente los archivos locales en
    `<installers_base_path>\\RSAT-ActiveDirectory-Offline` (nunca
    Windows Update -- ver `/LimitAccess` arriba). Es idempotente: si ya
    estaba instalado, DISM lo reporta como éxito igual, sin reinstalar
    nada.

    Pensado para colgarse como ítem del catálogo (`installer_type:
    "python"`, ver `config/apps.json`).

    Lanza `RsatSetupError` si DISM falla -- por ejemplo, si la carpeta
    `RSAT-ActiveDirectory-Offline` no vino junto a los demás
    instaladores, si le falta el paquete del idioma de Windows del
    equipo, o si el equipo quedó con un reinicio pendiente (ver
    `_is_reboot_pending`, mismo caso real que documenta
    `netfx35_setup.py`: correr DISM en ese estado no falla rápido, se
    queda colgado hasta agotar `_TIMEOUT_SECONDS` esperando el lock del
    CBS)."""
    if _is_reboot_pending():
        raise RsatSetupError(
            "Reinicio Pendiente: hay un reinicio de Windows pendiente (probablemente por una "
            "actualización que se acaba de instalar) -- DISM no puede instalar RSAT hasta que el "
            "equipo reinicie. Reinicia el equipo y vuelve a marcar esta casilla."
        )

    command = _build_dism_command(installers_base_path)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise RsatSetupError("DISM (RSAT AD DS/LDS Tools): tiempo de espera agotado.")
    except OSError as exc:
        raise RsatSetupError(f"DISM (RSAT AD DS/LDS Tools): no se pudo ejecutar -- {exc}")

    if result.returncode not in _SUCCESS_CODES:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"No se pudo instalar RSAT (AD DS/LDS Tools) (DISM terminó con código {result.returncode})"
        if detail:
            msg += f" -- {detail}"
        raise RsatSetupError(msg)

    if result.returncode == 3010:
        return "RSAT (AD DS/LDS Tools) instalado vía DISM (pide reiniciar para terminar de aplicarse)"
    return "RSAT (AD DS/LDS Tools) ya estaba instalado (o se instaló correctamente) vía DISM"
