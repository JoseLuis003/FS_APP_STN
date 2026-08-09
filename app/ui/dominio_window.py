"""Pantalla DOMINIO: une el equipo al dominio `copaair.com`.

Emula el script `DomainJoined.ps1` que ya usaba el equipo de soporte, pero
de forma más robusta -- en particular, agrega la validación de credenciales
que el script original no tenía (ver `app/domain_join.py` para el detalle
completo de qué se corrigió):

- Si el usuario/contraseña son incorrectos, se le avisa al técnico con un
  mensaje claro y se le pide que los vuelva a ingresar (solo se limpia la
  contraseña; usuario, equipo y OU quedan como estaban).
- Cualquier otro error (OU inválida, sin red, nombre de equipo duplicado,
  etc.) se muestra con su detalle, sin reintentar solo ni continuar con los
  pasos siguientes.
- Una vez unido el equipo (y aplicados los grupos locales / autologon), se
  le PREGUNTA al técnico antes de reiniciar -- no se reinicia solo.

El técnico solo escribe su usuario (ej. "jperez"); el prefijo de dominio
"copaair\\" se muestra fijo en la UI y Python lo antepone (ver
`app/domain_join.full_username`).

Seguridad: la contraseña nunca se guarda en disco ni se pasa por línea de
comandos -- vive únicamente en memoria mientras corre esta pantalla y se le
pasa a PowerShell por stdin (ver `app/domain_join.py`).
"""
from __future__ import annotations

import socket
import subprocess
from typing import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import ASSETS_DIR
from app.domain_join import (
    OU_OPTIONS,
    USERNAME_DOMAIN_PREFIX,
    BadCredentialsError,
    DomainJoinError,
    apply_post_join_setup,
    join_domain,
)
from app.ui.styles import build_stylesheet

_DEFAULT_WIDTH = 480
_DEFAULT_HEIGHT = 440
_SCREEN_MARGIN = 40


def _initial_window_size() -> tuple[int, int]:
    width, height = _DEFAULT_WIDTH, _DEFAULT_HEIGHT
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        width = min(width, max(available.width() - _SCREEN_MARGIN, 300))
        height = min(height, max(available.height() - _SCREEN_MARGIN, 300))
    return width, height


class DomainJoinWorker(QThread):
    """Corre `join_domain()` y, si tiene éxito, `apply_post_join_setup()` en
    un hilo aparte para no congelar la interfaz. Una señal distinta por cada
    tipo de resultado, para que la UI reaccione distinto en cada caso (ver
    `DominioWindow`)."""

    credentials_rejected = Signal(str)
    failed = Signal(str)
    post_setup_warning = Signal(str)
    succeeded = Signal()

    def __init__(
        self,
        current_name: str,
        new_name: str,
        ou_dn: str,
        username: str,
        password: str,
        parent=None,
    ):
        super().__init__(parent)
        self.current_name = current_name
        self.new_name = new_name
        self.ou_dn = ou_dn
        self.username = username
        self.password = password

    def run(self) -> None:
        try:
            join_domain(self.current_name, self.new_name, self.ou_dn, self.username, self.password)
        except BadCredentialsError as exc:
            self.credentials_rejected.emit(str(exc))
            return
        except DomainJoinError as exc:
            self.failed.emit(str(exc))
            return
        finally:
            # La contraseña ya no hace falta en memoria una vez que
            # terminó (con éxito o no) el intento de unión.
            self.password = ""

        try:
            apply_post_join_setup()
        except DomainJoinError as exc:
            self.post_setup_warning.emit(str(exc))
            return

        self.succeeded.emit()


