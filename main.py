"""Punto de entrada de FS_APP_STN (instalador desatendido).

Uso:
    python main.py

Empaquetado a .exe único (ejecutar en Windows, ver README.md):
    pyinstaller build.spec
"""
import sys

from PySide6.QtWidgets import QApplication

from app.config import ASSETS_DIR
from app.ui.home_window import HomeWindow
from app.ui.styles import build_stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FS_APP_STN")
    # Forzamos el estilo "Fusion": los estilos nativos de Windows/macOS
    # ignoran buena parte del QSS de QCheckBox::indicator (la casilla se
    # dibuja con el tema del sistema y no respeta los colores que le
    # definimos). Con Fusion, Qt dibuja los controles el mismo en
    # cualquier plataforma y sí obedece la hoja de estilos.
    app.setStyle("Fusion")
    # La hoja de estilos se aplica a nivel de QApplication (no por ventana)
    # a propósito: un QMessageBox (u otro diálogo) abierto con
    # `QMessageBox.warning(self, ...)` es una ventana de nivel superior
    # aparte, y NO hereda el `.setStyleSheet(...)` puesto sobre una ventana
    # puntual (LtpCssWindow, DominioWindow, etc.) — solo hereda lo que esté
    # puesto en la QApplication. Sin esto, los cuadros de diálogo de
    # error/advertencia quedan sin el color de letra ni el fondo de la app,
    # y en Windows con tema oscuro el texto queda invisible (letras oscuras
    # sobre fondo negro, o viceversa).
    app.setStyleSheet(build_stylesheet(ASSETS_DIR))
    # La app ahora arranca en la portada (FS APP PORTABLE), que a su vez
    # abre la pantalla de instalación (MainWindow) al presionar APPS.
    window = HomeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
