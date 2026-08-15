"""Lógica de las opciones ATB / BTP / DCP del submenú DEVICE's de "AppShell
Configuracion" (catálogo LTP / CSS, ver `app/ui/appshell_config_panel.py`).

A diferencia del resto de ítems del catálogo, estas opciones no ejecutan un
instalador tradicional (.exe/.msi/.bat): en vez de eso, editan directamente
el archivo INI de configuración de AppShell que ya está en el equipo:

    C:\\Program Files (x86)\\DXC Technology\\PssAppShell\\Configurations\\PrintAgent_COPA_PROD.ini

Para cada casilla marcada (ATB, BTP y/o DCP), se agregan dos valores en ese
archivo:

- En la línea `device.comport=`: el puerto COM de ese equipo (ATB -> COM7,
  BTP -> COM8, DCP -> COM9).
- En la línea `device.list=`: el identificador de ese equipo (ATB -> ATB1,
  BTP -> BTP1, DCP -> DCP1).

En ambos casos, si la línea ya tiene algún valor después del signo `=`, el
nuevo valor se agrega al final separado por una coma SIN espacio (ej.
`device.comport=COM7` -> `device.comport=COM7,COM8` al aplicar también
BTP). Si la línea está vacía después del `=`, el valor simplemente se
escribe ahí, sin coma. Esto permite marcar y aplicar ATB, BTP y DCP en
corridas distintas (o juntas, en cualquier combinación) sin perder lo que
ya se había configurado antes.

BGR, OCR y BGR-OCR (las otras 3 casillas del submenú DEVICE's) no tienen
ninguna lógica todavía -- no se tocan acá."""
from __future__ import annotations

import re
from pathlib import Path

# Ruta donde vive el INI de configuración de AppShell en el equipo.
DEFAULT_INI_PATH = Path(
    r"C:\Program Files (x86)\DXC Technology\PssAppShell\Configurations\PrintAgent_COPA_PROD.ini"
)

# Orden fijo de aplicación (no depende del orden en que el técnico marcó
# las casillas) -- por (puerto COM, identificador) a agregar en device.list=.
_DEVICE_VALUES: dict[str, tuple[str, str]] = {
    "ATB": ("COM7", "ATB1"),
    "BTP": ("COM8", "BTP1"),
    "DCP": ("COM9", "DCP1"),
}
DEVICE_ORDER = ["ATB", "BTP", "DCP"]

_COMPORT_KEY = "device.comport"
_LIST_KEY = "device.list"


class AppShellConfigError(Exception):
    """Error esperado (archivo/línea no encontrada, ninguna opción marcada,
    etc.) al aplicar la configuración de AppShell. El mensaje ya viene
    listo para mostrárselo tal cual al técnico."""


def _key_pattern(key: str) -> re.Pattern[str]:
    # device.comport=XXXX -> grupo 1 = "device.comport=", grupo 2 = "XXXX"
    # (el valor existente, puede estar vacío), hasta fin de línea (sin
    # incluir \r\n) para preservar el salto de línea original tal cual.
    return re.compile(rf"(?m)^({re.escape(key)}=)([^\r\n]*)")


_COMPORT_PATTERN = _key_pattern(_COMPORT_KEY)
_LIST_PATTERN = _key_pattern(_LIST_KEY)


def _append_value(text: str, pattern: re.Pattern[str], new_value: str, key: str, ini_path: Path) -> str:
    """Agrega `new_value` al final del valor existente de la línea que
    matchea `pattern` (separado por coma sin espacio si ya hay algo), o lo
    escribe directo si la línea está vacía después del `=`. Lanza
    `AppShellConfigError` si la línea `key=` no aparece en el archivo."""

    def _replace(match: re.Match[str]) -> str:
        existing = match.group(2)
        if existing:
            return match.group(1) + existing + "," + new_value
        return match.group(1) + new_value

    updated_text, hits = pattern.subn(_replace, text)
    if hits == 0:
        raise AppShellConfigError(f"No se encontró ninguna línea '{key}=' en '{ini_path}'.")
    return updated_text


def apply_appshell_device_config(
    selected_devices: list[str],
    ini_path: Path = DEFAULT_INI_PATH,
) -> str:
    """Aplica, para cada equipo en `selected_devices` (subconjunto de
    "ATB"/"BTP"/"DCP", en cualquier orden), su puerto COM y su
    identificador en `ini_path` (ver el docstring del módulo).

    Se procesan siempre en el orden fijo `DEVICE_ORDER`, sin importar el
    orden de `selected_devices`, para que el resultado en el archivo sea
    predecible sin importar en qué orden estén las casillas en pantalla.

    Devuelve un mensaje corto de éxito para mostrar en el estado de la
    pantalla. Lanza `AppShellConfigError` si no se seleccionó ningún
    equipo, si el archivo no existe, o si alguna de las líneas requeridas
    no aparece en el archivo -- el llamador decide cómo mostrarlo (igual
    que el resto de errores de esta pantalla)."""
    devices = [d for d in DEVICE_ORDER if d in set(selected_devices)]
    if not devices:
        raise AppShellConfigError("No hay ninguna opción de DEVICE's (ATB/BTP/DCP) seleccionada.")

    ini_path = Path(ini_path)
    if not ini_path.exists():
        raise AppShellConfigError(f"No se encontró el archivo '{ini_path}'.")

    with ini_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()

    for device in devices:
        comport_value, list_value = _DEVICE_VALUES[device]
        text = _append_value(text, _COMPORT_PATTERN, comport_value, _COMPORT_KEY, ini_path)
        text = _append_value(text, _LIST_PATTERN, list_value, _LIST_KEY, ini_path)

    with ini_path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)

    return f"AppShell: {ini_path} ({', '.join(devices)})"
