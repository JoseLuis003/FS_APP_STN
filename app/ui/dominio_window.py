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
- Pedido explícito: si el técnico acepta reiniciar, ANTES de reiniciar de
  verdad se corren NetFX35 (`netfx35_setup`) y el prerequisito de DELL
  Command Update (`dotnet_desktop_runtime_setup`) -- ver
  `PostJoinExtraInstallsWorker` más abajo. La idea es aprovechar que el
  equipo YA se va a reiniciar para terminar la unión al dominio: esos 2
  componentes suelen necesitar un reinicio para activarse del todo (ver
  `_is_reboot_pending()` en app/netfx35_setup.py), así que instalarlos
  justo antes evita un SEGUNDO reinicio aparte más tarde, cuando el
  técnico los marque desde APPS. Si el técnico responde que NO quiere
  reiniciar ahora, no se instala nada acá -- quedan pendientes para
  hacerse normal desde APPS, junto con el reinicio que decida hacer el
  técnico por su cuenta.

El técnico solo escribe su usuario (ej. "jperez"); el sufijo de dominio
"@copaair.com" (formato UPN, ver `app/domain_join.py` para el motivo del
cambio de formato) se muestra fijo en la UI y Python lo agrega (ver
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

from app.config import load_settings
from app.domain_join import (
    OU_OPTIONS,
    USERNAME_DOMAIN_SUFFIX,
    BadCredentialsError,
    ComputerNameExistsError,
    DomainJoinError,
    apply_computer_description,
    apply_post_join_setup,
    fetch_ou_list_from_ad,
    join_domain,
)
from app.dotnet_desktop_runtime_setup import ensure_dotnet_desktop_runtime_installed
from app.installer import InstallLogger
from app.netfx35_setup import ensure_netfx35_installed

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
    """Corre `join_domain()` y, si tiene éxito, `apply_computer_description()`
    y `apply_post_join_setup()` en un hilo aparte para no congelar la
    interfaz. Una señal distinta por cada tipo de resultado, para que la UI
    reaccione distinto en cada caso (ver `DominioWindow`)."""

    credentials_rejected = Signal(str)
    name_conflict = Signal(str)
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
        description_warning: str | None = None
        try:
            try:
                target_name = join_domain(
                    self.current_name, self.new_name, self.ou_dn, self.username, self.password
                )
            except BadCredentialsError as exc:
                self.credentials_rejected.emit(str(exc))
                return
            except ComputerNameExistsError as exc:
                # Se distingue de un DomainJoinError genérico (ver
                # `_on_name_conflict`): acá el equipo NUNCA llegó a intentar
                # Add-Computer (el nombre se valida ANTES, ver
                # `check_computer_name_available` en app/domain_join.py), así
                # que el técnico necesita un mensaje distinto -- no es "algo
                # falló al unirse", es "ese nombre ya existe en AD, decide qué
                # hacer antes de reintentar".
                self.name_conflict.emit(str(exc))
                return
            except DomainJoinError as exc:
                self.failed.emit(str(exc))
                return

            # Pedido explícito: dejar el número de serie del equipo en el
            # campo Description de Active Directory. Se corre ACÁ (todavía
            # con `target_name` recién unido y las credenciales en
            # memoria), no en `apply_post_join_setup()`, porque a
            # diferencia de ese paso, este SÍ necesita las credenciales de
            # dominio (hace su propio bind LDAP). Un fallo acá no es
            # bloqueante: el equipo ya quedó unido al dominio de todos
            # modos, así que solo se junta como advertencia (ver más abajo).
            try:
                apply_computer_description(target_name, self.ou_dn, self.username, self.password)
            except DomainJoinError as exc:
                description_warning = str(exc)
        finally:
            # La contraseña ya no hace falta en memoria una vez que
            # terminaron (con éxito o no) los 2 pasos que la necesitan:
            # unirse al dominio y escribir la Description.
            # `apply_post_join_setup()`, más abajo, no requiere
            # credenciales de dominio.
            self.password = ""

        try:
            apply_post_join_setup()
        except DomainJoinError as exc:
            warnings = [w for w in (description_warning, str(exc)) if w]
            self.post_setup_warning.emit("\n\n".join(warnings))
            return

        if description_warning:
            self.post_setup_warning.emit(description_warning)
            return

        self.succeeded.emit()


class FetchOuListWorker(QThread):
    """Corre `fetch_ou_list_from_ad()` en un hilo aparte (una consulta LDAP
    puede tardar unos segundos) para no congelar la interfaz -- mismo
    patrón de señales que `DomainJoinWorker`, para reutilizar el mismo
    manejo de "credenciales incorrectas" vs. "cualquier otro error"."""

    credentials_rejected = Signal(str)
    failed = Signal(str)
    succeeded = Signal(list)

    def __init__(self, username: str, password: str, parent=None):
        super().__init__(parent)
        self.username = username
        self.password = password

    def run(self) -> None:
        try:
            ou_options = fetch_ou_list_from_ad(self.username, self.password)
        except BadCredentialsError as exc:
            self.credentials_rejected.emit(str(exc))
            return
        except DomainJoinError as exc:
            self.failed.emit(str(exc))
            return
        finally:
            self.password = ""

        self.succeeded.emit(ou_options)


class PostJoinExtraInstallsWorker(QThread):
    """Corre, en un hilo aparte (para no congelar la interfaz), NetFX35
    (`ensure_netfx35_installed`) y el prerequisito de DELL Command Update
    (`ensure_dotnet_desktop_runtime_installed`) -- pedido explícito: se
    llama SOLO cuando el técnico acepta reiniciar después de unirse al
    dominio, para aprovechar ese reinicio (que igual hace falta para
    completar la unión) y dejar estos 2 componentes también resueltos,
    en vez de necesitar un reinicio aparte más tarde desde APPS.

    Corre los 2 SIEMPRE, aunque el primero falle (son independientes
    entre sí -- ver `finished_all`, que junta el resultado de ambos) --
    y el resultado de este worker NUNCA impide el reinicio: si alguno
    falla, `DominioWindow` igual reinicia el equipo (que de todos modos
    hace falta para la unión al dominio) y solo le avisa al técnico que
    puede volver a intentarlo desde APPS."""

    finished_all = Signal(list)  # [(label, success, detalle_o_error), ...]

    def __init__(self, installers_base_path: str, logger: InstallLogger, parent=None):
        super().__init__(parent)
        self.installers_base_path = installers_base_path
        self.logger = logger

    def run(self) -> None:
        # Se arma la lista de pasos ACÁ ADENTRO (no como atributo de clase)
        # a propósito: así toma el valor ACTUAL de
        # `ensure_netfx35_installed`/`ensure_dotnet_desktop_runtime_installed`
        # en el momento de correr, en vez de "congelar" una referencia fija
        # al importarse el módulo -- mismo criterio que
        # `_python_step_handlers()` en app/installer.py, y necesario para
        # que las pruebas puedan mockear estas 2 funciones.
        steps = (
            ("NetFX35", ensure_netfx35_installed),
            (".NET Desktop Runtime (prerequisito de DELL Command Update)", ensure_dotnet_desktop_runtime_installed),
        )
        results: list[tuple[str, bool, str]] = []
        for label, handler in steps:
            self.logger.write(f"{label}: iniciando (post unión al dominio, antes de reiniciar)")
            try:
                detail = handler(self.installers_base_path)
            except Exception as exc:  # mismo criterio que _python_step_handlers en app/installer.py
                self.logger.write(f"{label}: ERROR - {exc}")
                results.append((label, False, str(exc)))
                continue
            self.logger.write(f"{label}: OK ({detail})")
            results.append((label, True, detail))
        self.finished_all.emit(results)


class DominioWindow(QMainWindow):
    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.setWindowTitle("FS APP PORTABLE - DOMINIO")
        # La hoja de estilos se aplica a nivel de QApplication en
        # `main.py` -- así también la heredan los QMessageBox de esta
        # ventana (diálogos de nivel superior aparte, que no heredan un
        # `.setStyleSheet()` puesto solo sobre esta ventana).
        self.resize(*_initial_window_size())

        # Si se abrió desde la portada, este callback regresa a esa
        # pantalla; si no se indica, ATRAS simplemente cierra esta ventana.
        self._on_back = on_back

        self._current_name = socket.gethostname()
        self._worker: DomainJoinWorker | None = None
        self._ou_worker: FetchOuListWorker | None = None
        self._extra_installs_worker: PostJoinExtraInstallsWorker | None = None
        # Solo para leer `installers_base_path` (ver
        # `_run_post_join_extra_installs`) -- esta pantalla no tiene un
        # botón de Ajustes propio, así que se lee tal cual está guardado.
        self.settings = load_settings()

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

        ou_row = QHBoxLayout()
        ou_row.addWidget(self.ou_combo, 1)
        self.cargar_ous_btn = QPushButton("Cargar OUs desde AD")
        self.cargar_ous_btn.setToolTip(
            "Consulta Active Directory en vivo (con el usuario y contraseña\n"
            "de abajo) y reemplaza esta lista fija de 5 por las OUs reales\n"
            "encontradas bajo Workstations_Copa."
        )
        self.cargar_ous_btn.clicked.connect(self._on_cargar_ous)
        ou_row.addWidget(self.cargar_ous_btn)
        form.addRow("Unidad organizativa (OU):", ou_row)

        username_row = QHBoxLayout()
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("jlbarrios")
        username_row.addWidget(self.username_edit, 1)
        suffix_label = QLabel(USERNAME_DOMAIN_SUFFIX)
        suffix_label.setStyleSheet("color: #555555; font-weight: 600;")
        username_row.addWidget(suffix_label)
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
        self._worker.name_conflict.connect(self._on_name_conflict)
        self._worker.failed.connect(self._on_failed)
        self._worker.post_setup_warning.connect(self._on_post_setup_warning)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.start()

    def _on_cargar_ous(self) -> None:
        """Consulta Active Directory en vivo (con el usuario/contraseña ya
        escritos) y reemplaza `self.ou_combo` con las OUs reales
        encontradas -- ver `fetch_ou_list_from_ad` en `app/domain_join.py`."""
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        if not username:
            QMessageBox.warning(self, "Cargar OUs desde AD", "Ingresa tu usuario de dominio primero.")
            self.username_edit.setFocus()
            return
        if not password:
            QMessageBox.warning(self, "Cargar OUs desde AD", "Ingresa tu contraseña de dominio primero.")
            self.password_edit.setFocus()
            return

        self._set_controls_enabled(False)
        self.status_label.setText("Consultando Active Directory...")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        self._ou_worker = FetchOuListWorker(username, password, self)
        self._ou_worker.credentials_rejected.connect(self._on_ou_credentials_rejected)
        self._ou_worker.failed.connect(self._on_ou_failed)
        self._ou_worker.succeeded.connect(self._on_ou_succeeded)
        self._ou_worker.start()

    # --------------------------------------------------------- señales hilo
    def _on_ou_credentials_rejected(self, message: str) -> None:
        self._finish_attempt()
        self.status_label.setText("Usuario o contraseña incorrectos.")
        QMessageBox.warning(
            self,
            "Credenciales incorrectas",
            f"{message}\n\nPor favor vuelve a ingresar tu usuario y contraseña.",
        )
        self.password_edit.clear()
        self.password_edit.setFocus()

    def _on_ou_failed(self, message: str) -> None:
        self._finish_attempt()
        self.status_label.setText(f"No se pudo cargar la lista de OUs: {message}")
        QMessageBox.critical(self, "No se pudo cargar la lista de OUs", message)

    def _on_ou_succeeded(self, ou_options: list) -> None:
        self._finish_attempt()
        # Si la OU seleccionada antes de recargar sigue estando en la lista
        # nueva, se mantiene marcada -- si no, queda la primera de la lista
        # nueva (comportamiento normal de QComboBox al hacer `clear()`).
        previous_dn = self.ou_combo.currentData()
        self.ou_combo.clear()
        for label, dn in ou_options:
            self.ou_combo.addItem(label, dn)
        restored_index = self.ou_combo.findData(previous_dn)
        if restored_index >= 0:
            self.ou_combo.setCurrentIndex(restored_index)
        self.status_label.setText(f"Se cargaron {len(ou_options)} OU(s) desde Active Directory.")

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

    def _on_name_conflict(self, message: str) -> None:
        """El nombre elegido ya existe en Active Directory -- ver
        `ComputerNameExistsError`. A diferencia de `_on_failed`, acá el
        equipo NUNCA llegó a intentar unirse al dominio (la validación
        ocurre ANTES de `Add-Computer`), así que no hace falta ofrecer
        reiniciar ni nada por el estilo -- el técnico solo necesita
        decidir qué hacer con el nombre (ver las 3 opciones en el
        mensaje) y volver a intentarlo."""
        self._finish_attempt()
        self.status_label.setText("Ese nombre de equipo ya existe en Active Directory.")
        QMessageBox.critical(self, "Nombre de equipo ya existe en Active Directory", message)
        self.computer_name_edit.setFocus()
        self.computer_name_edit.selectAll()

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
            # Antes de reiniciar de verdad, se aprovecha para dejar
            # instalados NetFX35 y el prerequisito de DELL Command Update
            # (ver `PostJoinExtraInstallsWorker`) -- si el técnico hubiera
            # dicho que NO, no se instala nada acá, queda pendiente para
            # hacerse normal desde APPS.
            self._run_post_join_extra_installs()

    def _run_post_join_extra_installs(self) -> None:
        self._set_controls_enabled(False)
        self.status_label.setText(
            "Aprovechando el reinicio: instalando NetFX35 y el .NET Desktop Runtime "
            "(prerequisito de DELL Command Update)..."
        )
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        logger = InstallLogger()
        self._extra_installs_worker = PostJoinExtraInstallsWorker(self.settings.installers_base_path, logger, self)
        self._extra_installs_worker.finished_all.connect(self._on_post_join_extra_installs_finished)
        self._extra_installs_worker.start()

    def _on_post_join_extra_installs_finished(self, results: list) -> None:
        """`results` es `[(label, success, detalle_o_error), ...]` (ver
        `PostJoinExtraInstallsWorker.finished_all`). Sin importar el
        resultado, el equipo se reinicia igual -- ya hace falta para
        completar la unión al dominio; si algo falló acá, solo se le
        avisa al técnico para que lo reintente después desde APPS."""
        self._finish_attempt()
        failed = [(label, detail) for label, success, detail in results if not success]
        if failed:
            detail_lines = "\n".join(f"- {label}: {detail}" for label, detail in failed)
            QMessageBox.warning(
                self,
                "NetFX35 / .NET Desktop Runtime: con advertencias",
                "El equipo se va a reiniciar igual para completar la unión al dominio, pero "
                "no se pudo dejar todo listo antes del reinicio:\n\n"
                f"{detail_lines}\n\n"
                "Puedes volver a intentarlo manualmente desde APPS después de reiniciar.",
            )
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
        self.cargar_ous_btn.setEnabled(enabled)
        self.computer_name_edit.setEnabled(enabled)
        self.ou_combo.setEnabled(enabled)
        self.username_edit.setEnabled(enabled)
        self.password_edit.setEnabled(enabled)
