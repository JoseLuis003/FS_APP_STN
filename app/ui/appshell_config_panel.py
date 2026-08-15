"""Panel de configuración de "AppShell Configuracion", parte del catálogo
de LTP / CSS: se muestra u oculta según el checkbox del mismo nombre (ver
`LtpCssWindow._build_ui`, mismo mecanismo que ya usa `SharesConfigPanel`
para "Shares Configuracion").

Despliega el submenú DEVICE's con 5 casillas (ATB, BTP, DCP, BGR, OCR).
Las 5 tienen lógica propia (ver `app/appshell_config_apply.py`): al
presionar INSTALAR, ATB/BTP/DCP marcados agregan su puerto COM y su
identificador al INI de configuración de AppShell, y BGR/OCR marcados
crean o actualizan el archivo Mastcom.xml con su sesión correspondiente."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QWidget

# Nombres de las 5 opciones, en el mismo orden y disposición que la imagen
# de referencia: 3 filas con 2 columnas (equipo individual a la izquierda,
# BGR/OCR a la derecha). La fila de DCP no tiene pareja a la derecha (ya
# no existe "BGR-OCR" -- se eliminó, no hacía falta).
_DEVICE_PAIRS = [
    ("ATB", "BGR"),
    ("BTP", "OCR"),
    ("DCP", None),
]

# Nombres de las casillas con lógica de aplicación propia (ver
# app/appshell_config_apply.py). Actualmente las 5 la tienen.
DEVICE_NAMES_WITH_LOGIC = ["ATB", "BTP", "DCP", "BGR", "OCR"]


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

        # item_id (ej. "ATB", "BGR") -> QCheckBox
        self.device_checks: dict[str, QCheckBox] = {}

        grid_row = 0
        for left_name, right_name in _DEVICE_PAIRS:
            left_check = QCheckBox(left_name)
            devices_layout.addWidget(left_check, grid_row, 0)
            self.device_checks[left_name] = left_check
            if right_name is not None:
                right_check = QCheckBox(right_name)
                devices_layout.addWidget(right_check, grid_row, 1)
                self.device_checks[right_name] = right_check
            grid_row += 1

        row.addWidget(devices_box)
        row.addStretch(1)

    def reset_device_checks(self, names: list[str]) -> None:
        """Desmarca las casillas indicadas (por nombre, ej. "ATB"). Se usa
        después de aplicar exitosamente la configuración de AppShell, para
        evitar que una casilla marcada siga presente en un INSTALAR
        posterior y duplique valores ya agregados (ver
        `apply_appshell_device_config` / `apply_appshell_mastcom_config`,
        que agregan sin reemplazar lo existente -- una casilla no reseteada
        aplicaría el mismo cambio dos veces)."""
        for name in names:
            checkbox = self.device_checks.get(name)
            if checkbox is not None:
                checkbox.setChecked(False)
