"""Pantalla LTP / CSS: segundo catálogo de instalación, separado del de
APPS (ver `app/ui/main_window.py`), con su propio archivo de catálogo
(`config/ltp_css_apps.json`). Reutiliza el mismo motor de instalación
(`InstallManager`) y el mismo generador de reporte que APPS, pero con una
lista de aplicaciones distinta y sin los botones NUEVO/UNSELECT/MTO/AJUSTES
(por ahora esta pantalla solo necesita ATRAS e INSTALAR).

GEMALTO / 3M / DESKO son mutuamente excluyentes (solo uno se puede marcar a
la vez) mediante el mecanismo de "grupo exclusivo" de
`app/ui/catalog_widgets.py` — ver el campo `exclusive_group` en
`config/ltp_css_apps.json`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import ASSETS_DIR, AppItem, LTP_CSS_APPS_FILE, load_app_columns, load_settings
from app.installer import InstallManager
from app.report import generate_report
from app.ui.catalog_widgets import build_checkbox_column, reapply_exclusive_constraints
from app.ui.shares_config_panel import SharesConfigPanel
from app.ui.styles import build_stylesheet


class LtpCssWindow(QMainWindow):
    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.setWindowTitle("FS APP PORTABLE - LTP / CSS")
        self.setStyleSheet(build_stylesheet(ASSETS_DIR))
        # Un poco más alta que la de APPS: cuando se marca "Shares
        # Configuracion" aparece el panel SETTING's / DEVICES / CRT's debajo
        # del catálogo, y así entra completo sin tener que redimensionar.
        self.resize(950, 780)

        # Si se abrió desde la portada, este callback regresa a esa
        # pantalla; si no se indica, ATRAS simplemente cierra esta ventana.
        self._on_back = on_back

        self.settings = load_settings()
        self.columns = load_app_columns(LTP_CSS_APPS_FILE)

        # item_id -> (AppItem, QCheckBox)
        self.checkboxes: dict[str, tuple[AppItem, QCheckBox]] = {}
        self.install_manager: InstallManager | None = None

        self._build_ui()

        # Igual que en APPS: revisa cada pocos segundos si la carpeta de
        # instaladores sigue existiendo, para que el indicador arriba de
        # INSTALAR siempre esté al día.
        self._path_check_timer = QTimer(self)
        self._path_check_timer.timeout.connect(self._update_active_path_label)
        self._path_check_timer.start(3000)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(30)
        for column in self.columns:
            columns_row.addLayout(build_checkbox_column(column, self.checkboxes))
        columns_row.addStretch(1)
        root.addLayout(columns_row)

        # Panel de "Shares Configuracion": oculto por defecto, aparece
        # cuando se marca esa casilla en el catálogo de arriba.
        self.shares_config_panel = SharesConfigPanel()
        self.shares_config_panel.setVisible(False)
        root.addWidget(self.shares_config_panel)
        if "shares_configuracion" in self.checkboxes:
            _item, shares_checkbox = self.checkboxes["shares_configuracion"]
            shares_checkbox.toggled.connect(self.shares_config_panel.setVisible)
            self.shares_config_panel.setVisible(shares_checkbox.isChecked())

        root.addStretch(1)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Listo.")
        self.status_label.setObjectName("statusBar")
        status_row.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("installProgressBar")
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        status_row.addWidget(self.progress_bar)
        status_row.addStretch(1)

        root.addLayout(status_row)

        root.addLayout(self._build_controls())

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()

        atras_btn = QPushButton("ATRAS")
        atras_btn.clicked.connect(self._on_atras)
        row.addWidget(atras_btn)
        row.addStretch(1)

        installar_col = QVBoxLayout()
        installar_col.setSpacing(4)

        self.active_path_label = QLabel()
        self.active_path_label.setObjectName("activePathLabel")
        self.active_path_label.setAlignment(Qt.AlignRight)
        self.active_path_label.setWordWrap(True)
        self.active_path_label.setMaximumWidth(260)
        installar_col.addWidget(self.active_path_label)

        self.installar_btn = QPushButton("INSTALAR")
        self.installar_btn.setObjectName("installarButton")
        self.installar_btn.setMinimumSize(160, 70)
        self.installar_btn.clicked.connect(self._on_installar)
        installar_col.addWidget(self.installar_btn)

        row.addLayout(installar_col)
        self._update_active_path_label()

        return row

    def _update_active_path_label(self) -> None:
        if not hasattr(self, "active_path_label"):
            return
        path = self.settings.installers_base_path
        if path and Path(path).exists():
            self.active_path_label.setText(f"Instalando desde:\n{path}\n✓ Carpeta encontrada")
            self.active_path_label.setStyleSheet("color: #1a7a1a;")
        else:
            self.active_path_label.setText(f"Instalando desde:\n{path}\n⚠ Carpeta NO encontrada")
            self.active_path_label.setStyleSheet("color: #b03a2e; font-weight: 600;")

    # ------------------------------------------------------------- acciones
    def _on_atras(self) -> None:
        """Regresa a la portada (FS APP PORTABLE) si esta ventana se abrió
        desde ahí; si no, simplemente cierra esta ventana."""
        if self._on_back is not None:
            self._on_back()
        else:
            self.close()

    def _on_installar(self) -> None:
        selected: list[AppItem] = [
            item for item, checkbox in self.checkboxes.values() if checkbox.isEnabled() and checkbox.isChecked()
        ]
        if not selected:
            QMessageBox.warning(self, "Instalar", "No hay ninguna aplicación seleccionada.")
            return

        if not Path(self.settings.installers_base_path).exists():
            QMessageBox.critical(
                self,
                "Carpeta de instaladores no encontrada",
                "No se encuentra la carpeta configurada:\n\n"
                f"{self.settings.installers_base_path}\n\n"
                "Si los instaladores están en un USB, conéctalo y verifica la ruta en AJUSTES "
                "(la letra de unidad puede cambiar cada vez que lo conectas).",
            )
            return

        self._set_controls_enabled(False)
        self._results = {"ok": 0, "error": 0}
        self._install_records: list[tuple[str, str, datetime]] = []

        self.install_manager = InstallManager(self.settings.installers_base_path, self)
        self.install_manager.item_started.connect(self._on_item_started)
        self.install_manager.item_finished.connect(self._on_item_finished)
        self.install_manager.queue_finished.connect(self._on_queue_finished)
        self.install_manager.start(selected)

    # --------------------------------------------------------- señales cola
    def _on_item_started(self, item_id: str) -> None:
        _item, checkbox = self.checkboxes[item_id]
        checkbox.setProperty("installing", "true")
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        self.status_label.setText(f"Instalando: {_item.label}...")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

    def _on_item_finished(self, item_id: str, success: bool, message: str) -> None:
        item, checkbox = self.checkboxes[item_id]
        checkbox.setProperty("installing", "false")
        if success:
            self._results["ok"] += 1
            self._install_records.append((item.label, item.version, datetime.now()))
            checkbox.setVisible(False)
        else:
            self._results["error"] += 1
            checkbox.setProperty("failed", "true")
            checkbox.setChecked(False)
            checkbox.setToolTip(f"Error: {message}")
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)

    def _on_queue_finished(self) -> None:
        self._set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 1)
        ok = self._results["ok"]
        error = self._results["error"]
        self.status_label.setText(f"Instalación finalizada: {ok} correctas, {error} con error.")

        try:
            report_html, _report_csv = generate_report(self._install_records, section_label="LTP_CSS")
            report_msg = f"\n\nReporte generado en:\n{report_html}"
        except Exception as exc:
            report_html = None
            report_msg = f"\n\nNo se pudo generar el reporte: {exc}"

        QMessageBox.information(
            self,
            "Instalación finalizada",
            f"Completadas: {ok}\nCon error: {error}\n\nRevisa la carpeta 'logs' para el detalle.{report_msg}",
        )

        if report_html and sys.platform == "win32":
            try:
                os.startfile(report_html)
            except OSError:
                pass

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.installar_btn.setEnabled(enabled)
        for _item, checkbox in self.checkboxes.values():
            checkbox.setEnabled(enabled and _item.enabled)
        if enabled:
            reapply_exclusive_constraints(self.checkboxes)
