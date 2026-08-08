"""Hoja de estilos (QSS) para imitar el look de la app original:
checkboxes que se resaltan en azul sólido al marcarse, ítems deshabilitados
en gris, y filas en error resaltadas en rojo suave.
"""

MAIN_STYLESHEET = """
QWidget {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #eceae7;
}

QCheckBox {
    padding: 5px 8px;
    border: 1px solid transparent;
    border-radius: 2px;
    background-color: transparent;
    color: #202020;
    spacing: 8px;
}

QCheckBox:disabled {
    color: #9a9a9a;
}

QCheckBox:checked {
    background-color: #16267a;
    color: white;
    font-weight: 600;
}

QCheckBox[installing="true"] {
    background-color: #e8c547;
    color: #202020;
    font-weight: 600;
}

QCheckBox[failed="true"] {
    background-color: #c0392b;
    color: white;
    font-weight: 600;
}

/* Casilla (indicador) del checkbox: negra cuando NO esta seleccionada,
   blanca cuando esta seleccionada (resaltado azul) y tambien blanca
   cuando el item quedo en error (fondo rojo), para que siempre se
   distinga sobre cualquier fondo. */
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #202020;
    border-radius: 2px;
    background-color: #202020;
}

QCheckBox::indicator:checked {
    background-color: #ffffff;
    border: 1px solid #ffffff;
}

QCheckBox::indicator:disabled {
    background-color: #9a9a9a;
    border: 1px solid #9a9a9a;
}

QCheckBox[failed="true"]::indicator {
    background-color: #ffffff;
    border: 1px solid #ffffff;
}

QPushButton {
    background-color: #f4f3f1;
    border: 1px solid #9a9a9a;
    border-radius: 3px;
    padding: 10px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #e2e2e2;
}

QPushButton:pressed {
    background-color: #cfcfcf;
}

QPushButton#installarButton {
    background-color: #ffffff;
    border: 2px solid #202020;
    font-size: 16px;
    font-weight: 700;
}

QPushButton#installarButton:disabled {
    background-color: #d8d8d8;
    color: #8a8a8a;
    border-color: #b0b0b0;
}

QLabel#statusBar {
    color: #444444;
    padding: 4px;
}
"""
