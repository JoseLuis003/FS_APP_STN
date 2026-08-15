"""Panel de configuración de "Shares Configuracion", parte del catálogo de
LTP / CSS: se muestra u oculta según el checkbox del mismo nombre (ver
`LtpCssWindow._build_ui`, donde se conecta el `toggled` de esa casilla a
`setVisible` de este panel).

Trae tres secciones, tal como en la pantalla original:

- SETTING's: HOSTNAME y CIUDAD (casilla + campo editable, precargados con
  el nombre real del equipo — CIUDAD toma las primeras 3 letras de ese
  nombre, y no permite escribir más de 3 caracteres), los 4 campos LNIATA
  (casilla + campo alfanumérico limitado a 6 caracteres, para evitar
  errores de tecleo) y CONTINGENCIA (solo casilla, sin campo).
- DEVICES: BGR, OCR (WGE no se ofrece — no hace falta en esta pantalla).
- CRT's: 2, 4.

Cada campo de texto solo se puede editar mientras su casilla esté marcada
(si se desmarca la casilla, el campo se deshabilita pero conserva el
valor, por si se vuelve a marcar)."""
from __future__ import annotations

import socket

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

# Los campos LNIATA aceptan letras y números (alfanumérico), hasta este
# máximo de caracteres.
LNIATA_MAX_LENGTH = 6

# CIUDAD es un código de 3 caracteres (ej. "PTY", "MDE", "BOG").
CIUDAD_MAX_LENGTH = 3

# Sufijos de los 4 campos LNIATA, en el mismo orden que la imagen de
# referencia (CRT, ATB, BTP, DCP).
_LNIATA_SUFFIXES = ("CRT", "ATB", "BTP", "DCP")


def _get_hostname() -> str:
    """Nombre del equipo tal como lo ve el sistema operativo. Si por algún
    motivo no se puede obtener, se deja vacío en vez de fallar — el técnico
    siempre puede escribirlo a mano."""
    try:
        return socket.gethostname()
    except OSError:
        return ""


def _wire_mutually_exclusive(a: QCheckBox, b: QCheckBox) -> None:
    """Al marcar una de las dos casillas, desmarca la otra (sin
    deshabilitarla) -- versión mínima de `catalog_widgets._wire_exclusive_group`
    para un par suelto de checkboxes que no vienen del catálogo (no tienen
    un `AppItem`/`exclusive_group` detrás)."""

    def make_handler(current: QCheckBox, other: QCheckBox):
        def handler(checked: bool) -> None:
            if checked:
                other.setChecked(False)

        return handler

    a.toggled.connect(make_handler(a, b))
    b.toggled.connect(make_handler(b, a))


