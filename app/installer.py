"""Motor de instalación desatendida.

Ejecuta cada instalador seleccionado en un hilo de trabajo (QThread) para no
congelar la interfaz, y reporta progreso/resultado mediante señales Qt.
"""
from __future__ import annotations

import datetime
import os
import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from app.appshell_post_install import run_appshell_post_install
from app.branding_setup import apply_bginfo_registration, apply_branding_setup
from app.config import DEFAULT_STEP_TIMEOUT_SECONDS, AppItem, LOGS_DIR
from app.dotnet_desktop_runtime_setup import ensure_dotnet_desktop_runtime_installed
from app.manage_engine_setup import apply_manage_engine_setup
from app.netfx35_setup import ensure_netfx35_installed
from app.rsat_setup import ensure_rsat_ad_tools_installed
from app.sap_gui_setup import apply_sap_gui_setup, ensure_no_reboot_pending_for_sap_gui
from app.shares_setup import run_ltp_shares_post_install
from app.shortcuts import (
    copy_bfirst_assets_and_shortcut,
    copy_mto_assets_and_shortcuts,
    copy_stn_assets_and_shortcuts,
    create_server_access_shortcut,
)
from app.vpn_setup import apply_vpn_setup
from app.windows_activation import run_windows_activation
from app.workstation_settings import apply_workstation_settings

# Códigos de salida que se consideran éxito además de 0.
# 3010 = éxito, requiere reinicio (común en instaladores MSI / Windows Update).
# 1638 = ERROR_PRODUCT_VERSION, código estándar del Windows Installer: "ya
# hay otra versión de este producto instalada" -- típico en paquetes
# vcredist (Visual C++ Redistributable) cuando ya está presente una versión
# igual o más nueva. No es un fallo real: no hay nada que instalar, así que
# se trata como éxito en vez de detener la cola.
SUCCESS_CODES = {0, 3010, 1638}

# Reporte real de campo: durante "Windows-Updates-w11" (y en general
# cualquier paso "script"/"msu", ej. el hotfix .msu de REGISTRO EN AD),
# el técnico ve una ventana de PowerShell en pantalla completa/azul,
# SIN nada escrito en ella, durante todo el paso -- y lo interpreta como
# que la instalación se colgó, aunque FS_APP_STN.exe (tapada detrás)
# YA muestra "Instalando: <ítem>..." con su propia barra de progreso
# (ver `MainWindow._on_item_started`/`DominioWindow`, que se actualizan
# apenas arranca cada paso).
#
# La causa: `subprocess.run(...)` de más abajo lanza una herramienta de
# consola (powershell.exe, wusa.exe, cmd.exe/.bat) desde FS_APP_STN.exe,
# que es una app SIN consola propia (PyInstaller `--windowed`). Windows
# le crea una consola NUEVA y VISIBLE a ese proceso hijo aunque su
# stdout/stderr ya estén redirigidos a un pipe (`capture_output=True`)
# -- la redirección de stdout/stderr y la existencia de la ventana de
# consola son dos cosas independientes; hace falta pedir explícitamente
# que Windows NO cree esa ventana.
#
# `NO_CONSOLE_WINDOW` se agrega como `creationflags` a CADA
# `subprocess.run(...)` de la app (no solo acá -- ver el mismo patrón en
# `app/netfx35_setup.py`, `app/rsat_setup.py`, `app/domain_join.py`, y
# el resto de módulos que lanzan una herramienta de línea de comandos)
# para que el técnico solo vea la interfaz de FS_APP_STN mientras el
# paso corre en segundo plano, sin ninguna ventana en blanco que
# confunda. NO afecta a instaladores con interfaz gráfica propia (EXE/
# MSI sin instalación silenciosa, ej. Dell Command Update, DELL
# Optimizer, DELL OwnerTag): `CREATE_NO_WINDOW` solo suprime la consola
# de procesos de "subsistema de consola" -- una app gráfica (subsistema
# Windows/GUI) no usa consola en absoluto, así que este flag no le
# afecta ni oculta su ventana propia.
#
# `getattr(subprocess, "CREATE_NO_WINDOW", 0)` en vez de la constante
# directa porque `CREATE_NO_WINDOW` solo existe en el módulo
# `subprocess` en Windows -- acceder al atributo directo
# (`subprocess.CREATE_NO_WINDOW`) lanzaría `AttributeError` en
# Linux/Mac, donde se desarrolla y prueba esta app. Con
# `getattr(..., 0)`, fuera de Windows queda en 0 -- el mismo valor por
# defecto que ya tiene `creationflags` cuando no se pasa, así que no
# cambia nada fuera de Windows (ni en las pruebas).
NO_CONSOLE_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Detecta una ruta absoluta de Windows ("C:\..." / "C:/..." / "\\servidor\...")
# sin depender de `Path.is_absolute()` -- esa función se comporta distinto
# según el sistema operativo donde corre el código (en Linux, que es donde se
# desarrolla y prueba esta app, "C:\Program Files\..." NO se considera
# absoluta), y acá necesitamos detectarla igual sin importar en qué SO se
# esté ejecutando este chequeo.
_ABS_WINDOWS_PATH_RE = re.compile(r"^([A-Za-z]:[\\/]|\\\\)")