class DominioWindow(QMainWindow):
    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.setWindowTitle("FS APP PORTABLE - DOMINIO")
        self.setStyleSheet(build_stylesheet(ASSETS_DIR))
        self.resize(*_initial_window_size())

        # Si se abrió desde la portada, este callback regresa a esa
        # pantalla; si no se indica, ATRAS simplemente cierra esta ventana.
        self._on_back = on_back

        self._current_name = socket.gethostname()
        self._worker: DomainJoinWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        intro = QLabel(
            "Une este equipo al dominio de Copa Airlines (copaair.com). "
            "Ingresa tus credenciales de dominio para autorizar la operación."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)

        self.computer_name_edit = QLineEdit(self._current_name)
        self.computer_name_edit.setToolTip(
            "Nombre con el que quedará el equipo en el dominio. Déjalo igual "
            "para no renombrar el equipo."
        )
        form.addRow("Nombre del equipo:", self.computer_name_edit)

        self.ou_combo = QComboBox()
        for label, dn in OU_OPTIONS:
            self.ou_combo.addItem(label, dn)
        form.addRow("Unidad organizativa (OU):", self.ou_combo)

        username_row = QHBoxLayout()
        prefix_label = QLabel(USERNAME_DOMAIN_PREFIX)
        prefix_label.setStyleSheet("color: #555555; font-weight: 600;")
        username_row.addWidget(prefix_label)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("usuario de dominio")
        username_row.addWidget(self.username_edit, 1)
        form.addRow("Usuario:", username_row)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("contraseña de dominio")
        self.password_edit.returnPressed.connect(self._on_unir)
        form.addRow("Contraseña:", self.password_edit)

        root.addLayout(form)

        self.status_label = QLabel("Listo.")
        self.status_label.setObjectName("statusBar")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("installProgressBar")
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        root.addStretch(1)
        root.addLayout(self._build_controls())

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()

        atras_btn = QPushButton("ATRAS")
        atras_btn.clicked.connect(self._on_atras)
        row.addWidget(atras_btn)
        row.addStretch(1)

        self.unir_btn = QPushButton("UNIR AL DOMINIO")
        self.unir_btn.setObjectName("installarButton")
        self.unir_btn.setMinimumSize(180, 60)
        self.unir_btn.clicked.connect(self._on_unir)
        row.addWidget(self.unir_btn)

        return row

    # ------------------------------------------------------------- acciones
    def _on_atras(self) -> None:
        """Regresa a la portada (FS APP PORTABLE) si esta ventana se abrió
        desde ahí; si no, simplemente cierra esta ventana."""
        if self._on_back is not None:
            self._on_back()
        else:
            self.close()

    def _on_unir(self) -> None:
        computer_name = self.computer_name_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        if not computer_name:
            QMessageBox.warning(self, "Unir al dominio", "El nombre del equipo no puede estar vacío.")
            return
        if not username:
            QMessageBox.warning(self, "Unir al dominio", "Ingresa tu usuario de dominio.")
            self.username_edit.setFocus()
            return
        if not password:
            QMessageBox.warning(self, "Unir al dominio", "Ingresa tu contraseña de dominio.")
            self.password_edit.setFocus()
            return

        ou_dn = self.ou_combo.currentData()

        self._set_controls_enabled(False)
        self.status_label.setText("Uniendo el equipo al dominio, esto puede tardar un momento...")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        self._worker = DomainJoinWorker(self._current_name, computer_name, ou_dn, username, password, self)
        self._worker.credentials_rejected.connect(self._on_credentials_rejected)
        self._worker.failed.connect(self._on_failed)
        self._worker.post_setup_warning.connect(self._on_post_setup_warning)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.start()

    # --------------------------------------------------------- señales hilo
    def _on_credentials_rejected(self, message: str) -> None:
        self._finish_attempt()
        self.status_label.setText("Usuario o contraseña incorrectos.")
        QMessageBox.warning(
            self,
            "Credenciales incorrectas",
            f"{message}\n\nPor favor vuelve a ingresar tu usuario y contraseña.",
        )
        # Solo se limpia la contraseña -- equipo, OU y usuario quedan igual,
        # así el técnico no tiene que volver a escribirlos.
        self.password_edit.clear()
        self.password_edit.setFocus()

    def _on_failed(self, message: str) -> None:
        self._finish_attempt()
        self.status_label.setText(f"No se pudo unir al dominio: {message}")
        QMessageBox.critical(self, "No se pudo unir al dominio", message)

    def _on_post_setup_warning(self, message: str) -> None:
        self._finish_attempt()
        self.status_label.setText("Equipo unido al dominio (con advertencias en la configuración posterior).")
        QMessageBox.warning(
            self,
            "Unido al dominio, con advertencias",
            "El equipo se unió correctamente al dominio, pero hubo un problema en la "
            f"configuración posterior (grupos locales / autologon):\n\n{message}\n\n"
            "Puedes revisar esto manualmente más tarde.",
        )
        self._offer_restart()

    def _on_succeeded(self) -> None:
        self._finish_attempt()
        self.status_label.setText("Equipo unido correctamente al dominio.")
        self._offer_restart()

    def _finish_attempt(self) -> None:
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 1)
        self._set_controls_enabled(True)

    def _offer_restart(self) -> None:
        respuesta = QMessageBox.question(
            self,
            "Reiniciar equipo",
            "Se recomienda reiniciar el equipo ahora para completar la unión al dominio.\n\n"
            "¿Reiniciar ahora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if respuesta == QMessageBox.Yes:
            self._restart_computer()

    def _restart_computer(self) -> None:
        try:
            subprocess.Popen(["shutdown", "/r", "/t", "10"])
        except OSError as exc:
            QMessageBox.warning(
                self,
                "No se pudo reiniciar",
                f"No se pudo iniciar el reinicio automáticamente ({exc}).\n\n"
                "Reinicia el equipo manualmente para completar el proceso.",
            )

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.unir_btn.setEnabled(enabled)
        self.computer_name_edit.setEnabled(enabled)
        self.ou_combo.setEnabled(enabled)
        self.username_edit.setEnabled(enabled)
        self.password_edit.setEnabled(enabled)
