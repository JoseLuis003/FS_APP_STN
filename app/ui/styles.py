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

/* Antes esta hoja de estilos se aplicaba con `.setStyleSheet(...)` en cada
   ventana por separado, y un QMessageBox (los diálogos de "Instalación
   finalizada", "No se pudo unir al dominio", etc.) es una ventana de nivel
   superior aparte -- NO hereda el `.setStyleSheet()` de la ventana que lo
   abrió, solo lo que esté puesto a nivel de QApplication (ver `main.py`).
   Por eso esos diálogos se veían con la paleta cruda del sistema: en
   Windows con tema oscuro, fondo negro con letras casi del mismo tono.
   Con la regla de `QLabel` de arriba ya el texto queda oscuro y legible;
   acá se fija el fondo del propio cuadro de diálogo para que haga
   contraste con ese texto oscuro.
*/
QMessageBox {{
    background-color: #eceae7;
}}

/* Mismo problema que el QScrollArea de más abajo: un QLabel normal (sin
   `objectName`, como los textos de introducción o las etiquetas que arma
   QFormLayout — "Nombre del equipo:", "Usuario:", etc.) no tiene color de
   letra propio en esta hoja de estilos, así que toma el de la paleta del
   sistema. En Windows con tema oscuro esa paleta pone el texto en blanco,
   y como el fondo de la ventana es claro (#eceae7), el texto queda casi
   invisible. Los QLabel con `objectName` propio (`#statusBar`,
   `#activePathLabel`) ya tienen su color explícito más abajo y ese
   selector, al ser más específico, sigue ganando sobre esta regla general.
*/
QLabel {{
    color: #202020;
}}

/* Sin esto, un QScrollArea (usado en la pantalla LTP / CSS para que
   ATRAS/INSTALAR no se empujen fuera de la vista) pinta su propio fondo
   con la paleta del sistema en vez del fondo claro de la app — en Windows
   con tema oscuro eso sale negro, y el texto oscuro de los checkboxes se
   vuelve casi invisible encima. Puesto acá (en la hoja de estilos global)
   y no como stylesheet local del widget, para que no rompa el cascadeo
   de QSS de los checkboxes que viven adentro (ver bug corregido: marcar
   un checkbox dentro del área con scroll perdía el resaltado azul de
   ":checked" si el fondo se forzaba con un stylesheet aparte). El
   selector `QScrollArea > QWidget > QWidget` alcanza tanto el viewport
   interno como el widget de contenido.
*/
QScrollArea {{
    background-color: #eceae7;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
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
