"""Pantalla de bienvenida ("portada") de FS APP PORTABLE.

Muestra 3 botones de navegación (APPS, LTP / CSS, DOMINIO) en una barra
superior, y debajo la imagen de campaña completa (sin recortarla). APPS
abre el catálogo de instalación original (`app/ui/main_window.py`),
LTP / CSS abre su propio catálogo (`app/ui/ltp_css_window.py`) y DOMINIO
abre la pantalla de unión al dominio `copaair.com`
(`app/ui/dominio_window.py`).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config import ASSETS_DIR
from app.ui.dominio_window import DominioWindow
from app.ui.ltp_css_window import LtpCssWindow
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


def _compute_background_geometry(
    widget_width: int, widget_height: int, dpr: float, pixmap_width: int, pixmap_height: int
) -> tuple[int, int, float, float]:
    """Calcula a qué tamaño (en píxeles FÍSICOS, no lógicos) hay que
    escalar la imagen de fondo para que se vea nítida en pantallas de alta
    densidad (125% / 150% / 200% de escala en Windows -- muy común en
    laptops corporativos), y la posición LÓGICA (x, y) donde dibujarla
    centrada dentro del widget.

    Bug que esto corrige: `QWidget.size()` devuelve el tamaño LÓGICO de la
    ventana (ej. 515x580), no el tamaño físico real de la pantalla. Si se
    le pide a `QPixmap.scaled()` ese tamaño lógico tal cual (como hacía
    antes este widget) en una pantalla con escala > 100%, el resultado
    queda con menos píxeles reales de los que la pantalla puede mostrar, y
    Qt lo estira para llenar el espacio -- ahí aparece el efecto
    "pixelado"/borroso que se reportó, sin importar qué tan nítida sea la
    imagen original. La corrección: multiplicar por `devicePixelRatioF()`
    (la relación entre píxeles físicos y lógicos de la pantalla actual)
    antes de escalar, y llamar a `QPixmap.setDevicePixelRatio()` en el
    resultado para que Qt lo dibuje a su tamaño lógico correcto sin
    volver a estirarlo.

    Devuelve `(0, 0, 0.0, 0.0)` si la imagen no tiene tamaño válido (para
    que quien llame pueda saltarse el dibujo sin dividir por cero)."""
    if pixmap_width <= 0 or pixmap_height <= 0 or dpr <= 0:
        return 0, 0, 0.0, 0.0
    physical_widget_width = widget_width * dpr
    physical_widget_height = widget_height * dpr
    scale = min(physical_widget_width / pixmap_width, physical_widget_height / pixmap_height)
    target_width_px = round(pixmap_width * scale)
    target_height_px = round(pixmap_height * scale)
    x = (widget_width - target_width_px / dpr) / 2
    y = (widget_height - target_height_px / dpr) / 2
    return target_width_px, target_height_px, x, y


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
            dpr = self.devicePixelRatioF() or 1.0
            target_w, target_h, x, y = _compute_background_geometry(
                self.width(), self.height(), dpr, self._pixmap.width(), self._pixmap.height()
            )
            if target_w > 0 and target_h > 0:
                scaled = self._pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                painter.drawPixmap(QPointF(x, y), scaled)
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

        # Se crean la primera vez que se presiona cada botón, y se
        # reutilizan si se vuelve a entrar (no hace falta reconstruir el
        # catálogo cada vez).
        self.main_window: MainWindow | None = None
        self.ltp_css_window: LtpCssWindow | None = None
        self.dominio_window: DominioWindow | None = None

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
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            # stretch=1 en cada botón: se reparten el ancho disponible en
            # partes iguales, sin dejar un hueco vacío después del último.
            top_bar_layout.addWidget(btn, 1)

        apps_btn.clicked.connect(self._on_apps)
        ltp_btn.clicked.connect(self._on_ltp_css)
        dominio_btn.clicked.connect(self._on_dominio)

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
            self.main_window = MainWindow(on_back=self._on_back_to_home)
        self.main_window.show()
        self.hide()

    def _on_back_to_home(self) -> None:
        """Se conecta al botón ATRAS del catálogo de instalación (MainWindow)
        para volver a mostrar esta portada."""
        self.show()
        if self.main_window is not None:
            self.main_window.hide()

    def _on_ltp_css(self) -> None:
        if self.ltp_css_window is None:
            self.ltp_css_window = LtpCssWindow(on_back=self._on_back_from_ltp_css)
        self.ltp_css_window.show()
        self.hide()

    def _on_back_from_ltp_css(self) -> None:
        """Se conecta al botón ATRAS de la pantalla LTP / CSS para volver a
        mostrar esta portada."""
        self.show()
        if self.ltp_css_window is not None:
            self.ltp_css_window.hide()

    def _on_dominio(self) -> None:
        if self.dominio_window is None:
            self.dominio_window = DominioWindow(on_back=self._on_back_from_dominio)
        self.dominio_window.show()
        self.hide()

    def _on_back_from_dominio(self) -> None:
        """Se conecta al botón ATRAS de la pantalla DOMINIO para volver a
        mostrar esta portada."""
        self.show()
        if self.dominio_window is not None:
            self.dominio_window.hide()
