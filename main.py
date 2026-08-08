"""Punto de entrada de FS_APP_STN (instalador desatendido).

Uso:
    python main.py

Empaquetado a .exe único (ejecutar en Windows, ver README.md):
    pyinstaller build.spec
"""
import sys

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FS_APP_STN")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