def _is_absolute_installer_path(installer_rel: str) -> bool:
    return bool(_ABS_WINDOWS_PATH_RE.match(installer_rel))


def _resolve_installer_path(base: Path, installer_rel: str) -> Path:
    """Resuelve la ruta de UN paso: si `installer_rel` ya es una ruta
    absoluta de Windows (ej. una app que quedó instalada en
    `C:\\Program Files\\...` por un paso anterior y solo hace falta abrirla,
    no reinstalarla), se usa tal cual, sin unirla a `base`. Si es relativa
    (el caso normal), se une a `base` como siempre."""
    if _is_absolute_installer_path(installer_rel):
        return Path(installer_rel)
    return base / installer_rel


# Registro de pasos "python" (`installer_type: "python"`): a diferencia de
# exe/msi/msu/script/open, este tipo de paso no apunta a un archivo -- el
# campo "installer" del paso es una CLAVE que identifica qué función de
# Python correr (ver `app/shares_setup.py` y `app/appshell_post_install.py`).
# Se usa para lógica que ya no tiene sentido mantener como un .bat/.ps1
# suelto en la carpeta de instaladores (más aún si Seguridad de Copa
# bloquea directamente la ejecución de .bat, como pasa con AppShell), sino
# que se porta directo a código Python empaquetado dentro de la app (con
# su propio manejo de errores por paso, en vez de depender de un solo
# código de salida de todo un script).
#
# Cada handler registrado acá recibe `installers_base_path` como único
# argumento posicional (ver el `handler(self.installers_base_path)` más
# abajo, en `InstallWorker.run`) -- lo uses o no (p. ej.
# `run_ltp_shares_post_install` lo ignora, porque sus pasos no dependen de
# la carpeta de instaladores; `run_appshell_post_install` sí lo necesita,
# para ubicar los accesos directos que hay que copiar).
#
# Armado adentro de una función (en vez de un dict a nivel de módulo) a
# propósito: así, cada llamada resuelve estas funciones como variables
# globales de este módulo EN ESE MOMENTO -- si algo las reemplaza (p. ej.
# `mock.patch("app.installer.run_ltp_shares_post_install", ...)` en una
# prueba), la próxima llamada ya ve el reemplazo. Con un dict armado una
# sola vez al importar el módulo, quedaría "congelada" la referencia
# original de forma permanente, inmune a cualquier patch posterior.
def _python_step_handlers() -> dict:
    return {
        "ltp_shares_post_install": run_ltp_shares_post_install,
        "appshell_post_install": run_appshell_post_install,
        "windows_activation": run_windows_activation,
        "branding_setup": apply_branding_setup,
        "stn_shortcuts": copy_stn_assets_and_shortcuts,
        "server_access_shortcut": create_server_access_shortcut,
        "workstation_settings": apply_workstation_settings,
        "bginfo_registration": apply_bginfo_registration,
        "mto_shortcuts": copy_mto_assets_and_shortcuts,
        "bfirst_assets": copy_bfirst_assets_and_shortcut,
        "sap_gui_setup": apply_sap_gui_setup,
        "sap_gui_reboot_check": ensure_no_reboot_pending_for_sap_gui,
        "vpn_setup": apply_vpn_setup,
        "netfx35_setup": ensure_netfx35_installed,
        "dotnet_desktop_runtime_setup": ensure_dotnet_desktop_runtime_installed,
        "rsat_ad_tools_setup": ensure_rsat_ad_tools_installed,
        "manage_engine_setup": apply_manage_engine_setup,
    }


