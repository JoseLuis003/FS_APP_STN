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
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import ASSETS_DIR
from app.ui.main_window import MainWindow

_BAR_COLOR = "#0a1f3d"  # mismo tono oscuro/azul de la imagen de campaña

# MODO AJUSTE DE TAMAÑO: mientras esto sea True, la ventana queda libre de
# redimensionar (en vez de tamaño fijo) y aparece una etiqueta con el ancho
# x alto actual en píxeles, para poder arrastrar el borde de la ventana
# hasta el tamaño que se vea bien y anotar el número exacto. Una vez que
# tengas el tamaño que te gusta, dime esos dos números y cambio esto de
# vuelta a `False` (o directamente fijo el tamaño con `setFixedSize`) para
# que la ventana quede compacta y no se pueda seguir estirando.
SIZE_ADJUST_MODE = False

# Tamaño final ya decidido (515 x 580 px, confirmado en Windows).
FIXED_WIDTH = 515
FIXED_HEIGHT = 580

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
QLabel#sizeDebugLabel {{
    color: #ffe28a;
    font-size: 12px;
    font-weight: 700;
    background-color: rgba(0, 0, 0, 120);
    padding: 4px 8px;
    border-radius: 3px;
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
        self.setStyleSheet(_HOME_STYLESHEET)

        self.size_label: QLabel | None = None

        if SIZE_ADJUST_MODE:
            # Ventana redimensionable + etiqueta con el tamaño actual, para
            # poder encontrar a ojo el tamaño ideal arrastrando el borde.
            self.resize(FIXED_WIDTH, FIXED_HEIGHT)
            self.setMinimumSize(300, 300)
        else:
            # Tamaño fijo (no `resize`, que solo sugiere un tamaño inicial
            # pero deja la ventana libre de estirarse): así se garantiza que
            # la portada siempre abra compacta, sin importar la resolución
            # de la pantalla.
            self.setFixedSize(FIXED_WIDTH, FIXED_HEIGHT)

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

        if SIZE_ADJUST_MODE:
            self.size_label = QLabel()
            self.size_label.setObjectName("sizeDebugLabel")
            top_bar_layout.addWidget(self.size_label)
            self._update_size_label()

        root.addWidget(top_bar)

        # Debajo, la imagen de campaña completa (sin recortar).
        background = _BackgroundWidget(ASSETS_DIR / "home_background.png")
        root.addWidget(background, stretch=1)

    def resizeEvent(self, event) -> None:
        self._update_size_label()
        super().resizeEvent(event)

    def _update_size_label(self) -> None:
        """Solo existe en SIZE_ADJUST_MODE: muestra el ancho x alto actual
        de la ventana en píxeles, en vivo, mientras se arrastra el borde
        para encontrar el tamaño ideal."""
        if self.size_label is not None:
            self.size_label.setText(f"{self.width()} x {self.height()} px")

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