class SharesConfigPanel(QWidget):
    """Panel que aparece al marcar "Shares Configuracion" en el catálogo de
    LTP / CSS, con las secciones SETTING's / DEVICES / CRT's."""

    def __init__(self, parent=None):
        super().__init__(parent)

        hostname = _get_hostname()
        # CIUDAD toma por defecto las primeras 3 letras del nombre del
        # equipo (ej. "LTP-JB" -> "LTP"), pero el técnico puede cambiarlo.
        ciudad_default = hostname[:3].upper()

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(16)

        # ------------------------------------------------------- SETTING's
        settings_box = QGroupBox("SETTING's")
        settings_layout = QGridLayout(settings_box)
        settings_layout.setVerticalSpacing(6)
        settings_layout.setHorizontalSpacing(10)

        alphanumeric_validator = QRegularExpressionValidator(
            QRegularExpression(rf"^[A-Za-z0-9]{{0,{LNIATA_MAX_LENGTH}}}$")
        )

        self.hostname_check = QCheckBox("HOSTNAME")
        self.hostname_edit = QLineEdit(hostname)
        self._add_setting_row(settings_layout, 0, self.hostname_check, self.hostname_edit)
        self.hostname_check.setChecked(True)

        self.lniata_checks: dict[str, QCheckBox] = {}
        self.lniata_edits: dict[str, QLineEdit] = {}
        for row_index, suffix in enumerate(_LNIATA_SUFFIXES, start=1):
            check = QCheckBox(f"LNIATA {suffix}")
            edit = QLineEdit()
            edit.setMaxLength(LNIATA_MAX_LENGTH)
            edit.setValidator(alphanumeric_validator)
            edit.setPlaceholderText(f"hasta {LNIATA_MAX_LENGTH} caracteres")
            self._add_setting_row(settings_layout, row_index, check, edit)
            self.lniata_checks[suffix] = check
            self.lniata_edits[suffix] = edit

        ciudad_row = len(_LNIATA_SUFFIXES) + 1
        self.ciudad_check = QCheckBox("CIUDAD")
        self.ciudad_edit = QLineEdit(ciudad_default)
        self.ciudad_edit.setMaxLength(CIUDAD_MAX_LENGTH)
        self._add_setting_row(settings_layout, ciudad_row, self.ciudad_check, self.ciudad_edit)
        self.ciudad_check.setChecked(True)

        self.contingencia_check = QCheckBox("CONTINGENCIA")
        settings_layout.addWidget(self.contingencia_check, ciudad_row + 1, 0, 1, 2)

        row.addWidget(settings_box)

        # -------------------------------------------------------- DEVICES
        devices_box = QGroupBox("DEVICES")
        devices_layout = QVBoxLayout(devices_box)
        self.bgr_check = QCheckBox("BGR")
        self.ocr_check = QCheckBox("OCR")
        for cb in (self.bgr_check, self.ocr_check):
            devices_layout.addWidget(cb)
        devices_layout.addStretch(1)
        row.addWidget(devices_box)

        # --------------------------------------------------------- CRT's
        crts_box = QGroupBox("CRT's")
        crts_layout = QVBoxLayout(crts_box)
        self.crt_2_check = QCheckBox("2")
        self.crt_4_check = QCheckBox("4")
        crts_layout.addWidget(self.crt_2_check)
        crts_layout.addWidget(self.crt_4_check)
        crts_layout.addStretch(1)
        row.addWidget(crts_box)

        row.addStretch(1)

        self._wire_field_enabling()
        # Una estación tiene 2 pantallas CRT o 4, no ambas -- ver
        # `app/shares_config_apply.py` (CRT 4 espera encontrar la línea
        # `CRT=...` en su valor exacto de fábrica; si CRT 2 ya se aplicó
        # antes en la misma corrida, esa línea ya no coincide, así que
        # aplicar las dos juntas fallaría de forma dependiente del orden).
        _wire_mutually_exclusive(self.crt_2_check, self.crt_4_check)

    @staticmethod
    def _add_setting_row(layout: QGridLayout, row_index: int, check: QCheckBox, edit: QLineEdit) -> None:
        layout.addWidget(check, row_index, 0)
        layout.addWidget(edit, row_index, 1)

    def _wire_field_enabling(self) -> None:
        """El campo de texto de cada fila solo se puede editar mientras su
        casilla esté marcada (si se desmarca, el campo se deshabilita pero
        conserva lo escrito, por si se vuelve a marcar)."""
        pairs = [(self.hostname_check, self.hostname_edit), (self.ciudad_check, self.ciudad_edit)]
        pairs += [(self.lniata_checks[s], self.lniata_edits[s]) for s in _LNIATA_SUFFIXES]

        for check, edit in pairs:
            edit.setEnabled(check.isChecked())
            check.toggled.connect(edit.setEnabled)

    def reset_lniata_fields(self) -> None:
        """Limpia los 4 campos LNIATA (casilla desmarcada + texto vacío)
        después de aplicar la configuración con éxito — son valores de un
        solo uso para esa corrida. HOSTNAME y CIUDAD NO se tocan aquí:
        identifican al equipo y deben quedar para la próxima vez."""
        for suffix in _LNIATA_SUFFIXES:
            self.lniata_checks[suffix].setChecked(False)
            self.lniata_edits[suffix].clear()

    def reset_contingencia(self) -> None:
        """Desmarca la casilla CONTINGENCIA después de correr el script con
        éxito — es una acción de un solo uso para esa corrida, igual que los
        campos LNIATA."""
        self.contingencia_check.setChecked(False)

    def reset_devices_and_crts(self) -> None:
        """Desmarca BGR, OCR, CRT 2 y CRT 4 después de aplicarlos con éxito
        — igual que los campos LNIATA y CONTINGENCIA, son acciones de un
        solo uso para esa corrida (volver a marcarlas en una corrida
        posterior sin haber cambiado nada más no debería pasar; si hiciera
        falta, el técnico las vuelve a marcar a mano)."""
        self.bgr_check.setChecked(False)
        self.ocr_check.setChecked(False)
        self.crt_2_check.setChecked(False)
        self.crt_4_check.setChecked(False)
