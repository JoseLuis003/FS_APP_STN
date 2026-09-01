"""Puerto a Python de `Desktop-Central/UEMSAgent/Agent_Install.ps1` (ítem
"Manage Engine" del catálogo APPS, 3ra columna, id `manage_engine`).

Reporte real de campo: el ítem terminaba con "OK" (código de salida 0) sin
instalar nada. La causa, revisando el `.ps1` original:

1. `Start-Process msiexec.exe -Wait -ArgumentList '...'` corre `msiexec`
   pero NUNCA revisa su código de salida real (no usa `-PassThru` ni mira
   `.ExitCode`) -- pase lo que pase con la instalación (ruta no
   encontrada, error de MSI, lo que sea), el script sigue de largo hasta
   `Write-Output "¡INSTALADO!"` / `Exit 0` igual. El código de salida que
   ve `InstallWorker` (`app/installer.py`) es el de `powershell.exe`
   ejecutando el script -- no el de `msiexec.exe` -- así que siempre daba
   0, aunque `msiexec` hubiera fallado.
2. Las 4 rutas que usa `msiexec` (`.msi`, `.mst`, los 2 `.crt`) estaban
   escritas fijas a `C:\\CM APPS\\APPS\\...` -- mismo bug de fondo que
   tenía "Microsoft Office 365" antes de corregirse (ver
   `get_default_installers_base_path()`/`load_settings()` en
   `app/config.py`): si la app corre desde una USB con otra letra de
   unidad, esa ruta fija no existe.

Esta versión corrige los 2 problemas: arma las rutas dinámicamente a
partir de `installers_base_path` (como el resto del catálogo) y SÍ revisa
el código de salida real de `msiexec` -- fail loud si no es de éxito (0 o
3010, mismo criterio que el resto de la app, ver `SUCCESS_CODES` en
`app/installer.py`), leyendo el log propio de `msiexec` (`/lv`, igual que
el original) para dar un detalle real del error en vez de un código
críptico sin contexto.

Las 2 reglas de firewall para "Zoho Assist" (`New-NetFirewallRule` en el
original, acá vía `netsh advfirewall`, sin depender de PowerShell) se
mantienen como paso BEST-EFFORT, igual que el comportamiento real del
script original: `New-NetFirewallRule` ahí tampoco revisaba error alguno
(`$ErrorActionPreference` nunca se puso en "Stop"), así que si fallaba, el
script de todos modos seguía y reportaba éxito --酸acá se preserva esa
misma tolerancia a propósito (Zoho Assist es soporte remoto complementario,
no el agente en sí), pero informando en el detalle final si alguna de las
2 reglas no se pudo agregar, en vez de quedar en silencio total como
antes."""
from __future__ import annotations

import ntpath
import subprocess
import time
from pathlib import Path

# Evita que Windows le abra su propia ventana de consola a `msiexec.exe`/
# `netsh.exe` (quedaría en blanco y parecería colgado) -- ver la
# explicación completa en `NO_CONSOLE_WINDOW`, `app/installer.py`.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# msiexec puede tardar varios minutos -- mismo orden de magnitud que los
# demás pasos MSI/DISM del catálogo.
_MSIEXEC_TIMEOUT_SECONDS = 600
_NETSH_TIMEOUT_SECONDS = 30

# Mismo criterio que el resto de la app para este código (ver
# SUCCESS_CODES en app/installer.py): 3010 = éxito, pide reiniciar.
_SUCCESS_CODES = {0, 3010}

# Carpeta de origen (relativa a `installers_base_path`) con el .msi, el
# .mst y los 2 certificados -- igual que el `.ps1` original, pero armada
# en tiempo de ejecución en vez de fija a `C:\...`.
_SOURCE_SUBPATH_PARTS = ("Desktop-Central", "UEMSAgent")

_MSI_FILE_NAME = "UEMSAgent.msi"
_TRANSFORM_FILE_NAME = "UEMSAgent.mst"
_SERVER_CRT_FILE_NAME = "DMRootCA-Server.crt"
_DS_CRT_FILE_NAME = "DMRootCA.crt"
_LOG_FILE_NAME = "Agentinstalllog.txt"

