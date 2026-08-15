"""Utilidades de UI compartidas entre las distintas pantallas de catálogo
(APPS, LTP / CSS, y las que vengan después): construir una columna de
checkboxes a partir de un `AppColumn`, con soporte para "grupos
exclusivos" — varios checkboxes que se muestran juntos en una misma fila y
de los que solo se puede marcar uno a la vez (por ejemplo GEMALTO / 3M /
DESKO en la pantalla LTP / CSS: son formas distintas de leer tarjetas, así
que no tiene sentido instalar más de una a la vez)."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

from app.config import AppColumn, AppItem


def build_checkbox_column(
    column: AppColumn,
    checkboxes: dict[str, tuple[AppItem, QCheckBox]],
    inline_widgets: dict[str, QWidget] | None = None,
) -> QVBoxLayout:
    """Arma una columna de checkboxes a partir de un `AppColumn`, en el
    mismo orden en que aparecen sus ítems. Los ítems que comparten un mismo
    `exclusive_group` (no vacío) se dibujan juntos en una sola fila
    horizontal la primera vez que aparece alguno de ellos, y quedan
    enlazados entre sí (ver `_wire_exclusive_group`). Los ítems ya
    encontrados/creados se registran en `checkboxes` (mutado in-place),
    igual que hacía el código anterior en `MainWindow._build_column`.

    `inline_widgets` (opcional): {item_id: widget} — si el id de un ítem
    aparece acá, ese widget se agrega dentro de esta misma columna, justo
    debajo de su checkbox (en vez de vivir aparte, más abajo, fuera de las
    columnas). Pensado para paneles como `AppShellConfigPanel`, que deben
    verse pegados a la casilla que los despliega. El llamador sigue
    encargándose de mostrar/ocultar el widget (`setVisible`) según el
    estado del checkbox -- esto solo decide DÓNDE se dibuja."""
    inline_widgets = inline_widgets or {}
    col_layout = QVBoxLayout()
    col_layout.setSpacing(2)

    for g_index, group in enumerate(column.groups):
        if g_index > 0:
            col_layout.addSpacing(20)

        # Agrupa los ítems por exclusive_group, preservando su orden de
        # aparición dentro del grupo (necesario para poder crear todos los
        # checkboxes del grupo de una sola vez, apenas se encuentra el
        # primero de ellos).
        members_by_group: dict[str, list[AppItem]] = {}
        for item in group.items:
            if item.exclusive_group:
                members_by_group.setdefault(item.exclusive_group, []).append(item)

        rendered_groups: set[str] = set()
        for item in group.items:
            if item.exclusive_group:
                if item.exclusive_group in rendered_groups:
                    continue  # ya se dibujó esta fila cuando apareció el primer ítem del grupo
                rendered_groups.add(item.exclusive_group)
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_checkboxes: list[QCheckBox] = []
                for member in members_by_group[item.exclusive_group]:
                    checkbox = QCheckBox(member.label)
                    checkbox.setChecked(member.default_checked)
                    checkbox.setEnabled(member.enabled)
                    checkboxes[member.id] = (member, checkbox)
                    row_layout.addWidget(checkbox)
                    row_checkboxes.append(checkbox)
                row_layout.addStretch(1)
                col_layout.addLayout(row_layout)
                _wire_exclusive_group(row_checkboxes)
                for member in members_by_group[item.exclusive_group]:
                    if member.id in inline_widgets:
                        col_layout.addWidget(inline_widgets[member.id])
            else:
                checkbox = QCheckBox(item.label)
                checkbox.setChecked(item.default_checked)
                checkbox.setEnabled(item.enabled)
                checkboxes[item.id] = (item, checkbox)
                col_layout.addWidget(checkbox)
                if item.id in inline_widgets:
                    col_layout.addWidget(inline_widgets[item.id])

    col_layout.addStretch(1)
    return col_layout


def _wire_exclusive_group(members: list[QCheckBox]) -> None:
    """Enlaza un grupo de checkboxes para que se comporten como un grupo de
    radio buttons: al marcar uno, se desmarcan y deshabilitan los demás; al
    desmarcarlo, los demás vuelven a habilitarse (pero siguen desmarcados
    salvo que el técnico los marque a mano)."""

    def make_handler(current: QCheckBox):
        def handler(checked: bool) -> None:
            for other in members:
                if other is current:
                    continue
                if checked:
                    other.setChecked(False)
                other.setEnabled(not checked)

        return handler

    # Si por algún motivo más de uno viniera marcado por defecto en el
    # catálogo, se respeta el primero y se deshabilitan los demás desde el
    # arranque (en vez de dejar un estado inconsistente en pantalla).
    already_checked = [cb for cb in members if cb.isChecked()]
    if already_checked:
        chosen = already_checked[0]
        for other in members:
            if other is not chosen:
                other.setChecked(False)
                other.setEnabled(False)

    for cb in members:
        cb.toggled.connect(make_handler(cb))


def reapply_exclusive_constraints(checkboxes: dict[str, tuple[AppItem, QCheckBox]]) -> None:
    """Vuelve a aplicar la regla de "solo uno a la vez" en todos los grupos
    exclusivos presentes en `checkboxes`. Hace falta llamarla después de
    rehabilitar checkboxes en bloque (por ejemplo, al terminar una cola de
    instalación con `_set_controls_enabled(True)`), porque ese rehabilitado
    genérico no sabe nada de grupos exclusivos y podría dejar habilitados
    por error a los "perdedores" de un grupo cuyo ganador sigue marcado."""
    groups: dict[str, list[QCheckBox]] = {}
    for item, checkbox in checkboxes.values():
        if item.exclusive_group:
            groups.setdefault(item.exclusive_group, []).append(checkbox)

    for members in groups.values():
        checked = [cb for cb in members if cb.isChecked()]
        if checked:
            chosen = checked[0]
            for cb in members:
                if cb is not chosen:
                    cb.setEnabled(False)