def _open_file(path: Path) -> None:
    """Abre `path` con la aplicación asociada en Windows (un PDF, o un .exe
    ya instalado que el técnico debe usar manualmente) -- equivalente a
    hacerle doble clic en el Explorador. Envuelto en su propia función para
    poder simularlo (mock) en pruebas, ya que `os.startfile` solo existe en
    Windows y no en Linux/Mac, donde se desarrolla y prueba esta app."""
    os.startfile(str(path))  # type: ignore[attr-defined]


def _resolve_step_command(installer_type: str, silent_args: str, installer_path: Path) -> list[str]:
    """Arma la línea de comandos de UN paso según su tipo de instalador."""
    if installer_type == "msi":
        cmd = ["msiexec", "/i", str(installer_path)]
    elif installer_type == "msu":
        # Paquetes de Windows Update independientes (.msu) no son
        # ejecutables ni se asocian a un intérprete como .ps1/.bat -- hay
        # que invocarlos explícitamente con wusa.exe (ej. REGISTRO EN AD).
        cmd = ["wusa", str(installer_path)]
    elif installer_type == "script":
        # Scripts .ps1/.bat/.cmd
        if installer_path.suffix.lower() == ".ps1":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer_path)]
        else:
            cmd = [str(installer_path)]
    else:
        # exe genérico
        cmd = [str(installer_path)]
    if silent_args:
        cmd += silent_args.split()
    return cmd


def build_command(item: AppItem, installer_path: Path) -> list[str]:
    """Arma la línea de comandos del PRIMER paso de `item` (mantiene esta
    firma por compatibilidad con código/tests existentes). Para ítems con
    pasos adicionales (`item.extra_steps`), ver `_iter_steps` y
    `InstallWorker.run`, que corren cada paso en secuencia."""
    return _resolve_step_command(item.installer_type, item.silent_args, installer_path)


def _iter_steps(item: AppItem):
    """Genera (installer_relativo, silent_args, installer_type,
    exit_code_messages, continue_on_error, success_codes, timeout_seconds)
    para el paso principal de `item` y luego cada uno de
    `item.extra_steps`, en el mismo orden en que deben ejecutarse.
    `exit_code_messages` (ver `AppItem` en app/config.py) es un dict
    {código_de_salida_como_string: mensaje} con mensajes a mostrar en vez
    del genérico "código de salida N" cuando ESE paso falla con un código
    puntual conocido (ej. SAP GUI 7.8, códigos 144/145 -- ver
    `InstallWorker.run`). `continue_on_error` (ver `AppItem`, solo
    disponible en pasos de `extra_steps` -- el paso principal siempre lo
    trae en `False`) le dice a `InstallWorker.run` que NO detenga la
    secuencia si ESE paso termina con código de salida distinto de éxito.
    `success_codes` (ver `AppItem`) es una lista de códigos ADICIONALES que
    ESE paso puntual debe tratar como éxito (ej. DELL Command Update,
    código 2 -- ver `InstallWorker.run`). `timeout_seconds` (ver `AppItem`)
    es el límite de este paso puntual antes de darlo por colgado --
    `DEFAULT_STEP_TIMEOUT_SECONDS` si no se especifica, tanto para el paso
    principal como para cada paso de `extra_steps` (ej.
    "Windows-Updates-w11", que necesita más que el límite general -- ver
    `AppItem.timeout_seconds`)."""
    yield (
        item.installer,
        item.silent_args,
        item.installer_type,
        item.exit_code_messages,
        False,
        item.success_codes,
        item.timeout_seconds,
    )
    for step in item.extra_steps:
        yield (
            step.get("installer", ""),
            step.get("silent_args", ""),
            step.get("installer_type", "exe"),
            step.get("exit_code_messages", {}),
            step.get("continue_on_error", False),
            step.get("success_codes", []),
            step.get("timeout_seconds", DEFAULT_STEP_TIMEOUT_SECONDS),
        )


