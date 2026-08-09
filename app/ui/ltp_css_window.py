"""Pantalla LTP / CSS: segundo catálogo de instalación, separado del de
APPS (ver `app/ui/main_window.py`), con su propio archivo de catálogo
(`config/ltp_css_apps.json`). Reutiliza el mismo motor de instalación
(`InstallManager`) que APPS, pero con una lista de aplicaciones distinta,
sin los botones NUEVO/UNSELECT/MTO/AJUSTES (por ahora esta pantalla solo
necesita ATRAS e INSTALAR) y sin generar el reporte HTML/CSV al terminar
(no hace falta en esta pantalla).

GEMALTO / 3M / DESKO son mutuamente excluyentes (solo uno se puede marcar a
la vez) mediante el mecanismo de "grupo exclusivo" de
`app/ui/catalog_widgets.py` — ver el campo `exclusive_group` en
`config/ltp_css_apps.json`.

"Shares Configuracion" tampoco se instala como los demás ítems: al marcar
su casilla aparece el panel `SharesConfigPanel` (CIUDAD, HOSTNAME, LNIATA,
etc.) y, al presionar INSTALAR, se aplica por separado con
`app/shares_config_apply.py` en vez de mandarse al motor de instalación
genérico.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# Tamaño de ventana "ideal" (suficiente para ver el catálogo completo sin
# scroll en un monitor normal). Si la pantalla del técnico es más chica —
# por ejemplo un laptop con poca resolución o con la barra de tareas
# ocupando espacio — se recorta para que la ventana siempre entre
# completa; el contenido que no quepa se ve haciendo scroll (ver
# QScrollArea en `_build_ui`), en vez de que la ventana se abra más alta
# que la pantalla y ATRAS/INSTALAR queden inalcanzables detrás de la barra
# de tareas.
_DEFAULT_WIDTH = 950
_DEFAULT_HEIGHT = 780
_SCREEN_MARGIN = 40


def _initial_window_size() -> tuple[int, int]:
    width, height = _DEFAULT_WIDTH, _DEFAULT_HEIGHT
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        width = min(width, max(available.width() - _SCREEN_MARGIN, 300))
        height = min(height, max(available.height() - _SCREEN_MARGIN, 300))
    return width, height

from app.config import AppItem, LTP_CSS_APPS_FILE, load_app_columns, load_settings
from app.installer import InstallManager
from app.shares_config_apply import SharesConfigError, apply_shares_configuration, apply_udf_configuration
from app.ui.catalog_widgets import build_checkbox_column, reapply_exclusive_constraints
from app.ui.shares_config_panel import SharesConfigPanel


class LtpCssWindow(QMainWindow):
    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.setWindowTitle("FS APP PORTABLE - LTP / CSS")
        # La hoja de estilos se aplica a nivel de QApplication en
        # `main.py` -- así también la heredan los QMessageBox de esta
        # ventana (diálogos de nivel superior aparte, que no heredan un
        # `.setStyleSheet()` puesto solo sobre esta ventana).
        # Se recorta al tamaño disponible de la pantalla si hace falta (ver
        # `_initial_window_size`) — el contenido que no quepa se ve
        # haciendo scroll, así que la ventana nunca se abre más alta que la
        # pantalla del técnico.
        self.resize(*_initial_window_size())

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

        # El catálogo y el panel de "Shares Configuracion" van dentro de un
        # QScrollArea: así, sin importar cuánto contenido haya (el panel
        # agrega bastante alto) ni qué tan chica sea la pantalla del
        # técnico, ATRAS e INSTALAR quedan siempre fijos y completos abajo
        # en vez de empujarse fuera de la vista.
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(30)
        for column in self.columns:
            columns_row.addLayout(build_checkbox_column(column, self.checkboxes))
        columns_row.addStretch(1)
        scroll_layout.addLayout(columns_row)

        # Panel de "Shares Configuracion": oculto por defecto, aparece
        # cuando se marca esa casilla en el catálogo de arriba.
        self.shares_config_panel = SharesConfigPanel()
        self.shares_config_panel.setVisible(False)
        scroll_layout.addWidget(self.shares_config_panel)
        if "shares_configuracion" in self.checkboxes:
            _item, shares_checkbox = self.checkboxes["shares_configuracion"]
            shares_checkbox.toggled.connect(self.shares_config_panel.setVisible)
            self.shares_config_panel.setVisible(shares_checkbox.isChecked())

        scroll_layout.addStretch(1)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(scroll_content)
        # El fondo del QScrollArea (y de su viewport) se define en la hoja
        # de estilos global (`app/ui/styles.py`) y no acá con un
        # stylesheet local — ponerlo acá rompía el resaltado azul de los
        # checkboxes marcados que viven adentro (ver comentario en
        # styles.py para el detalle del bug).
        root.addWidget(scroll_area, 1)

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

        # "Shares Configuracion" no es un instalador tradicional: se
        # separa de la cola normal y se aplica aparte con los valores del
        # panel (ver `_run_shares_configuration`).
        shares_entry = self.checkboxes.get("shares_configuracion")
        apply_shares = shares_entry is not None and shares_entry[0] in selected
        if apply_shares:
            selected = [it for it in selected if it is not shares_entry[0]]

        if selected and not Path(self.settings.installers_base_path).exists():
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

        if apply_shares:
            self._run_shares_configuration(shares_entry)

        if selected:
            self.install_manager = InstallManager(self.settings.installers_base_path, self)
            self.install_manager.item_started.connect(self._on_item_started)
            self.install_manager.item_finished.connect(self._on_item_finished)
            self.install_manager.queue_finished.connect(self._on_queue_finished)
            self.install_manager.start(selected)
        else:
            # Solo se había marcado Shares Configuracion: no queda nada
            # más que mandar al motor de instalación normal.
            self._on_queue_finished()

    def _run_shares_configuration(self, shares_entry: tuple[AppItem, QCheckBox]) -> None:
        """Aplica la configuración de Shares (ver `app/shares_config_apply.py`):
        primero el .XRF (`apply_shares_configuration`, con CIUDAD y HOSTNAME)
        y después el .INF de la carpeta UDF (`apply_udf_configuration`, con
        CIUDAD y — para cada LNIATA marcado (CRT/ATB/BTP/DCP) — su valor).
        Refleja el resultado en la casilla igual que un ítem normal de la
        cola."""
        item, checkbox = shares_entry
        checkbox.setProperty("installing", "true")
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        self.status_label.setText("Aplicando configuración de Shares...")

        hostname = self.shares_config_panel.hostname_edit.text()
        ciudad = self.shares_config_panel.ciudad_edit.text()
        lniata_crt = self.shares_config_panel.lniata_edits["CRT"].text()
        crt_enabled = self.shares_config_panel.lniata_checks["CRT"].isChecked()
        lniata_atb = self.shares_config_panel.lniata_edits["ATB"].text()
        atb_enabled = self.shares_config_panel.lniata_checks["ATB"].isChecked()
        lniata_btp = self.shares_config_panel.lniata_edits["BTP"].text()
        btp_enabled = self.shares_config_panel.lniata_checks["BTP"].isChecked()
        lniata_dcp = self.shares_config_panel.lniata_edits["DCP"].text()
        dcp_enabled = self.shares_config_panel.lniata_checks["DCP"].isChecked()

        try:
            detail_xrf = apply_shares_configuration(hostname, ciudad)
            detail_udf = apply_udf_configuration(
                ciudad,
                lniata_crt=lniata_crt,
                crt_enabled=crt_enabled,
                lniata_atb=lniata_atb,
                atb_enabled=atb_enabled,
                lniata_btp=lniata_btp,
                btp_enabled=btp_enabled,
                lniata_dcp=lniata_dcp,
                dcp_enabled=dcp_enabled,
            )
            detail = f"{detail_xrf} | {detail_udf}"
        except SharesConfigError as exc:
            self._results["error"] += 1
            checkbox.setProperty("installing", "false")
            checkbox.setProperty("failed", "true")
            checkbox.setChecked(False)
            checkbox.setToolTip(f"Error: {exc}")
            checkbox.style().unpolish(checkbox)
            checkbox.style().polish(checkbox)
            self.status_label.setText(f"Shares Configuracion: error - {exc}")
            return

        self._results["ok"] += 1
        self._install_records.append((item.label, item.version, datetime.now()))
        checkbox.setProperty("installing", "false")
        checkbox.setVisible(False)
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        self.status_label.setText(f"Shares Configuracion aplicada ({detail}).")

        # Con la casilla ya oculta (igual que cualquier ítem completado), el
        # panel tampoco debe seguir viéndose. Los campos LNIATA son de un
        # solo uso: se limpian para la próxima vez. HOSTNAME y CIUDAD SÍ
        # deben quedar (identifican al equipo, no cambian entre corridas).
        self.shares_config_panel.setVisible(False)
        self.shares_config_panel.reset_lniata_fields()

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

        # A diferencia de APPS, esta pantalla no genera reporte HTML/CSV al
        # terminar — no hace falta aquí.
        QMessageBox.information(
            self,
            "Instalación finalizada",
            f"Completadas: {ok}\nCon error: {error}\n\nRevisa la carpeta 'logs' para el detalle.",
        )

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.installar_btn.setEnabled(enabled)
        for _item, checkbox in self.checkboxes.values():
            checkbox.setEnabled(enabled and _item.enabled)
        if enabled:
            reapply_exclusive_constraints(self.checkboxes)