# Pausa después de que `msiexec` termina, antes de agregar las reglas de
# firewall -- heredada tal cual del `.ps1` original (`Start-Sleep -Seconds
# 20`); no se verificó de forma independiente si el agente realmente la
# necesita para terminar de registrar el servicio, se preserva por las
# dudas (no cuesta nada, y así este puerto no cambia el timing del
# original).
_POST_INSTALL_SLEEP_SECONDS = 20

# Ubicación fija (no depende de `installers_base_path`: es donde el MSI
# instala el agente, en el disco del equipo, no en los medios de
# instalación) del ejecutable de Zoho Assist para el que se abren los 2
# puertos -- igual que el `.ps1` original.
_ZOHO_ASSIST_AGENT_PATH = r"C:\Program Files (x86)\ZohoMeeting\agent.exe"
_ZOHO_ASSIST_RULE_NAME = "Zoho Assist"
_ZOHO_ASSIST_RULE_DESCRIPTION = "Allow Zoho Assist Agent"


class ManageEngineSetupError(Exception):
    """Error esperado si no se pudo instalar el agente de Manage Engine
    (UEMSAgent/Desktop Central). El mensaje ya viene listo para
    mostrárselo tal cual al técnico."""


def _build_msiexec_command(source_dir: str, log_path: str) -> list[str]:
    # `ntpath.join` (no `pathlib.Path`) a propósito -- mismo motivo que
    # `netfx35_setup.py`/`rsat_setup.py`: `installers_base_path` es una
    # ruta de Windows aunque esto se desarrolle y pruebe en Linux/Mac.
    msi_path = ntpath.join(source_dir, _MSI_FILE_NAME)
    server_crt_path = ntpath.join(source_dir, _SERVER_CRT_FILE_NAME)
    ds_crt_path = ntpath.join(source_dir, _DS_CRT_FILE_NAME)
    return [
        "msiexec.exe",
        "/I", msi_path,
        # `TRANSFORMS` se deja como nombre de archivo SUELTO (sin ruta),
        # igual que el .ps1 original -- Windows Installer lo resuelve
        # relativo a la carpeta del propio .msi automáticamente. Cada
        # elemento de esta lista es un argumento aparte (no una sola
        # cadena armada a mano), así que no hace falta encomillar nada
        # por más que las rutas tengan espacios (a diferencia del
        # `-ArgumentList` de una sola cadena que usaba `Start-Process`).
        f"TRANSFORMS={_TRANSFORM_FILE_NAME}",
        "ENABLESILENT=yes",
        "/passive",
        "REBOOT=ReallySuppress",
        "INSTALLSOURCE=Manual",
        f"SERVER_ROOT_CRT={server_crt_path}",
        f"DS_ROOT_CRT={ds_crt_path}",
        "/lv", log_path,
    ]


def _run_msiexec(source_dir: str, log_path: str) -> int:
    command = _build_msiexec_command(source_dir, log_path)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_MSIEXEC_TIMEOUT_SECONDS,
            creationflags=_NO_CONSOLE_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise ManageEngineSetupError("msiexec (UEMSAgent): tiempo de espera agotado.")
    except OSError as exc:
        raise ManageEngineSetupError(f"msiexec (UEMSAgent): no se pudo ejecutar -- {exc}")

    if result.returncode not in _SUCCESS_CODES:
        detail = _read_log_tail(log_path)
        if not detail:
            detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"No se pudo instalar el agente de Manage Engine (msiexec terminó con código {result.returncode})"
        if detail:
            msg += f" -- {detail}"
        raise ManageEngineSetupError(msg)

    return result.returncode


