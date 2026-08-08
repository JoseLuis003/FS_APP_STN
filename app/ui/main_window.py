"""Ventana principal: catálogo de aplicaciones en 3 columnas + controles."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import AppItem, Settings, load_app_columns, load_settings, save_settings
from app.installer import InstallManager
from app.ui.styles import MAIN_STYLESHEET


class SettingsDialog(QDialog):
    """Diálogo 'AJUSTES': ruta base de instaladores, modo de ejecución, etc."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.settings = settings

        self.base_path_edit = QLineEdit(settings.installers_base_path)
        self.confirm_checkbox = QCheckBox("Confirmar antes de instalar")
        self.confirm_checkbox.setChecked(settings.confirm_before_install)

        form = QFormLayout()
        form.addRow("Carpeta base de instaladores:", self.base_path_edit)
        form.addRow("", self.confirm_checkbox)

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

    def result_settings(self) -> Settings:
        self.settings.installers_base_path = self.base_path_edit.text().strip()
        self.settings.confirm_before_install = self.confirm_checkbox.isChecked()
        return self.settings


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FS_APP_STN - Instalador desatendido")
        self.setStyleSheet(MAIN_STYLESHEET)
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

        self.status_label = QLabel("Listo.")
        self.status_label.setObjectName("statusBar")
        root.addWidget(self.status_label)

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
        atras_btn = QPushButton("ATRAS")
        mto_btn = QPushButton("MTO")

        nuevo_btn.clicked.connect(self._on_nuevo)
        unselect_btn.clicked.connect(self._on_unselect)
        ajustes_btn.clicked.connect(self._on_ajustes)
        atras_btn.clicked.connect(self._on_atras)
        mto_btn.clicked.connect(self._on_mto)

        grid.addWidget(nuevo_btn, 0, 0)
        grid.addWidget(unselect_btn, 0, 1)
        grid.addWidget(ajustes_btn, 0, 2)
        grid.addWidget(atras_btn, 1, 0)
        grid.addWidget(mto_btn, 1, 1)

        row.addLayout(grid)
        row.addStretch(1)

        self.installar_btn = QPushButton("INSTALAR")
        self.installar_btn.setObjectName("installarButton")
        self.installar_btn.setMinimumSize(160, 70)
        self.installar_btn.clicked.connect(self._on_installar)
        row.addWidget(self.installar_btn)

        return row

    # ------------------------------------------------------------- acciones
    def _on_unselect(self) -> None:
        for _item, checkbox in self.checkboxes.values():
            checkbox.setChecked(False)

    def _on_ajustes(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.settings = dialog.result_settings()
            save_settings(self.settings)
            self.status_label.setText("Ajustes guardados.")

    def _on_nuevo(self) -> None:
        # TODO: definir junto al equipo de IT qué debe hacer "NUEVO"
        # (¿nuevo perfil de equipo? ¿limpiar catálogo actual?).
        QMessageBox.information(self, "NUEVO", "Funcionalidad pendiente de definir.")

    def _on_atras(self) -> None:
        # TODO: definir navegación de "ATRAS" (pantalla anterior / wizard).
        QMessageBox.information(self, "ATRAS", "Funcionalidad pendiente de definir.")

    def _on_mto(self) -> None:
        # TODO: definir alcance de "MTO" (¿modo mantenimiento?).
        QMessageBox.information(self, "MTO", "Funcionalidad pendiente de definir.")

    def _on_installar(self) -> None:
        selected: list[AppItem] = [
            item for item, checkbox in self.checkboxes.values() if checkbox.isEnabled() and checkbox.isChecked()
        ]
        if not selected:
            QMessageBox.warning(self, "Instalar", "No hay ninguna aplicación seleccionada.")
            return

        if self.settings.confirm_before_install:
            nombres = "\n".join(f"- {item.label}" for item in selected)
            resp = QMessageBox.question(
                self,
                "Confirmar instalación",
                f"Se instalarán {len(selected)} aplicación(es):\n\n{nombres}\n\n¿Continuar?",
            )
            if resp != QMessageBox.Yes:
                return

        self._set_controls_enabled(False)
        self._results = {"ok": 0, "error": 0}

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

    def _on_item_finished(self, item_id: str, success: bool, message: str) -> None:
        item, checkbox = self.checkboxes[item_id]
        checkbox.setProperty("installing", "false")
        if success:
            self._results["ok"] += 1
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
        ok = self._results["ok"]
        error = self._results["error"]
        self.status_label.setText(f"Instalación finalizada: {ok} correctas, {error} con error.")
        QMessageBox.information(
            self,
            "Instalación finalizada",
            f"Completadas: {ok}\nCon error: {error}\n\nRevisa la carpeta 'logs' para el detalle.",
        )

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.installar_btn.setEnabled(enabled)
        for _item, checkbox in self.checkboxes.values():
            checkbox.setEnabled(enabled and _item.enabled)
