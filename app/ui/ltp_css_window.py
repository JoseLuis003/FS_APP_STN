"""Pantalla LTP / CSS: segundo catálogo de instalación, separado del de
APPS (ver `app/ui/main_window.py`), con su propio archivo de catálogo
(`config/ltp_css_apps.json`). Reutiliza el mismo motor de instalación
(`InstallManager`) que APPS, y también reutiliza los diálogos de AJUSTES
(agregar / editar versión o instalador / eliminar aplicaciones) de
`app/ui/main_window.py`, pasándoles `LTP_CSS_APPS_FILE` en vez de
`APPS_FILE` para que operen sobre el catálogo de esta pantalla. No tiene
los botones NUEVO/UNSELECT/MTO (por ahora esta pantalla solo necesita
ATRAS, AJUSTES e INSTALAR) y no genera el reporte HTML/CSV al terminar
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

"AppShell Configuracion" (columna de AppShell) funciona con el mismo
mecanismo de mostrar/ocultar un panel al marcar su casilla: al marcarla
aparece `AppShellConfigPanel`, con el submenú DEVICE's (ATB, BTP, DCP,
BGR, OCR). Igual que "Shares Configuracion", este ítem NO pasa por el
motor de instalación genérico: al presionar INSTALAR se separa de la cola
normal y se aplica aparte con `app/appshell_config_apply.py` (ver
`_run_appshell_configuration`). ATB, BTP y DCP marcados agregan su puerto
COM y su identificador al INI de configuración de AppShell
(`PrintAgent_COPA_PROD.ini`); BGR y OCR marcados crean o actualizan el
archivo `Mastcom.xml` con su sesión correspondiente (sin borrar ninguna
sesión ya configurada ahí). Las dos lógicas son independientes entre sí y
pueden aplicarse juntas en la misma corrida.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
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

# Título base de la ventana; se le agrega el tamaño actual (ancho x alto en
# píxeles) al final, visible en la barra de título del sistema operativo —
# así el técnico puede ver de un vistazo si la ventana se está abriendo más
# grande de lo esperado, sin tener que agregar un widget aparte (ver
# `_update_title_with_size` / `resizeEvent`).
_BASE_TITLE = "FS APP PORTABLE - LTP / CSS"

# Tamaño de ventana por defecto al abrir (confirmado a mano por el
# técnico arrastrando el borde hasta que se veía bien: 583 x 632). La
# ventana sigue siendo redimensionable con normalidad -- esto es solo el
# tamaño INICIAL, no un límite; ver `_initial_window_size`, que además lo
# recorta si la pantalla del técnico es más chica que eso (por ejemplo un
# laptop con poca resolución o con la barra de tareas ocupando espacio),
# para que la ventana siempre entre completa. El contenido que no quepa se
# ve haciendo scroll (ver QScrollArea en `_build_ui`).
_DEFAULT_WIDTH = 583
_DEFAULT_HEIGHT = 632
_SCREEN_MARGIN = 40


def _initial_window_size() -> tuple[int, int]:
    width, height = _DEFAULT_WIDTH, _DEFAULT_HEIGHT
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        width = min(width, max(available.width() - _SCREEN_MARGIN, 300))
        height = min(height, max(available.height() - _SCREEN_MARGIN, 300))
    return width, height

from app.appshell_config_apply import (
    AppShellConfigError,
    apply_appshell_device_config,
    apply_appshell_mastcom_config,
)
from app.config import AppItem, LTP_CSS_APPS_FILE, load_app_columns, load_settings, save_settings
from app.installer import InstallLogger, InstallManager
from app.shares_config_apply import (
    SharesConfigError,
    apply_shares_configuration,
    apply_udf_configuration,
    run_contingencia_script,
)
from app.shortcuts import ShortcutError, create_ltp_shares_shortcuts
from app.ui.appshell_config_panel import AppShellConfigPanel
from app.ui.catalog_widgets import build_checkbox_column, reapply_exclusive_constraints
from app.ui.main_window import SettingsDialog
from app.ui.shares_config_panel import SharesConfigPanel


class LtpCssWindow(QMainWindow):
    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        # La hoja de estilos se aplica a nivel de QApplication en
        # `main.py` -- así también la heredan los QMessageBox de esta
        # ventana (diálogos de nivel superior aparte, que no heredan un
        # `.setStyleSheet()` puesto solo sobre esta ventana).
        # Se recorta al tamaño disponible de la pantalla si hace falta (ver
        # `_initial_window_size`) — el contenido que no quepa se ve
        # haciendo scroll, así que la ventana nunca se abre más alta que la
        # pantalla del técnico.
        self.resize(*_initial_window_size())
        # El título (con el tamaño actual agregado) se fija después de
        # `resize()` para reflejar el tamaño ya recortado desde el arranque,
        # sin depender de que `resizeEvent` llegue a tiempo.
        self._update_title_with_size()

        # Si se abrió desde la portada, este callback regresa a esa
        # pantalla; si no se indica, ATRAS simplemente cierra esta ventana.
        self._on_back = on_back

        self.settings = load_settings()
        self.columns = load_app_columns(LTP_CSS_APPS_FILE)

        # item_id -> (AppItem, QCheckBox)
        self.checkboxes: dict[str, tuple[AppItem, QCheckBox]] = {}
        self.install_manager: InstallManager | None = None

        # "Shares Configuracion" y "AppShell Configuracion" no pasan por
        # `InstallManager`/`InstallWorker` (ver `_run_shares_configuration`
        # y `_run_appshell_configuration`), así que sin este logger propio
        # sus resultados solo quedaban en la casilla y en `status_label`
        # -- nunca en la carpeta `logs`, aunque el diálogo final siempre le
        # dice al técnico que la revise ahí. Con esto, sus mensajes quedan
        # en el mismo archivo `logs/install_<fecha>.log` que usa el resto
        # de la cola (cada `InstallManager` crea su propia instancia de
        # `InstallLogger`, pero todas escriben -- con `open(..., "a")` -- al
        # mismo archivo del día, así que no hay conflicto entre esta
        # instancia y la de `InstallManager`).
        self.logger = InstallLogger()

        self._build_ui()

        # Igual que en APPS: revisa cada pocos segundos si la carpeta de
        # instaladores sigue existiendo, para que el indicador arriba de
        # INSTALAR siempre esté al día.
        self._path_check_timer = QTimer(self)
        self._path_check_timer.timeout.connect(self._update_active_path_label)
        self._path_check_timer.start(3000)

    def _update_title_with_size(self) -> None:
        """Agrega el tamaño actual de la ventana (ancho x alto en píxeles)
        al final del título, visible en la barra de título del sistema.
        Se llama al abrir la ventana y en cada `resizeEvent`, así el
        técnico puede ver de un vistazo si la ventana se abrió (o quedó,
        tras arrastrar el borde) más grande de lo esperado para su
        pantalla."""
        self.setWindowTitle(f"{_BASE_TITLE}  —  {self.width()} x {self.height()} px")

    def resizeEvent(self, event) -> None:
        self._update_title_with_size()
        super().resizeEvent(event)

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

        # Panel de "AppShell Configuracion": a diferencia del de "Shares
        # Configuracion" (más abajo), este se arma ANTES de las columnas y
        # se le pasa a `build_checkbox_column` como `inline_widgets` --
        # así queda dibujado dentro de la columna de AppShell, justo debajo
        # de esa casilla, en vez de aparte, más abajo, fuera de las
        # columnas. Oculto por defecto; qué debe hacer cada opción del
        # submenú se programa más adelante.
        self.appshell_config_panel = AppShellConfigPanel()
        self.appshell_config_panel.setVisible(False)
        inline_widgets = {"appshell_configuracion": self.appshell_config_panel}

        columns_row = QHBoxLayout()
        columns_row.setSpacing(30)
        for column in self.columns:
            columns_row.addLayout(build_checkbox_column(column, self.checkboxes, inline_widgets))
        columns_row.addStretch(1)
        scroll_layout.addLayout(columns_row)

        if "appshell_configuracion" in self.checkboxes:
            _item, appshell_checkbox = self.checkboxes["appshell_configuracion"]
            appshell_checkbox.toggled.connect(self.appshell_config_panel.setVisible)
            self.appshell_config_panel.setVisible(appshell_checkbox.isChecked())

        # Panel de "Shares Configuracion": este sí queda aparte, debajo de
        # todas las columnas (tiene 3 secciones lado a lado -- SETTING's,
        # DEVICES, CRT's -- que necesitan más ancho del que tiene una sola
        # columna angosta). Oculto por defecto, aparece cuando se marca esa
        # casilla en el catálogo de arriba.
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

        ajustes_btn = QPushButton("AJUSTES")
        ajustes_btn.clicked.connect(self._on_ajustes)
        row.addWidget(ajustes_btn)

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

    def _on_ajustes(self) -> None:
        """Reutiliza el mismo diálogo AJUSTES de la pantalla APPS
        (`app/ui/main_window.SettingsDialog`), pasándole `LTP_CSS_APPS_FILE`
        para que "Editar versiones..." y "Agregar aplicación..." operen
        sobre `config/ltp_css_apps.json` en vez de `config/apps.json`. La
        carpeta base de instaladores es la misma para ambas pantallas."""
        items = [item for item, _checkbox in self.checkboxes.values()]
        dialog = SettingsDialog(self.settings, items, len(self.columns), apps_file=LTP_CSS_APPS_FILE, parent=self)
        accepted = dialog.exec() == QDialog.Accepted
        if accepted:
            self.settings = dialog.result_settings()
            save_settings(self.settings)
            self.status_label.setText("Ajustes guardados.")
        if dialog.catalog_changed:
            self._reload_catalog()
            if not accepted:
                self.status_label.setText("Catálogo actualizado.")
        self._update_active_path_label()

    def _reload_catalog(self) -> None:
        """Vuelve a leer `config/ltp_css_apps.json` y reconstruye la lista
        de checkboxes (usado después de agregar/editar/eliminar una
        aplicación desde AJUSTES), preservando la selección actual de los
        ítems que siguen existiendo. Igual que en APPS (ver
        `MainWindow._reload_catalog`)."""
        checked_ids = {
            item_id for item_id, (_item, checkbox) in self.checkboxes.items() if checkbox.isChecked()
        }
        self.checkboxes = {}
        self.columns = load_app_columns(LTP_CSS_APPS_FILE)
        self._build_ui()
        for item_id, (_item, checkbox) in self.checkboxes.items():
            if item_id in checked_ids:
                checkbox.setChecked(True)

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

        # "AppShell Configuracion" tampoco es un instalador tradicional:
        # igual que Shares Configuracion, se separa de la cola normal y se
        # aplica aparte con los valores del submenú DEVICE's (ver
        # `_run_appshell_configuration`).
        appshell_entry = self.checkboxes.get("appshell_configuracion")
        apply_appshell = appshell_entry is not None and appshell_entry[0] in selected
        if apply_appshell:
            selected = [it for it in selected if it is not appshell_entry[0]]

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

        if apply_appshell:
            self._run_appshell_configuration(appshell_entry)

        if selected:
            self.install_manager = InstallManager(self.settings.installers_base_path, self)
            self.install_manager.item_started.connect(self._on_item_started)
            self.install_manager.item_finished.connect(self._on_item_finished)
            self.install_manager.queue_finished.connect(self._on_queue_finished)
            self.install_manager.start(selected)
        else:
            # Solo se había marcado Shares Configuracion y/o AppShell
            # Configuracion: no queda nada más que mandar al motor de
            # instalación normal.
            self._on_queue_finished()

    def _run_shares_configuration(self, shares_entry: tuple[AppItem, QCheckBox]) -> None:
        """Aplica la configuración de Shares (ver `app/shares_config_apply.py`):
        primero el .XRF (`apply_shares_configuration`, con CIUDAD y HOSTNAME),
        después el .INF de la carpeta UDF (`apply_udf_configuration`, con
        CIUDAD y — para cada LNIATA marcado (CRT/ATB/BTP/DCP) — su valor), y
        después, si la casilla CONTINGENCIA está marcada,
        `run_contingencia_script()` (corre `Contingencia.bat`, un proceso
        externo real, no una edición de archivo), y por último SIEMPRE
        `create_ltp_shares_shortcuts()` (deja los 2 accesos directos de
        Shares en el escritorio público, con CIUDAD ya resuelto). Refleja
        el resultado en la casilla igual que un ítem normal de la cola."""
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
        contingencia_enabled = self.shares_config_panel.contingencia_check.isChecked()
        bgr_enabled = self.shares_config_panel.bgr_check.isChecked()
        ocr_enabled = self.shares_config_panel.ocr_check.isChecked()
        crt2_enabled = self.shares_config_panel.crt_2_check.isChecked()
        crt4_enabled = self.shares_config_panel.crt_4_check.isChecked()

        self.logger.write(f"{item.label}: iniciando -> CIUDAD={ciudad!r}, HOSTNAME={hostname!r}")
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
                bgr_enabled=bgr_enabled,
                ocr_enabled=ocr_enabled,
                crt2_enabled=crt2_enabled,
                crt4_enabled=crt4_enabled,
            )
            detail = f"{detail_xrf} | {detail_udf}"
            if contingencia_enabled:
                detail_contingencia = run_contingencia_script(self.settings.installers_base_path)
                detail = f"{detail} | {detail_contingencia}"
            detail_shortcuts = create_ltp_shares_shortcuts(ciudad)
            detail = f"{detail} | {detail_shortcuts}"
        except (SharesConfigError, ShortcutError) as exc:
            self.logger.write(f"{item.label}: ERROR - {exc}")
            self._results["error"] += 1
            checkbox.setProperty("installing", "false")
            checkbox.setProperty("failed", "true")
            checkbox.setChecked(False)
            checkbox.setToolTip(f"Error: {exc}")
            checkbox.style().unpolish(checkbox)
            checkbox.style().polish(checkbox)
            self.status_label.setText(f"Shares Configuracion: error - {exc}")
            return

        self.logger.write(f"{item.label}: OK ({detail})")
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
        self.shares_config_panel.reset_contingencia()
        self.shares_config_panel.reset_devices_and_crts()

    def _run_appshell_configuration(self, appshell_entry: tuple[AppItem, QCheckBox]) -> None:
        """Aplica la configuración de AppShell (ver
        `app/appshell_config_apply.py`), en dos partes independientes:

        - ATB/BTP/DCP marcados: agregan su puerto COM y su identificador al
          INI de configuración de AppShell (`apply_appshell_device_config`).
        - BGR/OCR marcados: crean o actualizan `Mastcom.xml` con su sesión
          correspondiente (`apply_appshell_mastcom_config`).

        Si alguna de las dos partes falla (o ninguna casilla del submenú
        está marcada), se refleja como error en la casilla, igual que
        cualquier fallo de instalación normal -- pero solo se resetean
        (desmarcan) las opciones que SÍ llegaron a aplicarse con éxito
        antes del fallo, para que un reintento no las vuelva a aplicar (y
        así duplicar valores ya agregados); las que no se alcanzaron a
        aplicar quedan marcadas, listas para reintentar."""
        item, checkbox = appshell_entry
        checkbox.setProperty("installing", "true")
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        self.status_label.setText("Aplicando configuración de AppShell...")

        device_checks = self.appshell_config_panel.device_checks
        selected_ini_devices = [name for name in ("ATB", "BTP", "DCP") if device_checks[name].isChecked()]
        selected_mastcom_options = [name for name in ("BGR", "OCR") if device_checks[name].isChecked()]

        self.logger.write(f"{item.label}: iniciando -> DEVICE's seleccionados: {selected_ini_devices + selected_mastcom_options}")

        if not selected_ini_devices and not selected_mastcom_options:
            self.logger.write(f"{item.label}: ERROR - No hay ninguna opción de DEVICE's (ATB/BTP/DCP/BGR/OCR) seleccionada.")
            self._results["error"] += 1
            checkbox.setProperty("installing", "false")
            checkbox.setProperty("failed", "true")
            checkbox.setChecked(False)
            checkbox.setToolTip("Error: No hay ninguna opción de DEVICE's (ATB/BTP/DCP/BGR/OCR) seleccionada.")
            checkbox.style().unpolish(checkbox)
            checkbox.style().polish(checkbox)
            self.status_label.setText(
                "AppShell Configuracion: error - No hay ninguna opción de DEVICE's seleccionada."
            )
            return

        applied_names: list[str] = []
        details: list[str] = []
        error: AppShellConfigError | None = None
        try:
            if selected_ini_devices:
                details.append(apply_appshell_device_config(selected_ini_devices))
                applied_names.extend(selected_ini_devices)
            if selected_mastcom_options:
                details.append(apply_appshell_mastcom_config(selected_mastcom_options))
                applied_names.extend(selected_mastcom_options)
        except AppShellConfigError as exc:
            error = exc

        if error is not None:
            self.logger.write(f"{item.label}: ERROR - {error}")
            self._results["error"] += 1
            if applied_names:
                self.appshell_config_panel.reset_device_checks(applied_names)
            checkbox.setProperty("installing", "false")
            checkbox.setProperty("failed", "true")
            checkbox.setChecked(False)
            checkbox.setToolTip(f"Error: {error}")
            checkbox.style().unpolish(checkbox)
            checkbox.style().polish(checkbox)
            self.status_label.setText(f"AppShell Configuracion: error - {error}")
            return

        detail = " | ".join(details)
        self.logger.write(f"{item.label}: OK ({detail})")
        self._results["ok"] += 1
        self._install_records.append((item.label, item.version, datetime.now()))
        checkbox.setProperty("installing", "false")
        checkbox.setVisible(False)
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        self.status_label.setText(f"AppShell Configuracion aplicada ({detail}).")

        # Con la casilla ya oculta, el panel tampoco debe seguir viéndose.
        # Las opciones aplicadas se desmarcan para que una corrida
        # posterior no vuelva a aplicarlas (ver docstring del método).
        self.appshell_config_panel.setVisible(False)
        self.appshell_config_panel.reset_device_checks(applied_names)

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
