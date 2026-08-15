"""Panel de configuración de "AppShell Configuracion", parte del catálogo
de LTP / CSS: se muestra u oculta según el checkbox del mismo nombre (ver
`LtpCssWindow._build_ui`, mismo mecanismo que ya usa `SharesConfigPanel`
para "Shares Configuracion").

Por ahora solo despliega el submenú DEVICE's con las 10 opciones de la
imagen de referencia (ATB, BTP, DCP, BGR, OCR, BGR-OCR, ATB-BTP, ATB-DCP,
BTP-DCP, ATB-BTP-DCP) — son casillas simples, sin ninguna lógica todavía;
qué debe hacer cada una se define y se programa más adelante."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QWidget

# Nombres de las 10 opciones, en el mismo orden y disposición que la imagen
# de referencia: las primeras 3 filas tienen 2 columnas (equipo individual
# a la izquierda, BGR/OCR/BGR-OCR a la derecha), y las últimas 4 son
# combinaciones de varios equipos, una por fila, a lo ancho.
_DEVICE_PAIRS = [
    ("ATB", "BGR"),
    ("BTP", "OCR"),
    ("DCP", "BGR-OCR"),
]
_DEVICE_COMBOS = [
    "ATB-BTP",
    "ATB-DCP",
    "BTP-DCP",
    "ATB-BTP-DCP",
]


class AppShellConfigPanel(QWidget):
    """Panel que aparece al marcar "AppShell Configuracion" en el catálogo
    de LTP / CSS, con el submenú DEVICE's."""

    def __init__(self, parent=None):
        super().__init__(parent)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(16)

        devices_box = QGroupBox("DEVICE's")
        devices_layout = QGridLayout(devices_box)
        devices_layout.setVerticalSpacing(6)
        devices_layout.setHorizontalSpacing(24)

        # item_id (ej. "ATB", "BGR-OCR") -> QCheckBox
        self.device_checks: dict[str, QCheckBox] = {}

        grid_row = 0
        for left_name, right_name in _DEVICE_PAIRS:
            left_check = QCheckBox(left_name)
            right_check = QCheckBox(right_name)
            devices_layout.addWidget(left_check, grid_row, 0)
            devices_layout.addWidget(right_check, grid_row, 1)
            self.device_checks[left_name] = left_check
            self.device_checks[right_name] = right_check
            grid_row += 1

        for combo_name in _DEVICE_COMBOS:
            combo_check = QCheckBox(combo_name)
            # Ocupa las 2 columnas de la grilla, igual que en la imagen de
            # referencia (estas 4 opciones van a lo ancho, no en pareja).
            devices_layout.addWidget(combo_check, grid_row, 0, 1, 2)
            self.device_checks[combo_name] = combo_check
            grid_row += 1

        row.addWidget(devices_box)
        row.addStretch(1)