class InstallLogger:
    def __init__(self, logs_dir: Path = LOGS_DIR):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()
        self.log_path = self.logs_dir / f"install_{today}.log"

    def write(self, message: str) -> None:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")


class InstallWorker(QThread):
    """Ejecuta los pasos de un ítem (el principal + `item.extra_steps`, si
    los tiene) en segundo plano, en orden, uno detrás del otro -- por
    defecto se detiene en el primer paso que falle (no reintenta ni sigue
    con los siguientes). La mayoría de los ítems tienen un solo paso, así
    que para esos el comportamiento y los mensajes son exactamente los
    mismos que antes.

    Excepción: un paso de `extra_steps` con `"continue_on_error": true` (ver
    `AppItem` en app/config.py) -- si ESE paso termina con un código de
    salida que no es de éxito, la secuencia SIGUE con el próximo paso en
    vez de cortarse ahí (el fallo igual queda registrado en el log). Si al
    terminar toda la secuencia hubo uno o más pasos así, el ítem de todos
    modos se reporta como error (con el detalle de cuáles), simplemente ya
    se alcanzó a correr todo lo que seguía. Caso real que motivó esto: "SAP
    GUI 7.8" -- ver el comentario de `continue_on_error` en `AppItem`."""

    finished_item = Signal(str, bool, str)  # item_id, success, message

    def __init__(self, item: AppItem, installers_base_path: str, logger: InstallLogger, parent: QObject | None = None):
        super().__init__(parent)
        self.item = item
        self.installers_base_path = installers_base_path
        self.logger = logger

    def run(self) -> None:
        item = self.item
        base = Path(self.installers_base_path)
        steps = list(_iter_steps(item))
        total_steps = len(steps)
        last_detail = ""
        # Mensajes de los pasos que fallaron pero, por tener
        # `continue_on_error`, no cortaron la secuencia -- si queda alguno
        # acá al terminar todos los pasos, el ítem se reporta como error de
        # todos modos (ver docstring de la clase).
        continued_failures: list[str] = []

        for index, (
            installer_rel,
            silent_args,
            installer_type,
            exit_code_messages,
            continue_on_error,
            success_codes,
            timeout_seconds,
        ) in enumerate(steps, start=1):
            step_tag = f" (paso {index}/{total_steps})" if total_steps > 1 else ""

            if installer_type == "python":
                # Tipo "python": el paso no apunta a un archivo -- "installer"
                # es la clave de una función registrada en
                # _python_step_handlers() (ver app/shares_setup.py y
                # app/appshell_post_install.py). No hay ruta que resolver ni
                # verificar que exista; el éxito/fracaso lo decide la función
                # en sí (puede lanzar cualquier excepción, no solo un código
                # de salida de proceso). Se le pasa siempre
                # `installers_base_path`, lo use o no.
                handler = _python_step_handlers().get(installer_rel)
                if handler is None:
                    msg = f"Paso de Python desconocido: '{installer_rel}'{step_tag}"
                    self.logger.write(f"{item.label}: ERROR - {msg}")
                    self.finished_item.emit(item.id, False, msg)
                    return
                self.logger.write(f"{item.label}{step_tag}: ejecutando paso Python -> {installer_rel}")
                try:
                    last_detail = handler(self.installers_base_path)
                except Exception as exc:  # una función de paso puede lanzar cualquier tipo de error
                    msg = f"{exc}{step_tag}"
                    self.logger.write(f"{item.label}: ERROR - {msg}")
                    self.finished_item.emit(item.id, False, msg)
                    return
                self.logger.write(f"{item.label}{step_tag}: OK ({last_detail})")
                continue

            installer_path = _resolve_installer_path(base, installer_rel)

            if not installer_path.exists():
                msg = f"No se encontró el instalador en: {installer_path}{step_tag}"
                self.logger.write(f"{item.label}: ERROR - {msg}")
                self.finished_item.emit(item.id, False, msg)
                return

            if installer_type == "open":
                # Tipo "open": abrir un archivo (PDF, o un .exe ya instalado
                # para que el técnico lo use) y seguir de inmediato -- no es
                # un proceso que se "instale" con código de salida, así que
                # no se espera (no bloquea la cola) ni se interpreta éxito
                # más allá de que la llamada no haya lanzado una excepción.
                self.logger.write(f"{item.label}{step_tag}: abriendo -> {installer_path}")
                try:
                    _open_file(installer_path)
                except OSError as exc:
                    msg = f"No se pudo abrir{step_tag}: {exc}"
                    self.logger.write(f"{item.label}: ERROR - {msg}")
                    self.finished_item.emit(item.id, False, msg)
                    return
                last_detail = f"abierto: {installer_path}"
                continue

            cmd = _resolve_step_command(installer_type, silent_args, installer_path)
            self.logger.write(f"{item.label}{step_tag}: iniciando -> {' '.join(cmd)}")
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(installer_path.parent),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,  # ver `AppItem.timeout_seconds` -- 30 min por defecto, configurable por paso
                    creationflags=NO_CONSOLE_WINDOW,
                )
            except subprocess.TimeoutExpired:
                timeout_minutes = timeout_seconds / 60
                # Sin decimales cuando cae justo en un número entero de
                # minutos (el caso normal: 30, 60, ...) -- con decimales
                # solo si alguien configuró algo raro como 90 segundos.
                timeout_label = (
                    f"{timeout_minutes:g} min" if timeout_minutes == int(timeout_minutes) else f"{timeout_minutes:.1f} min"
                )
                msg = f"Tiempo de espera agotado ({timeout_label}){step_tag}."
                self.logger.write(f"{item.label}: ERROR - {msg}")
                self.finished_item.emit(item.id, False, msg)
                return
            except OSError as exc:
                msg = f"No se pudo ejecutar{step_tag}: {exc}"
                self.logger.write(f"{item.label}: ERROR - {msg}")
                self.finished_item.emit(item.id, False, msg)
                return

            success = result.returncode in SUCCESS_CODES or result.returncode in success_codes
            detail = f"código de salida {result.returncode}"
            if result.returncode == 3010:
                detail += " (requiere reinicio)"
            elif result.returncode == 1638:
                detail += " (ya estaba instalado)"
            elif success and result.returncode in success_codes:
                # Éxito gracias a `success_codes` de ESTE paso puntual (no
                # es uno de los códigos globales de siempre) -- si hay un
                # texto configurado para este código en
                # `exit_code_messages`, se agrega como nota aclaratoria
                # (caso real: DELL Command Update, código 2 -- ver
                # `success_codes` en app/config.py).
                custom_note = exit_code_messages.get(str(result.returncode))
                if custom_note:
                    detail += f" ({custom_note})"
            self.logger.write(f"{item.label}{step_tag}: {'OK' if success else 'FALLÓ'} ({detail})")
            # Se captura stdout/stderr siempre (no solo cuando falla) --
            # caso real de campo: "Manage Engine" (script de PowerShell)
            # terminaba con código 0 ("OK") sin instalar nada, y el log no
            # tenía ninguna pista de qué había pasado adentro del script
            # porque antes esto solo se registraba en la rama de fallo. Se
            # trunca a 500 caracteres igual que en la rama de fallo, para
            # no inflar el log con salidas verborrágicas (ej. logs de MSI).
            if success:
                # `isinstance` a propósito (no solo `result.stdout or ""`):
                # varias pruebas existentes mockean `subprocess.run` con un
                # `Mock(returncode=0)` sin especificar `stdout`/`stderr` --
                # en ese caso el atributo es otro `Mock` (no `None` ni
                # string), que nunca se había tocado en la rama de éxito
                # antes de este cambio. Sin este chequeo, `[:500]` más
                # abajo rompería con `TypeError: 'Mock' object is not
                # subscriptable`.
                stdout_ok = result.stdout.strip() if isinstance(result.stdout, str) else ""
                stderr_ok = result.stderr.strip() if isinstance(result.stderr, str) else ""
                if stdout_ok:
                    self.logger.write(f"{item.label}: stdout -> {stdout_ok[:500]}")
                if stderr_ok:
                    self.logger.write(f"{item.label}: stderr -> {stderr_ok[:500]}")
            if not success:
                # Se registra tanto stderr como stdout (muchos instaladores
                # de Windows -- sobre todo los que solo muestran una
                # interfaz gráfica -- no escriben nada en stderr y el único
                # detalle real, si lo hay, queda en stdout). Si los dos
                # vienen vacíos, se deja explícito en el log que el
                # instalador no dio ningún detalle además del código de
                # salida -- así se sabe que no es que el log esté
                # incompleto, sino que el instalador en sí no reportó nada
                # más (en ese caso, para investigar qué significa ese
                # código en particular hay que correrlo a mano con el
                # switch de log propio del instalador, si tiene uno, o
                # revisar la documentación del fabricante).
                stderr_text = (result.stderr or "").strip()
                stdout_text = (result.stdout or "").strip()
                if stderr_text:
                    self.logger.write(f"{item.label}: stderr -> {stderr_text[:500]}")
                if stdout_text:
                    self.logger.write(f"{item.label}: stdout -> {stdout_text[:500]}")
                if not stderr_text and not stdout_text:
                    self.logger.write(
                        f"{item.label}: el instalador no escribió nada en stdout/stderr -- "
                        f"el único detalle disponible es el código de salida {result.returncode}."
                    )
                # Si ESTE paso tiene un mensaje configurado para ESTE código
                # de salida puntual (ver `exit_code_messages` en `AppItem`,
                # app/config.py), se usa ese en vez del genérico "código de
                # salida N" -- pensado para códigos "conocidos" que no son
                # un error real sino algo que el técnico puede resolver él
                # mismo (ej. SAP GUI 7.8, 144/145: pendiente reinicio). La
                # casilla igual queda en rojo/sin marcar como cualquier
                # fallo -- el código real de todos modos ya quedó en el log
                # de arriba, esto solo cambia lo que ve el técnico en el
                # tooltip.
                custom_message = exit_code_messages.get(str(result.returncode))
                message = custom_message if custom_message else f"{detail}{step_tag}"
                if continue_on_error:
                    # No se corta la secuencia -- ver `continue_on_error` en
                    # `AppItem` (app/config.py) y el docstring de esta clase
                    # (caso real: "SAP GUI 7.8"). Se guarda el mensaje para
                    # reportar el ítem como error al final de todos modos, y
                    # se sigue con el próximo paso sin tocar `last_detail`
                    # (que solo se actualiza con pasos exitosos).
                    continued_failures.append(f"{message}{step_tag}" if step_tag not in message else message)
                    continue
                self.finished_item.emit(item.id, False, message)
                return
            last_detail = detail

        if continued_failures:
            # Uno o más pasos con `continue_on_error` fallaron en el camino
            # -- la secuencia se completó igual, pero el ítem se reporta
            # como error de todos modos (no se oculta solo porque se haya
            # podido seguir con el resto).
            self.finished_item.emit(item.id, False, "; ".join(continued_failures))
            return

        final_detail = f"{total_steps} pasos completados ({last_detail})" if total_steps > 1 else last_detail
        self.finished_item.emit(item.id, True, final_detail)


