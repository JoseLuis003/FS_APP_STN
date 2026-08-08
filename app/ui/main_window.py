"""Ventana principal: catálogo de aplicaciones en 3 columnas + controles."""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    ASSETS_DIR,
    AppItem,
    Settings,
    add_app_item,
    load_app_columns,
    load_settings,
    save_app_versions,
    save_settings,
    slugify_id,
)
from app.installer import InstallManager
from app.installer_detect import detect_silent_args
from app.report import generate_report
from app.ui.styles import build_stylesheet

# Preset del botón NUEVO: catálogo típico para un equipo nuevo.
NUEVO_PRESET_IDS = {
    "bginfo",
    "dell_command",
    "dell_optimizer",
    "dell_ownertag",
    "adobe_reader",
    "forcepoint",
    "google_chrome",
    "ms_teams_work",
    "windows_updates",
    "anyconnect",
    "background",
    "ajustes_necesarios",
    "shortcuts",
    "manage_engine",
    "netfx35",
}

# Preset del botón MTO: catálogo para mantenimiento.
MTO_PRESET_IDS = {
    "isoview",
    "cortana",
    "toolbox_print",
    "shortcut_mto",
}


class CatalogEditorDialog(QDialog):
    """Diálogo 'Editar versiones': una tabla simple donde un compañero de
    soporte puede actualizar la versión de cada aplicación sin tocar el
    archivo apps.json a mano. Guarda directo al archivo y también deja
    actualizados los AppItem que ya está usando la ventana principal."""

    def __init__(self, items: list[AppItem], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar versiones de las aplicaciones")
        self.setMinimumSize(560, 480)
        self.items = items

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar aplicación...")
        self.search_edit.textChanged.connect(self._filter_rows)

        self.table = QTableWidget(len(items), 2)
        self.table.setHorizontalHeaderLabels(["Aplicación", "Versión"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        for row, item in enumerate(items):
            name_cell = QTableWidgetItem(item.label)
            name_cell.setFlags(name_cell.flags() & ~Qt.ItemIsEditable)
            version_text = item.version if item.version and item.version != "N/D" else ""
            version_cell = QTableWidgetItem(version_text)
            self.table.setItem(row, 0, name_cell)
            self.table.setItem(row, 1, version_cell)

        hint = QLabel(
            "Escribe la versión de cada aplicación en la columna derecha y presiona "
            "Guardar. Deja el campo vacío si no aplica (se guarda como \"N/D\")."
        )
        hint.setWordWrap(True)

        save_btn = QPushButton("Guardar")
        cancel_btn = QPushButton("Cancelar")
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.table)
        layout.addLayout(btn_row)

    def _filter_rows(self, text: str) -> None:
        text = text.strip().lower()
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text().lower()
            self.table.setRowHidden(row, text not in name)

    def _on_save(self) -> None:
        updates: dict[str, str] = {}
        for row, item in enumerate(self.items):
            new_version = self.table.item(row, 1).text().strip() or "N/D"
            if new_version != item.version:
                updates[item.id] = new_version
                item.version = new_version  # actualiza el objeto en vivo que usa la ventana principal

        if updates:
            try:
                save_app_versions(updates)
            except Exception as exc:
                QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar apps.json:\n\n{exc}")
                return

        self.accept()


class AddAppDialog(QDialog):
    """Diálogo 'Agregar aplicación': permite sumar al catálogo una aplicación
    que todavía no está en la lista, pidiendo el instalador y sugiriendo (sin
    garantizarlo) el switch de instalación silenciosa según el tipo de
    archivo detectado (ver `app/installer_detect.py`)."""

    _EXTENSION_TYPES = {
        ".exe": "exe",
        ".msi": "msi",
        ".ps1": "script",
        ".bat": "script",
        ".cmd": "script",
    }

    def __init__(self, installers_base_path: str, column_count: int, existing_ids: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar aplicación")
        self.setMinimumWidth(480)
        self.installers_base_path = installers_base_path
        self.existing_ids = existing_ids
        self._installer_path = ""
        self._installer_type = ""

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ej: 7-Zip")

        self.installer_edit = QLineEdit()
        self.installer_edit.setReadOnly(True)
        self.installer_edit.setPlaceholderText("Selecciona el archivo instalador (.exe, .msi, .ps1, .bat)...")
        browse_btn = QPushButton("Examinar...")
        browse_btn.clicked.connect(self._on_browse_installer)
        installer_row = QHBoxLayout()
        installer_row.setContentsMargins(0, 0, 0, 0)
        installer_row.addWidget(self.installer_edit)
        installer_row.addWidget(browse_btn)
        installer_row_widget = QWidget()
        installer_row_widget.setLayout(installer_row)

        self.type_label = QLabel("(selecciona un instalador)")

        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("Ej: /S  o  /qn /norestart")
        detect_btn = QPushButton("Detectar")
        detect_btn.clicked.connect(self._on_detect)
        args_row = QHBoxLayout()
        args_row.setContentsMargins(0, 0, 0, 0)
        args_row.addWidget(self.args_edit)
        args_row.addWidget(detect_btn)
        args_row_widget = QWidget()
        args_row_widget.setLayout(args_row)

        self.detect_hint_label = QLabel()
        self.detect_hint_label.setWordWrap(True)
        self.detect_hint_label.setStyleSheet("color: #444444;")

        self.column_combo = QComboBox()
        for i in range(column_count):
            self.column_combo.addItem(f"Columna {i + 1}", i)

        self.version_edit = QLineEdit()
        self.version_edit.setPlaceholderText("Opcional, ej: 1.2.3")

        form = QFormLayout()
        form.addRow("Nombre a mostrar:", self.name_edit)
        form.addRow("Instalador:", installer_row_widget)
        form.addRow("Tipo detectado:", self.type_label)
        form.addRow("Argumentos silenciosos:", args_row_widget)
        form.addRow("", self.detect_hint_label)
        form.addRow("Columna:", self.column_combo)
        form.addRow("Versión (opcional):", self.version_edit)

        hint = QLabel(
            "El switch que sugiere \"Detectar\" es solo un punto de partida — no hay forma de "
            "garantizarlo sin ejecutar el instalador. Confírmalo tú mismo antes de dejarlo en uso."
        )
        hint.setWordWrap(True)

        save_btn = QPushButton("Agregar")
        cancel_btn = QPushButton("Cancelar")
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(btn_row)

    def _on_browse_installer(self) -> None:
        start_dir = self.installers_base_path if Path(self.installers_base_path).exists() else str(Path.home())
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Selecciona el instalador",
            start_dir,
            "Instaladores (*.exe *.msi *.ps1 *.bat *.cmd)",
        )
        if not path:
            return
        self._installer_path = path
        self.installer_edit.setText(path)
        ext = Path(path).suffix.lower()
        self._installer_type = self._EXTENSION_TYPES.get(ext, "exe")
        self.type_label.setText(self._installer_type)
        self.detect_hint_label.setText("")
        self.args_edit.clear()

    def _on_detect(self) -> None:
        if not self._installer_path:
            QMessageBox.warning(self, "Detectar", "Primero selecciona el archivo instalador.")
            return
        args, explanation = detect_silent_args(Path(self._installer_path), self._installer_type)
        if args:
            self.args_edit.setText(args)
        self.detect_hint_label.setText(explanation)

    def _on_save(self) -> None:
        label = self.name_edit.text().strip()
        if not label:
            QMessageBox.warning(self, "Agregar aplicación", "Escribe el nombre a mostrar.")
            return
        if not self._installer_path:
            QMessageBox.warning(self, "Agregar aplicación", "Selecciona el archivo instalador.")
            return

        base_path = Path(self.installers_base_path)
        installer_path = Path(self._installer_path)
        new_id = slugify_id(label, self.existing_ids)

        try:
            relative_installer = installer_path.resolve().relative_to(base_path.resolve()).as_posix()
        except ValueError:
            # El instalador elegido está fuera de la carpeta base: lo copiamos
            # dentro (en una subcarpeta con el id nuevo) para que quede
            # accesible con una ruta relativa, igual que el resto del catálogo.
            try:
                dest_dir = base_path / new_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / installer_path.name
                shutil.copy2(installer_path, dest_path)
                relative_installer = dest_path.relative_to(base_path).as_posix()
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Error al copiar el instalador",
                    "No se pudo colocar el instalador dentro de la carpeta de instaladores:\n\n"
                    f"{exc}",
                )
                return
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo leer la ruta del instalador:\n\n{exc}")
            return

        item = {
            "id": new_id,
            "label": label,
            "installer": relative_installer,
            "silent_args": self.args_edit.text().strip(),
            "installer_type": self._installer_type or "exe",
            "default_checked": False,
            "enabled": True,
            "version": self.version_edit.text().strip() or "N/D",
        }

        try:
            add_app_item(self.column_combo.currentData(), item)
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo actualizar apps.json:\n\n{exc}")
            return

        self.accept()


class SettingsDialog(QDialog):
    """Diálogo 'AJUSTES': ruta base de instaladores, modo de ejecución, etc."""

    def __init__(self, settings: Settings, items: list[AppItem], column_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.setMinimumWidth(420)
        self.settings = settings
        self.items = items
        self.column_count = column_count
        self.catalog_changed = False

        self.base_path_edit = QLineEdit(settings.installers_base_path)
        self.base_path_edit.setPlaceholderText(r"Ej: C:\Instaladores  o  E:\Instaladores (USB)")
        self.base_path_edit.textChanged.connect(self._update_path_status)

        browse_btn = QPushButton("Examinar...")
        browse_btn.clicked.connect(self._on_browse)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.addWidget(self.base_path_edit)
        path_row.addWidget(browse_btn)
        path_row_widget = QWidget()
        path_row_widget.setLayout(path_row)

        self.path_status_label = QLabel()
        self.path_status_label.setWordWrap(True)

        edit_versions_btn = QPushButton("Editar versiones de las aplicaciones...")
        edit_versions_btn.clicked.connect(self._on_edit_versions)

        add_app_btn = QPushButton("Agregar aplicación...")
        add_app_btn.clicked.connect(self._on_add_app)

        form = QFormLayout()
        form.addRow("Carpeta base de instaladores:", path_row_widget)
        form.addRow("", self.path_status_label)
        form.addRow("", edit_versions_btn)
        form.addRow("", add_app_btn)

        save_btn = QPushButton("Guardar")
        cancel_btn = QPushButton("Cancelar")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btn_row)

        self._update_path_status()

    def _on_edit_versions(self) -> None:
        dialog = CatalogEditorDialog(self.items, self)
        dialog.exec()

    def _on_add_app(self) -> None:
        base_path = self.base_path_edit.text().strip() or self.settings.installers_base_path
        existing_ids = {item.id for item in self.items}
        dialog = AddAppDialog(base_path, self.column_count, existing_ids, self)
        if dialog.exec() == QDialog.Accepted:
            self.catalog_changed = True
            QMessageBox.information(
                self,
                "Aplicación agregada",
                "La aplicación se agregó al catálogo. La lista se actualizará al cerrar Ajustes.",
            )

    def _on_browse(self) -> None:
        current = self.base_path_edit.text().strip()
        start_dir = current if current and Path(current).exists() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecciona la carpeta de instaladores (puede estar en un USB)",
            start_dir,
        )
        if folder:
            # Qt siempre devuelve rutas con '/'; en Windows funcionan igual,
            # pero las normalizamos al separador nativo para que se vea prolijo.
            self.base_path_edit.setText(str(Path(folder)))

    def _update_path_status(self) -> None:
        text = self.base_path_edit.text().strip()
        if not text:
            self.path_status_label.setText("")
            return
        if Path(text).exists():
            self.path_status_label.setText("✓ Carpeta encontrada")
            self.path_status_label.setStyleSheet("color: #1a7a1a;")
        else:
            self.path_status_label.setText(
                "⚠ No se encuentra esa carpeta ahora mismo (verifica que el USB esté conectado)"
            )
            self.path_status_label.setStyleSheet("color: #b03a2e;")

    def result_settings(self) -> Settings:
        self.settings.installers_base_path = self.base_path_edit.text().strip()
        return self.settings


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FS_APP_STN - Instalador desatendido")
        self.setStyleSheet(build_stylesheet(ASSETS_DIR))
        self.resize(900, 650)

        self.settings = load_settings()
        self.columns = load_app_columns()

        # item_id -> (AppItem, QCheckBox)
        self.checkboxes: dict[str, tuple[AppItem, QCheckBox]] = {}
        self.install_manager: InstallManager | None = None

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(30)
        for column in self.columns:
            columns_row.addLayout(self._build_column(column))
        columns_row.addStretch(1)
        root.addLayout(columns_row)
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
        self.progress_bar.setVisible(False)  # solo se muestra mientras algo se está instalando
        status_row.addWidget(self.progress_bar)
        status_row.addStretch(1)

        root.addLayout(status_row)

        root.addLayout(self._build_controls())

    def _build_column(self, column) -> QVBoxLayout:
        col_layout = QVBoxLayout()
        col_layout.setSpacing(2)
        for g_index, group in enumerate(column.groups):
            if g_index > 0:
                col_layout.addSpacing(20)
            for item in group.items:
                checkbox = QCheckBox(item.label)
                checkbox.setChecked(item.default_checked)
                checkbox.setEnabled(item.enabled)
                col_layout.addWidget(checkbox)
                self.checkboxes[item.id] = (item, checkbox)
        col_layout.addStretch(1)
        return col_layout

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()

        grid = QGridLayout()
        nuevo_btn = QPushButton("NUEVO")
        unselect_btn = QPushButton("UNSELECT")
        ajustes_btn = QPushButton("AJUSTES")
        mto_btn = QPushButton("MTO")

        nuevo_btn.clicked.connect(self._on_nuevo)
        unselect_btn.clicked.connect(self._on_unselect)
        ajustes_btn.clicked.connect(self._on_ajustes)
        mto_btn.clicked.connect(self._on_mto)

        grid.addWidget(nuevo_btn, 0, 0)
        grid.addWidget(unselect_btn, 0, 1)
        grid.addWidget(ajustes_btn, 0, 2)
        grid.addWidget(mto_btn, 1, 0)

        row.addLayout(grid)
        row.addStretch(1)

        self.installar_btn = QPushButton("INSTALAR")
        self.installar_btn.setObjectName("installarButton")
        self.installar_btn.setMinimumSize(160, 70)
        self.installar_btn.clicked.connect(self._on_installar)
        row.addWidget(self.installar_btn)

        return row

    # ------------------------------------------------------------- acciones
    def _apply_preset(self, preset_ids: set[str]) -> None:
        """Deja seleccionados unicamente los items de `preset_ids` (el resto
        queda sin marcar), respetando los que estan deshabilitados."""
        for item, checkbox in self.checkboxes.values():
            if not checkbox.isEnabled():
                continue
            checkbox.setChecked(item.id in preset_ids)

    def _on_unselect(self) -> None:
        for _item, checkbox in self.checkboxes.values():
            checkbox.setChecked(False)

    def _on_ajustes(self) -> None:
        items = [item for item, _checkbox in self.checkboxes.values()]
        dialog = SettingsDialog(self.settings, items, len(self.columns), self)
        accepted = dialog.exec() == QDialog.Accepted
        if accepted:
            self.settings = dialog.result_settings()
            save_settings(self.settings)
            self.status_label.setText("Ajustes guardados.")
        if dialog.catalog_changed:
            self._reload_catalog()
            if not accepted:
                self.status_label.setText("Catálogo actualizado: se agregó una nueva aplicación.")

    def _reload_catalog(self) -> None:
        """Vuelve a leer `config/apps.json` y reconstruye la lista de
        checkboxes (usado después de agregar una aplicación nueva desde
        AJUSTES), preservando la selección actual de los ítems que siguen
        existiendo."""
        checked_ids = {
            item_id for item_id, (_item, checkbox) in self.checkboxes.items() if checkbox.isChecked()
        }
        self.checkboxes = {}
        self.columns = load_app_columns()
        self._build_ui()
        for item_id, (_item, checkbox) in self.checkboxes.items():
            if item_id in checked_ids:
                checkbox.setChecked(True)

    def _on_nuevo(self) -> None:
        self._apply_preset(NUEVO_PRESET_IDS)
        self.status_label.setText("Selección aplicada: catálogo de equipo nuevo.")

    def _on_mto(self) -> None:
        self._apply_preset(MTO_PRESET_IDS)
        self.status_label.setText("Selección aplicada: catálogo de mantenimiento (MTO).")

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
        # Los instaladores silenciosos no reportan % de avance real, así que
        # se muestra en modo indeterminado ("barra que va y viene").
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

    def _on_item_finished(self, item_id: str, success: bool, message: str) -> None:
        item, checkbox = self.checkboxes[item_id]
        checkbox.setProperty("installing", "false")
        if success:
            self._results["ok"] += 1
            self._install_records.append((item.label, item.version, datetime.now()))
            # Al llegar al 100%, el ítem desaparece de la lista (igual que la app original).
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
            report_html, _report_csv = generate_report(self._install_records)
            report_msg = f"\n\nReporte generado en:\n{report_html}"
        except Exception as exc:  # nunca bloquear el flujo de instalación por el reporte
            report_html = None
            report_msg = f"\n\nNo se pudo generar el reporte: {exc}"

        QMessageBox.information(
            self,
            "Instalación finalizada",
            f"Completadas: {ok}\nCon error: {error}\n\nRevisa la carpeta 'logs' para el detalle.{report_msg}",
        )

        if report_html and sys.platform == "win32":
            try:
                os.startfile(report_html)  # abre el reporte en el navegador por defecto
            except OSError:
                pass

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.installar_btn.setEnabled(enabled)
        for _item, checkbox in self.checkboxes.values():
            checkbox.setEnabled(enabled and _item.enabled)
