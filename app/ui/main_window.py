"""Ventana principal: catálogo de aplicaciones en 3 columnas + controles."""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QRegularExpressionValidator
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
    QInputDialog,
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
    APPS_FILE,
    ASSETS_DIR,
    AppItem,
    Settings,
    add_app_item,
    load_app_columns,
    load_settings,
    remove_app_item,
    save_app_versions,
    save_settings,
    slugify_id,
    update_app_installer,
)
from app.copa_id_setup import (
    CopaIdSetupError,
    apply_copa_id_asset_tag,
    detect_current_asset_tag,
    is_valid_asset_tag,
)
from app.installer import InstallLogger, InstallManager
from app.installer_detect import detect_silent_args
from app.report import REBOOT_PENDING_VERSION_LABEL, generate_report, is_reboot_pending_message
from app.ui.catalog_widgets import build_checkbox_column, reapply_exclusive_constraints, wire_linked_groups

# Id del ítem especial "Copa ID (Asset Tag)" (columna 1, junto a los demás
# ítems de Dell -- ver `app/copa_id_setup.py` para el detalle completo del
# porqué de este ítem: no es un checkbox más, tiene un campo de texto al
# lado (`self.asset_tag_edit`) y no pasa por el motor de instalación
# genérico -- se saca de la cola en `_on_installar()` y se aplica aparte,
# igual que "Shares Configuracion"/"AppShell Configuracion" en LTP / CSS
# (ver `app/ui/ltp_css_window.py`).
COPA_ID_ITEM_ID = "copa_id"

# Id del ítem "REGISTRO EN AD" -- a diferencia de "Copa ID", SÍ pasa por el
# motor de instalación genérico normal (3 pasos: hotfix .msu, RSAT AD DS/LDS
# Tools, y por último `Scripts/REG_AD.ps1`, ver `config/apps.json` y
# `app/rsat_setup.py`), pero además tiene un campo de texto al lado
# (`self.owner_user_edit`) donde el técnico escribe el usuario de dominio
# del DUEÑO real del equipo (ej. "jperez", sin "@copaair.com" -- mismo
# formato que espera `Get-ADUser -Identity` en REG_AD.ps1).
#
# Pedido explícito de campo: antes, `REG_AD.ps1` tomaba este usuario
# automáticamente de `$env:USERNAME` (la sesión de Windows con la que corre
# FS_APP_STN.exe) -- una corrección ANTERIOR había quitado a propósito un
# `Read-Host` interactivo ahí porque colgaba la ejecución desatendida
# esperando una respuesta que nunca llegaba (ver REG_AD.ps1). El problema
# real de campo: en la práctica esa sesión de Windows suele ser una cuenta
# local genérica del técnico (ej. "CM"), NO el usuario final que va a ser
# dueño del equipo -- así que "ManagedBy" quedaba mal asignado en AD.
#
# Solución: en vez de un diálogo emergente (que sorprendería si hay más
# ítems marcados junto con este, y no se podría prellenar/corregir con
# tranquilidad antes de arrancar la cola), se usa el mismo mecanismo que
# "Copa ID (Asset Tag)": un campo de texto SIEMPRE visible en la fila del
# ítem, vía `inline_widgets` (ver `_build_ui`). A diferencia de Copa ID,
# este ítem SÍ sigue pasando por la cola normal -- el valor del campo no se
# le pasa como argumento de línea de comandos a `REG_AD.ps1` (eso
# necesitaría cambiar el motor genérico de `InstallWorker` para un caso
# especial más), sino por una variable de entorno
# (`FS_APP_STN_AD_OWNER_USER`) que se define en el proceso ANTES de
# arrancar la cola (ver `_on_installar`) -- `subprocess.run` (que usa
# `InstallWorker` para correr cada paso) hereda el entorno del proceso
# padre por defecto, así que `REG_AD.ps1` la ve sin ningún cambio en
# `app/installer.py`. Si por algún motivo la variable no llegara a estar
# (ej. alguien corre el script a mano fuera de la app), `REG_AD.ps1` cae de
# vuelta a `$env:USERNAME` como antes -- nunca falla por falta de este dato.
REGISTRO_AD_ITEM_ID = "registro_ad"

