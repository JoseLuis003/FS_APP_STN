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

BGR y OCR (las otras 2 casillas del submenú DEVICE's) tienen su propia
lógica, completamente separada de la de ATB/BTP/DCP: en vez de editar el
INI de arriba, crean/actualizan un archivo XML,

    C:\\Program Files (x86)\\DXC Technology\\PssAppShell\\Mastcom\\Mastcom.xml

con un `<Session>` por cada una marcada (ver `apply_appshell_mastcom_config`
más abajo para el detalle). Si el archivo no existe, se crea completo; si
ya existe, NO se borra lo que ya tenía configurado -- solo se agrega (o se
actualiza in-place, si ya había una sesión con el mismo Alias) la
información de la(s) opción(es) marcada(s)."""
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


# --------------------------------------------------------------------------
# BGR / OCR -- Mastcom.xml (ver el docstring del módulo). A diferencia de
# ATB/BTP/DCP (que editan un INI ya existente), acá el archivo puede no
# existir todavía -- si no existe, se crea completo; si existe, se agrega o
# actualiza (por Alias) sin tocar el resto del archivo.
# --------------------------------------------------------------------------

DEFAULT_MASTCOM_XML_PATH = Path(
    r"C:\Program Files (x86)\DXC Technology\PssAppShell\Mastcom\Mastcom.xml"
)

# Alias que identifica a cada sesión dentro del <Device>, y el bloque
# <Session>...</Session> completo (ya indentado igual que el resto del
# archivo -- 3 tabs para <Session>/</Session>, 4 tabs para sus campos)
# que corresponde a cada opción del submenú DEVICE's.
_BGR_ALIAS = "BGR1"
_BGR_SESSION_BLOCK = (
    "\t\t\t<Session Name=\"Serial AEA\" Type=\"Reader\" Subtype=\"BGR\" Alias=\"BGR1\">\n"
    "\t\t\t\t<DLL>SERIALPORT.DLL</DLL>\n"
    "\t\t\t\t<Protocol>Serial AEA</Protocol>\n"
    "\t\t\t\t<Resource>COM6</Resource>\n"
    "\t\t\t\t<Speed>19200</Speed>\n"
    "\t\t\t\t<Parity>N</Parity>\n"
    "\t\t\t\t<Databits>8</Databits>\n"
    "\t\t\t\t<Stopbits>1</Stopbits>\n"
    "\t\t\t\t<FlowControl>Hardware</FlowControl>\n"
    "\t\t\t\t<ReceiptPrinter>NO</ReceiptPrinter>\n"
    "\t\t\t</Session>\n"
)

_OCR_ALIAS = "RTE1"
_OCR_SESSION_BLOCK = (
    "\t\t\t<Session Name=\"Serial\" Type=\"Reader\" Subtype=\"RTE\" Alias=\"RTE1\">\n"
    "\t\t\t\t<DLL>SERIALPORT.DLL</DLL>\n"
    "\t\t\t\t<Protocol>Serial Reader</Protocol>\n"
    "\t\t\t\t<Resource>COM9</Resource>\n"
    "\t\t\t\t<Speed>9600</Speed>\n"
    "\t\t\t\t<Parity>E</Parity>\n"
    "\t\t\t\t<Databits>7</Databits>\n"
    "\t\t\t\t<Stopbits>1</Stopbits>\n"
    "\t\t\t\t<FlowControl>Hardware</FlowControl>\n"
    "\t\t\t</Session>\n"
)

# Orden fijo de aplicación (no depende del orden en que el técnico marcó
# las casillas), igual que DEVICE_ORDER para ATB/BTP/DCP.
MASTCOM_OPTION_ORDER = ["BGR", "OCR"]

# option -> (Alias, bloque <Session> completo)
_MASTCOM_SESSIONS: dict[str, tuple[str, str]] = {
    "BGR": (_BGR_ALIAS, _BGR_SESSION_BLOCK),
    "OCR": (_OCR_ALIAS, _OCR_SESSION_BLOCK),
}

# Bloque <Device>...</Device> completo, con Type="DEVHAN" (el identificador
# que se busca en un archivo ya existente -- ver `_DEVICE_BLOCK_PATTERN`).
_DEVICE_BLOCK_PATTERN = re.compile(
    r'(?P<open><Device\b[^>]*Type="DEVHAN"[^>]*>)(?P<inner>.*?)(?P<close></Device>)',
    re.DOTALL,
)


def _build_mastcom_xml(session_blocks: str) -> str:
    """Arma el archivo Mastcom.xml completo (Configuration/OPAT/Device),
    con `session_blocks` (uno o más bloques <Session>...</Session>, ya
    concatenados) dentro del único <Device>. Se usa solo cuando el archivo
    todavía no existe."""
    return (
        "<Configuration>\n"
        "\t<OPAT>\n"
        '\t\t<Device Type="DEVHAN" Name="PSSAppShell" DialogVersion="8.01">\n'
        f"{session_blocks}"
        "\t\t</Device>\n"
        "\t</OPAT>\n"
        "</Configuration>\n"
    )


def apply_appshell_mastcom_config(
    selected_options: list[str],
    xml_path: Path = DEFAULT_MASTCOM_XML_PATH,
) -> str:
    """Aplica, para cada opción en `selected_options` (subconjunto de
    "BGR"/"OCR", en cualquier orden), su sesión correspondiente en
    `xml_path` (ver el docstring del módulo).

    Si el archivo no existe, se crea completo (Configuration/OPAT/Device)
    con solo la(s) sesión(es) seleccionada(s). Si ya existe, se busca el
    bloque `<Device Type="DEVHAN" ...>...</Device>`: por cada opción
    seleccionada, si ya hay una sesión con su mismo Alias (BGR1/RTE1), se
    reemplaza in-place (para no dejar dos sesiones BGR duplicadas si se
    vuelve a aplicar); si no, se agrega al final, SIN tocar ninguna otra
    sesión que ya estuviera configurada ahí (ej. si antes se aplicó BGR y
    ahora se aplica solo OCR, la sesión BGR existente no se toca).

    Se procesan siempre en el orden fijo `MASTCOM_OPTION_ORDER`, sin
    importar el orden de `selected_options`.

    Devuelve un mensaje corto de éxito para mostrar en el estado de la
    pantalla. Lanza `AppShellConfigError` si no se seleccionó ninguna
    opción, o si el archivo ya existe pero no tiene el bloque
    `<Device Type="DEVHAN" ...>` esperado."""
    options = [o for o in MASTCOM_OPTION_ORDER if o in set(selected_options)]
    if not options:
        raise AppShellConfigError("No hay ninguna opción de DEVICE's (BGR/OCR) seleccionada.")

    xml_path = Path(xml_path)

    if not xml_path.exists():
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        session_blocks = "".join(_MASTCOM_SESSIONS[o][1] for o in options)
        with xml_path.open("w", encoding="utf-8", newline="") as f:
            f.write(_build_mastcom_xml(session_blocks))
        return f"Mastcom: {xml_path} (creado, {', '.join(options)})"

    with xml_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()

    device_match = _DEVICE_BLOCK_PATTERN.search(text)
    if device_match is None:
        raise AppShellConfigError(
            f"El archivo '{xml_path}' ya existe pero no tiene el bloque "
            "<Device Type=\"DEVHAN\" ...>...</Device> esperado."
        )

    inner = device_match.group("inner")
    for option in options:
        alias, session_block = _MASTCOM_SESSIONS[option]
        alias_pattern = re.compile(
            rf'<Session\b[^>]*Alias="{re.escape(alias)}"[^>]*>.*?</Session>[ \t]*\r?\n?',
            re.DOTALL,
        )
        if alias_pattern.search(inner):
            # Ya había una sesión de esta opción (de una corrida anterior):
            # se reemplaza in-place, sin duplicarla.
            inner = alias_pattern.sub(session_block, inner, count=1)
        else:
            # No tocar el resto del contenido -- solo se agrega al final,
            # con una indentación consistente antes de </Device>.
            inner = inner.rstrip(" \t\r\n") + "\n" + session_block

    # Normaliza la indentación justo antes de </Device> (cosmético -- no
    # afecta ningún dato ya configurado, todo el contenido de `inner` se
    # conserva tal cual salvo por este espacio en blanco final).
    inner = inner.rstrip(" \t\r\n") + "\n\t\t"

    new_text = text[: device_match.start("inner")] + inner + text[device_match.start("close") :]

    with xml_path.open("w", encoding="utf-8", newline="") as f:
        f.write(new_text)

    return f"Mastcom: {xml_path} ({', '.join(options)})"
