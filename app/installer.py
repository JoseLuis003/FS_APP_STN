"""Motor de instalación desatendida.

Ejecuta cada instalador seleccionado en un hilo de trabajo (QThread) para no
congelar la interfaz, y reporta progreso/resultado mediante señales Qt.
"""
from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from app.config import AppItem, LOGS_DIR

# Códigos de salida que se consideran éxito además de 0.
# 3010 = éxito, requiere reinicio (común en instaladores MSI / Windows Update).
SUCCESS_CODES = {0, 3010}


def build_command(item: AppItem, installer_path: Path) -> list[str]:
    """Arma la línea de comandos según el tipo de instalador."""
    if item.installer_type == "msi":
        cmd = ["msiexec", "/i", str(installer_path)]
        if item.silent_args:
            cmd += item.silent_args.split()
        return cmd
    if item.installer_type == "script":
        # Scripts .ps1/.bat
        if installer_path.suffix.lower() == ".ps1":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer_path)]
        else:
            cmd = [str(installer_path)]
        if item.silent_args:
            cmd += item.silent_args.split()
        return cmd
    # exe genérico
    cmd = [str(installer_path)]
    if item.silent_args:
        cmd += item.silent_args.split()
    return cmd


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
    """Ejecuta un único instalador en segundo plano."""

    finished_item = Signal(str, bool, str)  # item_id, success, message

    def __init__(self, item: AppItem, installer_path: Path, logger: InstallLogger, parent: QObject | None = None):
        super().__init__(parent)
        self.item = item
        self.installer_path = installer_path
        self.logger = logger

    def run(self) -> None:
        item = self.item
        if not self.installer_path.exists():
            msg = f"No se encontró el instalador en: {self.installer_path}"
            self.logger.write(f"{item.label}: ERROR - {msg}")
            self.finished_item.emit(item.id, False, msg)
            return

        cmd = build_command(item, self.installer_path)
        self.logger.write(f"{item.label}: iniciando -> {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.installer_path.parent),
                capture_output=True,
                text=True,
                timeout=30 * 60,  # 30 minutos por instalador
            )
        except subprocess.TimeoutExpired:
            msg = "Tiempo de espera agotado (30 min)."
            self.logger.write(f"{item.label}: ERROR - {msg}")
            self.finished_item.emit(item.id, False, msg)
            return
        except OSError as exc:
            msg = f"No se pudo ejecutar: {exc}"
            self.logger.write(f"{item.label}: ERROR - {msg}")
            self.finished_item.emit(item.id, False, msg)
            return

        success = result.returncode in SUCCESS_CODES
        detail = f"código de salida {result.returncode}"
        if result.returncode == 3010:
            detail += " (requiere reinicio)"
        self.logger.write(f"{item.label}: {'OK' if success else 'FALLÓ'} ({detail})")
        if not success and result.stderr:
            self.logger.write(f"{item.label}: stderr -> {result.stderr.strip()[:500]}")
        self.finished_item.emit(item.id, success, detail)


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
        installer_path = item.resolved_installer_path(self.installers_base_path)
        self.item_started.emit(item.id)
        worker = InstallWorker(item, installer_path, self.logger, self)
        worker.finished_item.connect(self._on_item_finished)
        self._current_worker = worker
        worker.start()

    def _on_item_finished(self, item_id: str, success: bool, message: str) -> None:
        self.item_finished.emit(item_id, success, message)
        self._run_next()