class InstallManager(QObject):
    """Coordina la cola de instalación (secuencial) y expone señales para la UI."""

    item_started = Signal(str)               # item_id
    item_finished = Signal(str, bool, str)   # item_id, success, message
    queue_finished = Signal()

    def __init__(self, installers_base_path: str, parent: QObject | None = None):
        super().__init__(parent)
        self.installers_base_path = installers_base_path
        self.logger = InstallLogger()
        self._queue: list[AppItem] = []
        self._current_worker: InstallWorker | None = None

    def start(self, items: list[AppItem]) -> None:
        self._queue = list(items)
        self._run_next()

    def _run_next(self) -> None:
        if not self._queue:
            self.queue_finished.emit()
            return
        item = self._queue.pop(0)
        self.item_started.emit(item.id)
        # `InstallWorker` resuelve la ruta de cada paso por su cuenta (un
        # ítem puede tener más de un paso -- ver `item.extra_steps`), así
        # que acá solo se le pasa la carpeta base, no una ruta ya resuelta.
        worker = InstallWorker(item, self.installers_base_path, self.logger, self)
        worker.finished_item.connect(self._on_item_finished)
        self._current_worker = worker
        worker.start()

    def _on_item_finished(self, item_id: str, success: bool, message: str) -> None:
        self.item_finished.emit(item_id, success, message)
        self._run_next()
