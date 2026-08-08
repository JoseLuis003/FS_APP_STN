"""Hoja de estilos (QSS) para imitar el look de la app original:
checkboxes que se resaltan en azul sólido al marcarse, ítems deshabilitados
en gris, y filas en error resaltadas en rojo suave.

`build_stylesheet()` recibe la carpeta de assets en tiempo de ejecución
(distinta en modo desarrollo vs. empaquetado con PyInstaller) para poder
insertar la ruta absoluta del ícono del checkmark dentro del QSS.
"""
from pathlib import Path


def build_stylesheet(assets_dir: Path) -> str:
    # Qt exige '/' en las rutas de QSS incluso en Windows, y una ruta
    # absoluta evita cualquier ambigüedad sobre desde dónde se resuelve.
    check_icon = (Path(assets_dir) / "check.png").as_posix()

    return f"""
QWidget {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: #eceae7;
}}

QCheckBox {{
    padding: 5px 8px;
    border: 1px solid transparent;
    border-radius: 2px;
    background-color: transparent;
    color: #202020;
    spacing: 8px;
}}

QCheckBox:disabled {{
    color: #9a9a9a;
}}

QCheckBox:checked {{
    background-color: #16267a;
    color: white;
    font-weight: 600;
}}

QCheckBox[installing="true"] {{
    background-color: #e8c547;
    color: #202020;
    font-weight: 600;
}}

QCheckBox[failed="true"] {{
    background-color: #c0392b;
    color: white;
    font-weight: 600;
}}

/* Casilla (indicador) del checkbox:
   - sin seleccionar: fondo transparente, marco negro
   - seleccionado: fondo blanco, marco blanco, flechita (check) negra
   - error de instalación: fondo blanco, marco blanco (igual que seleccionado,
     asi se distingue sobre el rojo de fondo de la fila) */
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid #202020;
    border-radius: 2px;
    background-color: transparent;
}}

QCheckBox::indicator:checked {{
    background-color: #ffffff;
    border: 2px solid #ffffff;
    image: url({check_icon});
}}

QCheckBox::indicator:disabled {{
    background-color: transparent;
    border: 2px solid #9a9a9a;
}}

QCheckBox[failed="true"]::indicator {{
    background-color: #ffffff;
    border: 2px solid #ffffff;
    image: none;
}}

QPushButton {{
    background-color: #f4f3f1;
    border: 1px solid #9a9a9a;
    border-radius: 3px;
    padding: 10px 14px;
    font-weight: 600;
    color: #000000;
}}

QPushButton:hover {{
    background-color: #e2e2e2;
}}

QPushButton:pressed {{
    background-color: #cfcfcf;
}}

QPushButton:disabled {{
    color: #6a6a6a;
}}

QPushButton#installarButton {{
    background-color: #ffffff;
    border: 2px solid #202020;
    font-size: 16px;
    font-weight: 700;
    color: #000000;
}}

QPushButton#installarButton:disabled {{
    background-color: #d8d8d8;
    color: #8a8a8a;
    border-color: #b0b0b0;
}}

QLabel#statusBar {{
    color: #444444;
    padding: 4px;
}}

QLabel#activePathLabel {{
    color: #555555;
    font-size: 11px;
    padding: 2px 4px;
}}

QProgressBar#installProgressBar {{
    background-color: #e0e0e0;
    border: 1px solid #9a9a9a;
    border-radius: 3px;
}}

QProgressBar#installProgressBar::chunk {{
    background-color: #16267a;
    border-radius: 2px;
}}
"""