# Preset del botón NUEVO: catálogo típico para un equipo nuevo.
NUEVO_PRESET_IDS = {
    "bginfo",
    "dell_command",
    "dell_optimizer",
    "dell_ownertag",
    "adobe_reader",
    "forcepoint",
    "crowdstrike",
    "google_chrome",
    "ms_teams_work",
    "windows_updates",
    "anyconnect",
    "background",
    "ajustes_necesarios",
    "registro_ad",
    "rsat_ad_tools",
    "shortcuts",
    "manage_engine",
    "windows_activation",
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
    """Diálogo 'Editar versiones': una tabla donde un compañero de soporte
    puede, sin tocar `apps.json` a mano:
    - escribir la versión de cada aplicación (columna "Versión" + botón
      Guardar, como antes);
    - reemplazar el instalador de una app por uno nuevo ("Actualizar
      instalador..."), que copia el archivo elegido a la carpeta de esa app
      dentro de APPS y actualiza el catálogo al instante;
    - eliminar una app del catálogo y borrar su carpeta dentro de APPS
      ("Eliminar").
    Actualizar y Eliminar aplican de inmediato (son operaciones de archivo,
    no se pueden "deshacer" con Cancelar); la columna Versión solo se guarda
    al presionar Guardar.

    `apps_file` indica sobre qué catálogo JSON operar: por defecto
    `config/apps.json` (pantalla APPS), pero la pantalla LTP / CSS reutiliza
    este mismo diálogo pasándole `LTP_CSS_APPS_FILE` para editar
    `config/ltp_css_apps.json` en su lugar."""

    def __init__(
        self,
        items: list[AppItem],
        installers_base_path: str,
        apps_file: Path = APPS_FILE,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Editar aplicaciones del catálogo")
        self.setMinimumSize(720, 480)
        self.items = list(items)
        self.installers_base_path = installers_base_path
        self.apps_file = apps_file
        # True si Actualizar instalador o Eliminar se usaron (afecta el
        # catálogo aunque se presione Cancelar, porque ya se escribió en
        # disco) -- MainWindow usa esto para saber si debe recargar la lista.
        self.catalog_changed = False

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar aplicación...")
        self.search_edit.textChanged.connect(self._filter_rows)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Aplicación", "Versión", "", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        hint = QLabel(
            "Columna \"Versión\": escríbela y presiona Guardar (se guarda como \"N/D\" si "
            "queda vacía). \"Actualizar instalador...\" y \"Eliminar\" aplican de inmediato, "
            "sin esperar a Guardar."
        )
        hint.setWordWrap(True)

        save_btn = QPushButton("Guardar")
        cancel_btn = QPushButton("Cerrar")
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self._on_close)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.table)
        layout.addLayout(btn_row)

        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            name_cell = QTableWidgetItem(item.label)
            name_cell.setFlags(name_cell.flags() & ~Qt.ItemIsEditable)
            version_text = item.version if item.version and item.version != "N/D" else ""
            version_cell = QTableWidgetItem(version_text)
            self.table.setItem(row, 0, name_cell)
            self.table.setItem(row, 1, version_cell)

            update_btn = QPushButton("Actualizar instalador...")
            update_btn.setStyleSheet("font-size: 11px; padding: 6px 10px;")
            update_btn.clicked.connect(lambda checked=False, it=item: self._on_update_installer(it))
            self.table.setCellWidget(row, 2, update_btn)

            delete_btn = QPushButton("Eliminar")
            delete_btn.setStyleSheet("font-size: 11px; padding: 6px 10px; color: #b03a2e; font-weight: 600;")
            delete_btn.clicked.connect(lambda checked=False, it=item: self._on_delete_item(it))
            self.table.setCellWidget(row, 3, delete_btn)

    def _filter_rows(self, text: str) -> None:
        text = text.strip().lower()
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text().lower()
            self.table.setRowHidden(row, text not in name)

    def _on_update_installer(self, item: AppItem) -> None:
        start_dir = self.installers_base_path if Path(self.installers_base_path).exists() else str(Path.home())
        new_path, _filter = QFileDialog.getOpenFileName(
            self,
            f'Nuevo instalador para "{item.label}"',
            start_dir,
            "Instaladores (*.exe *.msi *.ps1 *.bat *.cmd)",
        )
        if not new_path:
            return

        base_path = Path(self.installers_base_path)
        new_file = Path(new_path)
        current_rel = Path(item.installer)
        # Se copia a la misma carpeta que ya tenía asignada esa app dentro
        # de APPS (o a una carpeta nueva con su id, si por algún motivo no
        # tenía subcarpeta propia).
        target_dir = base_path / current_rel.parent if str(current_rel.parent) not in ("", ".") else base_path / item.id

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / new_file.name
            shutil.copy2(new_file, target_path)
            old_path = base_path / item.installer
            # Si el instalador nuevo tiene otro nombre de archivo, borramos
            # el anterior para no dejar basura en la carpeta de esa app.
            if old_path.exists() and old_path.resolve() != target_path.resolve():
                old_path.unlink()
            new_relative = target_path.relative_to(base_path).as_posix()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error al actualizar", f"No se pudo copiar el nuevo instalador:\n\n{exc}"
            )
            return

        current_version = item.version if item.version and item.version != "N/D" else ""
        new_version, ok = QInputDialog.getText(
            self,
            "Versión del instalador",
            f'Versión de "{item.label}" (déjalo vacío si no aplica):',
            text=current_version,
        )
        new_version = (new_version.strip() or "N/D") if ok else item.version

        try:
            update_app_installer(item.id, installer=new_relative, version=new_version, apps_file=self.apps_file)
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo actualizar apps.json:\n\n{exc}")
            return

        item.installer = new_relative
        item.version = new_version
        self.catalog_changed = True
        self._populate_table()
        QMessageBox.information(self, "Instalador actualizado", f'Se actualizó el instalador de "{item.label}".')

    def _on_delete_item(self, item: AppItem) -> None:
        confirm = QMessageBox.question(
            self,
            "Eliminar aplicación",
            f'¿Eliminar "{item.label}" del catálogo y borrar su carpeta dentro de APPS?\n\n'
            "Esta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            remove_app_item(item.id, apps_file=self.apps_file)
        except Exception as exc:
            QMessageBox.critical(self, "Error al eliminar", f"No se pudo actualizar apps.json:\n\n{exc}")
            return

        base_path = Path(self.installers_base_path)
        folder = base_path / Path(item.installer).parent
        try:
            # No borrar si la carpeta resultante es la propia carpeta base
            # (pasaría si el instalador no tenía subcarpeta propia) -- eso
            # borraría TODO el contenido de APPS por error.
            if folder.exists() and folder.is_dir() and folder.resolve() != base_path.resolve():
                shutil.rmtree(folder)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Aviso",
                f'"{item.label}" se eliminó del catálogo, pero no se pudo borrar su carpeta:\n\n{exc}',
            )

        self.items = [it for it in self.items if it.id != item.id]
        self.catalog_changed = True
        self._populate_table()

    def _on_save(self) -> None:
        updates: dict[str, str] = {}
        for row, item in enumerate(self.items):
            new_version = self.table.item(row, 1).text().strip() or "N/D"
            if new_version != item.version:
                updates[item.id] = new_version
                item.version = new_version  # actualiza el objeto en vivo que usa la ventana principal

        if updates:
            try:
                save_app_versions(updates, apps_file=self.apps_file)
            except Exception as exc:
                QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar apps.json:\n\n{exc}")
                return

        self.accept()

    def _on_close(self) -> None:
        # "Cerrar" en vez de "Cancelar": Actualizar instalador y Eliminar ya
        # escribieron en disco (self.catalog_changed ya quedó en True si se
        # usaron), así que no hay nada que "descartar" para esos cambios --
        # solo se pierden ediciones de versión que no se guardaron con
        # el botón Guardar.
        self.reject()


