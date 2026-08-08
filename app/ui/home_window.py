"""Pantalla de bienvenida ("portada") de FS APP PORTABLE.

Muestra 3 botones de navegación (APPS, LTP / CSS, DOMINIO) en una barra
superior, y debajo la imagen de campaña completa (sin recortarla). Por
ahora solo APPS abre una pantalla real (el catálogo de instalación que ya
existía, ver `app/ui/main_window.py`); los otros dos todavía no tienen una
sección definida, así que muestran un aviso de "próximamente" al
presionarlos.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import ASSETS_DIR
from app.ui.main_window import MainWindow

_BAR_COLOR = "#0a1f3d"  # mismo tono oscuro/azul de la imagen de campaña

_HOME_STYLESHEET = f"""
QWidget#homeTopBar {{
    background-color: {_BAR_COLOR};
}}
QPushButton#homeMenuButton {{
    background-color: #f4f3f1;
    border: 1px solid #9a9a9a;
    border-radius: 4px;
    padding: 12px 20px;
    font-size: 14px;
    font-weight: 700;
    color: #000000;
}}
QPushButton#homeMenuButton:hover {{
    background-color: #e2e2e2;
}}
QPushButton#homeMenuButton:pressed {{
    background-color: #cfcfcf;
}}
"""


class _BackgroundWidget(QWidget):
    """Widget que dibuja una imagen completa, sin recortarla (letterbox con
    un color sólido a los lados si la proporción de la ventana no coincide
    exactamente con la de la imagen)."""

    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap(str(image_path)) if image_path.exists() else QPixmap()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(_BAR_COLOR))
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        super().paintEvent(event)


class HomeWindow(QMainWindow):
    """Pantalla principal / portada de FS APP PORTABLE."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FS APP PORTABLE")
        # Tamaño fijo (no `resize`, que solo sugiere un tamaño inicial pero
        # deja la ventana libre de estirarse): así se garantiza que la
        # portada siempre abra compacta, sin importar la resolución de la
        # pantalla. Si se necesita otro tamaño, basta con cambiar estos dos
        # números (ancho, alto en píxeles).
        self.setFixedSize(740, 580)
        self.setStyleSheet(_HOME_STYLESHEET)

        # Se crea la primera vez que se presiona APPS, y se reutiliza si se
        # vuelve a presionar (no hace falta reconstruir el catálogo).
        self.main_window: MainWindow | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Barra superior con los 3 botones de navegación, siempre visible y
        # nunca tapando el contenido de la imagen de abajo.
        top_bar = QWidget()
        top_bar.setObjectName("homeTopBar")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(20, 16, 20, 16)
        top_bar_layout.setSpacing(14)

        apps_btn = QPushButton("APPS")
        ltp_btn = QPushButton("LTP / CSS")
        dominio_btn = QPushButton("DOMINIO")
        for btn in (apps_btn, ltp_btn, dominio_btn):
            btn.setObjectName("homeMenuButton")
            btn.setMinimumSize(120, 52)
            top_bar_layout.addWidget(btn)
        top_bar_layout.addStretch(1)

        apps_btn.clicked.connect(self._on_apps)
        ltp_btn.clicked.connect(lambda: self._show_placeholder("LTP / CSS"))
        dominio_btn.clicked.connect(lambda: self._show_placeholder("DOMINIO"))

        root.addWidget(top_bar)

        # Debajo, la imagen de campaña completa (sin recortar).
        background = _BackgroundWidget(ASSETS_DIR / "home_background.png")
        root.addWidget(background, stretch=1)

    def _on_apps(self) -> None:
        if self.main_window is None:
            self.main_window = MainWindow()
        self.main_window.show()
        self.hide()

    def _show_placeholder(self, section_name: str) -> None:
        QMessageBox.information(
            self,
            section_name,
            f'La sección "{section_name}" todavía no está disponible. Próximamente.',
        )
