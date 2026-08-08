"""Punto de entrada de FS_APP_STN (instalador desatendido).

Uso:
    python main.py

Empaquetado a .exe único (ejecutar en Windows, ver README.md):
    pyinstaller build.spec
"""
import sys

from PySide6.QtWidgets import QApplication

from app.ui.home_window import HomeWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FS_APP_STN")
    # Forzamos el estilo "Fusion": los estilos nativos de Windows/macOS
    # ignoran buena parte del QSS de QCheckBox::indicator (la casilla se
    # dibuja con el tema del sistema y no respeta los colores que le
    # definimos). Con Fusion, Qt dibuja los controles el mismo en
    # cualquier plataforma y sí obedece la hoja de estilos.
    app.setStyle("Fusion")
    # La app ahora arranca en la portada (FS APP PORTABLE), que a su vez
    # abre la pantalla de instalación (MainWindow) al presionar APPS.
    window = HomeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
