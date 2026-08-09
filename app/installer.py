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

from app.config import AppItem, LOGS_DIR
from app.shares_setup import run_ltp_shares_post_install

# Códigos de salida que se consideran éxito además de 0.
# 3010 = éxito, requiere reinicio (común en instaladores MSI / Windows Update).
SUCCESS_CODES = {0, 3010}

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
# Python correr (ver `app/shares_setup.py`). Se usa para lógica que ya no
# tiene sentido mantener como un .bat/.ps1 suelto en la carpeta de
# instaladores, sino que se porta directo a código Python empaquetado
# dentro de la app (con su propio manejo de errores por paso, en vez de
# depender de un solo código de salida de todo un script).
#
# Armado adentro de una función (en vez de un dict a nivel de módulo) a
# propósito: así, cada llamada resuelve `run_ltp_shares_post_install` como
# variable global de este módulo EN ESE MOMENTO -- si algo la reemplaza
# (p. ej. `mock.patch("app.installer.run_ltp_shares_post_install", ...)`
# en una prueba), la próxima llamada ya ve el reemplazo. Con un dict
# armado una sola vez al importar el módulo, quedaría "congelada" la
# referencia original de forma permanente, inmune a cualquier patch
# posterior.
def _python_step_handlers() -> dict:
    return {
        "ltp_shares_post_install": run_ltp_shares_post_install,
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
    """Genera (installer_relativo, silent_args, installer_type) para el
    paso principal de `item` y luego cada uno de `item.extra_steps`, en el
    mismo orden en que deben ejecutarse."""
    yield item.installer, item.silent_args, item.installer_type
    for step in item.extra_steps:
        yield step.get("installer", ""), step.get("silent_args", ""), step.get("installer_type", "exe")


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
    los tiene) en segundo plano, en orden, uno detrás del otro -- se detiene
    en el primer paso que falle (no reintenta ni sigue con los siguientes).
    La mayoría de los ítems tienen un solo paso, así que para esos el
    comportamiento y los mensajes son exactamente los mismos que antes."""

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

        for index, (installer_rel, silent_args, installer_type) in enumerate(steps, start=1):
            step_tag = f" (paso {index}/{total_steps})" if total_steps > 1 else ""

            if installer_type == "python":
                # Tipo "python": el paso no apunta a un archivo -- "installer"
                # es la clave de una función registrada en
                # _PYTHON_STEP_HANDLERS (ver app/shares_setup.py). No hay
                # ruta que resolver ni verificar que exista; el éxito/fracaso
                # lo decide la función en sí (puede lanzar cualquier
                # excepción, no solo un código de salida de proceso).
                handler = _python_step_handlers().get(installer_rel)
                if handler is None:
                    msg = f"Paso de Python desconocido: '{installer_rel}'{step_tag}"
                    self.logger.write(f"{item.label}: ERROR - {msg}")
                    self.finished_item.emit(item.id, False, msg)
                    return
                self.logger.write(f"{item.label}{step_tag}: ejecutando paso Python -> {installer_rel}")
                try:
                    last_detail = handler()
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
                    timeout=30 * 60,  # 30 minutos por paso
                )
            except subprocess.TimeoutExpired:
                msg = f"Tiempo de espera agotado (30 min){step_tag}."
                self.logger.write(f"{item.label}: ERROR - {msg}")
                self.finished_item.emit(item.id, False, msg)
                return
            except OSError as exc:
                msg = f"No se pudo ejecutar{step_tag}: {exc}"
                self.logger.write(f"{item.label}: ERROR - {msg}")
                self.finished_item.emit(item.id, False, msg)
                return

            success = result.returncode in SUCCESS_CODES
            detail = f"código de salida {result.returncode}"
            if result.returncode == 3010:
                detail += " (requiere reinicio)"
            self.logger.write(f"{item.label}{step_tag}: {'OK' if success else 'FALLÓ'} ({detail})")
            if not success:
                if result.stderr:
                    self.logger.write(f"{item.label}: stderr -> {result.stderr.strip()[:500]}")
                self.finished_item.emit(item.id, False, f"{detail}{step_tag}")
                return
            last_detail = detail

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