def _read_log_tail(log_path: str, max_chars: int = 800) -> str:
    """Lee los últimos `max_chars` caracteres del log de `msiexec` (`/lv`)
    -- el detalle real de un fallo de MSI suele estar cerca del final del
    log (mensaje "Product: ... -- Installation failed" / "Return Value
    3"), no al principio. Devuelve cadena vacía si el archivo no existe o
    no se puede leer (ej. si `msiexec` ni siquiera llegó a crearlo) -- en
    ese caso el llamador cae de vuelta a stdout/stderr de `msiexec`
    mismo."""
    try:
        raw = Path(log_path).read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""

    # Los logs de MSI (`/lv`) vienen en UTF-16 CON BOM en instalaciones
    # recientes de Windows Installer -- se detecta por el BOM (2 primeros
    # bytes) en vez de "probar" UTF-16 a ciegas primero: decodificar
    # bytes que en realidad son UTF-8/ANSI como si fueran UTF-16 con
    # `errors="ignore"` NO lanza excepción, solo produce texto
    # amontonado/ilegible (`errors="ignore"` traga el problema en vez de
    # avisarlo) -- así que "probar UTF-16 primero y seguir si sale texto
    # no vacío" quedaba mal para logs viejos en ANSI/UTF-8: nunca caía al
    # resto de encodings porque UTF-16 "ignore" casi siempre deja *algo*
    # no vacío, aunque sea basura.
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", errors="ignore").strip()
        if text:
            return text[-max_chars:]

    # Sin BOM de UTF-16: se intenta UTF-8 de forma ESTRICTA (no
    # "ignore") -- así, si el log realmente viene en UTF-16 sin BOM (muy
    # raro) o en algún ANSI de un solo byte, decodificarlo como UTF-8
    # falla de verdad (bytes inválidos) en vez de dar basura silenciosa,
    # y recién ahí se cae al último recurso.
    try:
        text = raw.decode("utf-8", errors="strict").strip()
        if text:
            return text[-max_chars:]
    except UnicodeDecodeError:
        pass

    # Último recurso: latin-1 nunca lanza (cubre los 256 valores de un
    # byte), por lo que sirve de red de seguridad final para logs ANSI
    # viejos que no son UTF-8 válido.
    text = raw.decode("latin-1", errors="ignore").strip()
    return text[-max_chars:] if text else ""


def _add_firewall_rule(program_path: str, protocol: str) -> str | None:
    """Agrega una regla de firewall entrante para `program_path` (mismo
    efecto que `New-NetFirewallRule` en el `.ps1` original, sin depender
    de PowerShell) -- best-effort a propósito, igual que el original (ver
    docstring del módulo): devuelve `None` si salió bien, o un texto corto
    con el detalle si falló, SIN lanzar excepción (una regla de firewall
    que no se pudo agregar no debe tumbar la instalación del agente en
    sí)."""
    command = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={_ZOHO_ASSIST_RULE_NAME}",
        "dir=in",
        "action=allow",
        f"program={program_path}",
        "enable=yes",
        "profile=domain,private,public",
        f"protocol={protocol}",
        f"description={_ZOHO_ASSIST_RULE_DESCRIPTION}",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_NETSH_TIMEOUT_SECONDS,
            creationflags=_NO_CONSOLE_WINDOW,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"regla {protocol}: no se pudo ejecutar netsh -- {exc}"

    if result.returncode != 0:
        detail = (result.stdout or result.stderr or "").strip()[:200]
        return f"regla {protocol}: netsh terminó con código {result.returncode}{f' -- {detail}' if detail else ''}"
    return None


def apply_manage_engine_setup(installers_base_path: str) -> str:
    """Instala el agente de Manage Engine (UEMSAgent/Desktop Central) vía
    `msiexec`, usando como origen los archivos locales en
    `<installers_base_path>\\Desktop-Central\\UEMSAgent\\` (nunca
    internet), y agrega las 2 reglas de firewall de "Zoho Assist"
    (best-effort, ver `_add_firewall_rule`).

    Pensado para colgarse como paso `installer_type: "python"` (ver
    `config/apps.json`, ítem `manage_engine`).

    Lanza `ManageEngineSetupError` si `msiexec` termina con un código que
    no es de éxito (0 o 3010) -- a diferencia del `.ps1` original, que
    nunca revisaba esto y por eso el ítem se reportaba como éxito aunque
    no se hubiera instalado nada."""
    source_dir = ntpath.join(installers_base_path, *_SOURCE_SUBPATH_PARTS)
    log_path = ntpath.join(source_dir, _LOG_FILE_NAME)

    returncode = _run_msiexec(source_dir, log_path)

    time.sleep(_POST_INSTALL_SLEEP_SECONDS)

    firewall_issues = [
        issue
        for issue in (
            _add_firewall_rule(_ZOHO_ASSIST_AGENT_PATH, "UDP"),
            _add_firewall_rule(_ZOHO_ASSIST_AGENT_PATH, "TCP"),
        )
        if issue
    ]

    detail = "UEMSAgent instalado" + (" (requiere reiniciar)" if returncode == 3010 else "")
    detail += "; reglas de firewall de Zoho Assist agregadas (UDP y TCP)"
    if firewall_issues:
        detail += f" -- ATENCIÓN, {'; '.join(firewall_issues)}"
    return detail