class AddAppDialog(QDialog):
    """Diálogo 'Agregar aplicación': permite sumar al catálogo una aplicación
    que todavía no está en la lista, pidiendo el instalador y sugiriendo (sin
    garantizarlo) el switch de instalación silenciosa según el tipo de
    archivo detectado (ver `app/installer_detect.py`).

    `apps_file` indica en qué catálogo JSON se agrega el ítem nuevo: por
    defecto `config/apps.json` (pantalla APPS); la pantalla LTP / CSS
    reutiliza este diálogo pasándole `LTP_CSS_APPS_FILE`."""

    _EXTENSION_TYPES = {
        ".exe": "exe",
        ".msi": "msi",
        ".ps1": "script",
        ".bat": "script",
        ".cmd": "script",
    }

    def __init__(
        self,
        installers_base_path: str,
        column_count: int,
        existing_ids: set[str],
        apps_file: Path = APPS_FILE,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Agregar aplicación")
        self.setMinimumWidth(480)
        self.installers_base_path = installers_base_path
        self.existing_ids = existing_ids
        self.apps_file = apps_file
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
            add_app_item(self.column_combo.currentData(), item, apps_file=self.apps_file)
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo actualizar apps.json:\n\n{exc}")
            return

        self.accept()


# PIN que protege "Editar versiones de las aplicaciones..." y "Agregar
# aplicación..." dentro de Ajustes (pedido explícito): son los únicos 2
# botones que modifican el catálogo (config/apps.json o
# config/ltp_css_apps.json) -- el resto de Ajustes (carpeta base de
# instaladores) queda sin PIN, cualquier técnico lo puede tocar.
SETTINGS_CATALOG_PIN = "0303"


class SettingsDialog(QDialog):
    """Diálogo 'AJUSTES': ruta base de instaladores, modo de ejecución, etc.

    `apps_file` indica sobre qué catálogo JSON operan "Editar versiones..."
    y "Agregar aplicación...": por defecto `config/apps.json` (pantalla
    APPS); la pantalla LTP / CSS reutiliza este mismo diálogo pasándole
    `LTP_CSS_APPS_FILE` para que ambos botones editen
    `config/ltp_css_apps.json` en su lugar. La carpeta base de instaladores
    (`installers_base_path`) es compartida entre ambas pantallas -- no hay
    nada que parametrizar ahí."""

    def __init__(
        self,
        settings: Settings,
        items: list[AppItem],
        column_count: int,
        apps_file: Path = APPS_FILE,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.setMinimumWidth(420)
        self.settings = settings
        self.items = items
        self.column_count = column_count
        self.apps_file = apps_file
        self.catalog_changed = False

        self.base_path_edit = QLineEdit(settings.installers_base_path)
        self.base_path_edit.setPlaceholderText(r"Ej: C:\CM APPS\APPS  o  E:\CM APPS\APPS (USB)")
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

    def _check_catalog_pin(self) -> bool:
        """Pide el PIN (`SETTINGS_CATALOG_PIN`) antes de abrir "Editar
        versiones..." o "Agregar aplicación..." -- los 2 únicos botones de
        Ajustes que modifican el catálogo. Devuelve `True` solo si el PIN
        ingresado es correcto; si el técnico cancela el diálogo o lo
        escribe mal, devuelve `False` (y avisa con un mensaje en el
        segundo caso) sin abrir nada."""
        pin, ok = QInputDialog.getText(
            self,
            "PIN requerido",
            "Ingresa el PIN para continuar:",
            echo=QLineEdit.Password,
        )
        if not ok:
            return False
        if pin != SETTINGS_CATALOG_PIN:
            QMessageBox.warning(self, "PIN incorrecto", "El PIN ingresado no es correcto.")
            return False
        return True

    def _on_edit_versions(self) -> None:
        if not self._check_catalog_pin():
            return
        base_path = self.base_path_edit.text().strip() or self.settings.installers_base_path
        dialog = CatalogEditorDialog(self.items, base_path, apps_file=self.apps_file, parent=self)
        dialog.exec()
        if dialog.catalog_changed:
            self.catalog_changed = True

    def _on_add_app(self) -> None:
        if not self._check_catalog_pin():
            return
        base_path = self.base_path_edit.text().strip() or self.settings.installers_base_path
        existing_ids = {item.id for item in self.items}
        dialog = AddAppDialog(base_path, self.column_count, existing_ids, apps_file=self.apps_file, parent=self)
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


# Tamaño de ventana por defecto al abrir (pedido explícito: igual que
# LTP / CSS, ver `app/ui/ltp_css_window.py`). La ventana sigue siendo
# redimensionable con normalidad -- esto es solo el tamaño INICIAL, no un
# límite; ver `_initial_window_size`, que además lo recorta si la
# pantalla del técnico es más chica que eso (por ejemplo un laptop con
# poca resolución o con la barra de tareas ocupando espacio), para que la
# ventana siempre entre completa.
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


class MainWindow(QMainWindow):
    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.setWindowTitle("FS APP PORTABLE - APPS")
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "app_icon.ico")))
        # La hoja de estilos (checkboxes, botones, QMessageBox, etc.) se
        # aplica a nivel de QApplication en `main.py` -- así también la
        # heredan los QMessageBox de esta ventana, que son diálogos de
        # nivel superior aparte y no heredan un `.setStyleSheet()` puesto
        # solo acá (ver comentario en `main.py`).
        self.resize(*_initial_window_size())

        # Si se abrió desde la portada (FS APP PORTABLE -> APPS), este
        # callback regresa a esa pantalla; si no se indica, ATRAS simplemente
        # cierra esta ventana.
        self._on_back = on_back

        self.settings = load_settings()
        self.columns = load_app_columns()

        # item_id -> (AppItem, QCheckBox)
        self.checkboxes: dict[str, tuple[AppItem, QCheckBox]] = {}
        self.install_manager: InstallManager | None = None

        # "Copa ID (Asset Tag)" no pasa por `InstallManager`/`InstallWorker`
        # (ver `_run_copa_id_asset_tag`), así que sin este logger propio su
        # resultado solo quedaría en la casilla y en `status_label` -- nunca
        # en la carpeta `logs` (mismo motivo que el logger propio de
        # `LtpCssWindow`, ver ese archivo).
        self.logger = InstallLogger()

        self._build_ui()

        # Revisa cada pocos segundos si la carpeta de instaladores sigue
        # existiendo (por ejemplo, si conectan la USB despues de abrir la
        # app, o si la desconectan) para que el indicador arriba de
        # INSTALAR siempre este al dia sin tener que reabrir AJUSTES.
        self._path_check_timer = QTimer(self)
        self._path_check_timer.timeout.connect(self._update_active_path_label)
        self._path_check_timer.start(3000)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # "Copa ID (Asset Tag)" se arma ANTES de las columnas y se le pasa a
        # `build_checkbox_column` como `inline_widgets` -- así el campo de
        # texto queda dibujado dentro de la columna 1, justo debajo de esa
        # casilla, en vez de aparte (mismo mecanismo que usa
        # `AppShellConfigPanel` en `app/ui/ltp_css_window.py`).
        self.asset_tag_edit = self._build_asset_tag_edit()
        self.owner_user_edit = self._build_owner_user_edit()
        inline_widgets = {COPA_ID_ITEM_ID: self.asset_tag_edit, REGISTRO_AD_ITEM_ID: self.owner_user_edit}

        columns_row = QHBoxLayout()
        columns_row.setSpacing(30)
        for column in self.columns:
            columns_row.addLayout(self._build_column(column, inline_widgets))
        # Enlaza ítems de un mismo `linked_group` (ej. REGISTRO EN AD y
        # RSAT) -- tiene que hacerse DESPUÉS de armar todas las columnas
        # porque sus miembros pueden vivir en columnas distintas (ver
        # docstring de `wire_linked_groups`).
        wire_linked_groups(self.checkboxes)
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

    def _build_column(self, column, inline_widgets: dict | None = None) -> QVBoxLayout:
        return build_checkbox_column(column, self.checkboxes, inline_widgets)

    def _build_asset_tag_edit(self) -> QLineEdit:
        """Construye el campo de texto de "Copa ID (Asset Tag)": solo
        permite dígitos, hasta 6 (validador + `setMaxLength` como respaldo),
        y se prellena con el Asset Tag que YA tenga configurado el equipo
        (vía WMI, ver `app.copa_id_setup.detect_current_asset_tag`) -- si no
        hay ninguno válido, queda vacío con el placeholder "NO SETUP" en vez
        de prellenarlo con un valor que de todos modos no pasaría la
        validación."""
        edit = QLineEdit()
        edit.setMaxLength(6)
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d{0,6}$")))
        edit.setPlaceholderText("NO SETUP")
        detected = detect_current_asset_tag()
        if detected:
            edit.setText(detected)
        return edit

    def _build_owner_user_edit(self) -> QLineEdit:
        """Construye el campo de texto de "REGISTRO EN AD": el usuario de
        dominio (ej. "jperez") del dueño real del equipo, que
        `_on_installar` valida y pasa a `REG_AD.ps1` vía la variable de
        entorno `FS_APP_STN_AD_OWNER_USER` (ver `REGISTRO_AD_ITEM_ID` más
        arriba para el porqué). Empieza vacío a propósito -- a diferencia
        del Asset Tag (que sí se puede detectar solo por WMI), no hay forma
        de adivinar quién va a ser el dueño de un equipo recién
        provisionado; que el técnico lo escriba siempre a mano evita
        registrar por error a la cuenta local genérica de turno."""
        edit = QLineEdit()
        edit.setPlaceholderText("usuario de dominio (ej. jperez)")
        return edit

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()

        grid = QGridLayout()
        nuevo_btn = QPushButton("NUEVO")
        unselect_btn = QPushButton("UNSELECT")
        ajustes_btn = QPushButton("AJUSTES")
        mto_btn = QPushButton("MTO")
        atras_btn = QPushButton("ATRAS")

        nuevo_btn.clicked.connect(self._on_nuevo)
        unselect_btn.clicked.connect(self._on_unselect)
        ajustes_btn.clicked.connect(self._on_ajustes)
        mto_btn.clicked.connect(self._on_mto)
        atras_btn.clicked.connect(self._on_atras)

        grid.addWidget(nuevo_btn, 0, 0)
        grid.addWidget(unselect_btn, 0, 1)
        grid.addWidget(ajustes_btn, 0, 2)
        grid.addWidget(mto_btn, 1, 0)
        grid.addWidget(atras_btn, 1, 1)

        row.addLayout(grid)
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
        """Refleja en pantalla, justo arriba del botón INSTALAR, la carpeta
        de instaladores que la app está usando en este momento y si existe
        ahora mismo (en verde) o no (en rojo) — así el técnico sabe de un
        vistazo si puede darle INSTALAR con confianza, sin tener que
        intentarlo y enterarse después por el log que la carpeta no
        estaba."""
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

    def _on_atras(self) -> None:
        """Regresa a la portada (FS APP PORTABLE) si esta ventana se abrió
        desde ahí; si no, simplemente cierra esta ventana."""
        if self._on_back is not None:
            self._on_back()
        else:
            self.close()

    def _on_ajustes(self) -> None:
        items = [item for item, _checkbox in self.checkboxes.values()]
        dialog = SettingsDialog(self.settings, items, len(self.columns), apps_file=APPS_FILE, parent=self)
        accepted = dialog.exec() == QDialog.Accepted
        if accepted:
            self.settings = dialog.result_settings()
            save_settings(self.settings)
            self.status_label.setText("Ajustes guardados.")
        if dialog.catalog_changed:
            self._reload_catalog()
            if not accepted:
                self.status_label.setText("Catálogo actualizado: se agregó una nueva aplicación.")
        self._update_active_path_label()

    def _reload_catalog(self) -> None:
        """Vuelve a leer `config/apps.json` y reconstruye la lista de
        checkboxes (usado después de agregar una aplicación nueva desde
        AJUSTES), preservando la selección actual de los ítems que siguen
        existiendo."""
        checked_ids = {
            item_id for item_id, (_item, checkbox) in self.checkboxes.items() if checkbox.isChecked()
        }
        # Preserva lo que el técnico haya escrito en "Copa ID (Asset Tag)"
        # -- si no, `_build_ui()` lo reemplazaría por lo que detecte WMI de
        # nuevo, descartando una corrección manual que el técnico ya hizo.
        asset_tag_text = self.asset_tag_edit.text() if hasattr(self, "asset_tag_edit") else ""
        # Mismo motivo que `asset_tag_text` arriba: no perder lo que el
        # técnico ya haya escrito en "REGISTRO EN AD" al reconstruir la UI.
        owner_user_text = self.owner_user_edit.text() if hasattr(self, "owner_user_edit") else ""
        self.checkboxes = {}
        self.columns = load_app_columns()
        self._build_ui()
        for item_id, (_item, checkbox) in self.checkboxes.items():
            if item_id in checked_ids:
                checkbox.setChecked(True)
        if asset_tag_text:
            self.asset_tag_edit.setText(asset_tag_text)
        if owner_user_text:
            self.owner_user_edit.setText(owner_user_text)

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

        # "Copa ID (Asset Tag)" no es un instalador tradicional: se saca de
        # la cola normal y se aplica aparte, con el valor que haya en
        # `self.asset_tag_edit` (ver `_run_copa_id_asset_tag` y el docstring
        # de `app/copa_id_setup.py`).
        copa_id_entry = self.checkboxes.get(COPA_ID_ITEM_ID)
        apply_copa_id = copa_id_entry is not None and copa_id_entry[0] in selected
        asset_tag_value = self.asset_tag_edit.text().strip() if apply_copa_id else ""
        if apply_copa_id:
            selected = [it for it in selected if it is not copa_id_entry[0]]
            if not is_valid_asset_tag(asset_tag_value):
                QMessageBox.warning(
                    self,
                    "Copa ID (Asset Tag)",
                    "El Asset Tag debe ser exactamente 6 dígitos numéricos antes de presionar INSTALAR.",
                )
                return

        # "REGISTRO EN AD" SÍ pasa por la cola normal (a diferencia de Copa
        # ID) -- acá solo se valida que el técnico haya escrito el usuario
        # owner y se lo deja listo en una variable de entorno para que
        # `REG_AD.ps1` lo use en vez de `$env:USERNAME` (ver
        # `REGISTRO_AD_ITEM_ID` para el detalle completo del mecanismo).
        registro_ad_entry = self.checkboxes.get(REGISTRO_AD_ITEM_ID)
        apply_registro_ad = registro_ad_entry is not None and registro_ad_entry[0] in selected
        if apply_registro_ad:
            owner_user_value = self.owner_user_edit.text().strip()
            if not owner_user_value:
                QMessageBox.warning(
                    self,
                    "REGISTRO EN AD",
                    "Escribe el usuario de dominio del dueño del equipo (ej. \"jperez\") antes de "
                    "presionar INSTALAR.",
                )
                return
            os.environ["FS_APP_STN_AD_OWNER_USER"] = owner_user_value

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
        self._install_records: list[tuple[str, str, datetime, bool]] = []

        # Se aplica ya mismo, sincrónico en el hilo de la UI -- a diferencia
        # de "Shares Configuracion"/"AppShell Configuracion" en LTP / CSS, no
        # hace falta diferirlo a `_on_queue_finished()`: no depende de que
        # ningún otro ítem de la cola termine antes (ver
        # `app/copa_id_setup.py`).
        if apply_copa_id:
            self._run_copa_id_asset_tag(copa_id_entry, asset_tag_value)

        if selected:
            self.install_manager = InstallManager(self.settings.installers_base_path, self)
            self.install_manager.item_started.connect(self._on_item_started)
            self.install_manager.item_finished.connect(self._on_item_finished)
            self.install_manager.queue_finished.connect(self._on_queue_finished)
            self.install_manager.start(selected)
        else:
            # Solo se había marcado Copa ID (Asset Tag): no hay cola de
            # instalación normal -- se cierra la corrida igual que si fuera
            # cualquier otra (mismo criterio que `LtpCssWindow._on_installar`).
            self._on_queue_finished()

    def _run_copa_id_asset_tag(self, copa_id_entry: tuple[AppItem, QCheckBox], asset_tag: str) -> None:
        """Graba `asset_tag` en el BIOS vía `cctk.exe --asset=<valor>` (ver
        `app.copa_id_setup.apply_copa_id_asset_tag`). No pasa por
        `InstallManager`/`InstallWorker`: se aplica aparte, sincrónico en el
        hilo de la UI, con exactamente el mismo tratamiento visual que
        cualquier ítem de la cola normal (casilla en rojo + tooltip si
        falla, oculta + desmarcada si tiene éxito) para que el técnico no
        note ninguna diferencia salvo que no muestra la barra de progreso
        "instalando" (no es un proceso largo)."""
        item, checkbox = copa_id_entry
        checkbox.setProperty("installing", "true")
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        self.status_label.setText("Copa ID (Asset Tag): grabando en BIOS vía cctk.exe...")

        self.logger.write(f"{item.label}: iniciando -> cctk.exe --asset={asset_tag}")
        try:
            detail = apply_copa_id_asset_tag(asset_tag, self.settings.installers_base_path)
        except CopaIdSetupError as exc:
            self.logger.write(f"{item.label}: ERROR - {exc}")
            self._results["error"] += 1
            self._install_records.append((item.label, item.version, datetime.now(), False))
            checkbox.setProperty("installing", "false")
            checkbox.setProperty("failed", "true")
            checkbox.setChecked(False)
            checkbox.setToolTip(f"Error: {exc}")
            checkbox.style().unpolish(checkbox)
            checkbox.style().polish(checkbox)
            self.status_label.setText(f"Copa ID (Asset Tag): error - {exc}")
            return

        self.logger.write(f"{item.label}: OK ({detail})")
        self._results["ok"] += 1
        # Se registra el Asset Tag grabado como "versión" en el reporte
        # final -- es el dato relevante de este ítem, no un número de
        # versión de software (mismo campo, reutilizado con otro sentido,
        # igual que hace el resto del catálogo con su `item.version`).
        self._install_records.append((item.label, asset_tag, datetime.now(), True))
        checkbox.setProperty("installing", "false")
        # Desmarcar además de ocultar -- mismo motivo que en
        # `_on_item_finished`: si no, la casilla queda marcada por debajo y
        # una corrida posterior la vuelve a aplicar sola.
        checkbox.setChecked(False)
        checkbox.setVisible(False)
        checkbox.style().unpolish(checkbox)
        checkbox.style().polish(checkbox)
        self.status_label.setText(f"Copa ID (Asset Tag): {detail}")

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
        # Se registra en `_install_records` tanto si tuvo éxito como si
        # falló -- las que fallan aparecen igual en el reporte final (ver
        # `app/report.py`), con "FALLO" en la columna de versión en vez de
        # la versión real, resaltadas en rojo y negrita. Caso especial
        # dentro de las que fallan: si el mensaje indica que el ítem
        # necesita que el técnico reinicie el equipo (ej. SAP GUI 144/145,
        # o NetFX35/BFirst cuando se detecta un reinicio pendiente ANTES
        # de correr DISM -- ver `is_reboot_pending_message` en
        # `app/report.py`), se registra con `REBOOT_PENDING_VERSION_LABEL`
        # en vez de `item.version`, para que el reporte muestre "FALLO
        # (Reinicio Pendiente)" en vez del "FALLO" genérico -- la casilla
        # en sí ya se marca en rojo igual que cualquier otro fallo, sin
        # necesitar nada especial acá (ver más abajo).
        version_for_report = item.version
        if not success and is_reboot_pending_message(message):
            version_for_report = REBOOT_PENDING_VERSION_LABEL
        self._install_records.append((item.label, version_for_report, datetime.now(), success))
        if success:
            self._results["ok"] += 1
            # Al llegar al 100%, el ítem desaparece de la lista (igual que la app original).
            # Además de ocultarla hay que DESMARCARLA (`setChecked(False)`):
            # ocultar una casilla no la desmarca sola, así que si se queda
            # marcada por debajo -- aunque invisible -- la próxima vez que
            # se presione INSTALAR (para instalar otras apps nuevas) esta
            # sigue contando como "seleccionada" en `_on_installar` y se
            # vuelve a instalar de nuevo, encima ANTES que las apps nuevas
            # (por el orden del catálogo). Bug real reportado en pruebas de
            # campo: las apps ya instaladas se reinstalaban solas al
            # instalar otras de una columna distinta.
            checkbox.setChecked(False)
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
        if hasattr(self, "asset_tag_edit"):
            copa_id_entry = self.checkboxes.get(COPA_ID_ITEM_ID)
            copa_id_enabled = copa_id_entry[0].enabled if copa_id_entry is not None else True
            self.asset_tag_edit.setEnabled(enabled and copa_id_enabled)
        if hasattr(self, "owner_user_edit"):
            registro_ad_entry = self.checkboxes.get(REGISTRO_AD_ITEM_ID)
            registro_ad_enabled = registro_ad_entry[0].enabled if registro_ad_entry is not None else True
            self.owner_user_edit.setEnabled(enabled and registro_ad_enabled)
        if enabled:
            reapply_exclusive_constraints(self.checkboxes)
