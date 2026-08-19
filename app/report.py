"""Generación del reporte de instalación: datos del equipo + tabla de
aplicaciones instaladas. Se genera en HTML (para verlo/imprimirlo) y en CSV
(para importarlo a Excel u otra herramienta de IT).
"""
from __future__ import annotations

import csv
import datetime
import html
import os
import platform
import re
import socket
import subprocess
import sys
from pathlib import Path

from app.config import APP_ROOT

REPORTS_DIR = APP_ROOT / "reports"


def _run_powershell(command: str) -> str:
    """Corre un comando corto de PowerShell y devuelve su salida (vacío si
    falla o no aplica, por ejemplo al probar esto fuera de Windows)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_computer_name() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "No disponible"


def get_serial_number() -> str:
    value = _run_powershell("(Get-CimInstance -ClassName Win32_BIOS).SerialNumber")
    return value or "No disponible"


def get_asset_tag() -> str:
    value = _run_powershell("(Get-CimInstance -ClassName Win32_SystemEnclosure).SMBIOSAssetTag")
    return value or "No disponible"


# Build de Windows a partir del cual el sistema es Windows 11 (empezó en
# el build 22000). Hace falta este número, y no la clave `ProductName` ni
# la versión "10.0.xxxxx" del registro, para diferenciar Windows 10 de
# 11 -- ver `_fix_windows_11_product_name`.
_WINDOWS_11_MIN_BUILD = 22000


def _fix_windows_11_product_name(product_name: str, build_number: object) -> str:
    """Corrige un bug conocido (y nunca arreglado) de Windows: la clave de
    registro `ProductName`
    (`HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion`) sigue
    diciendo literalmente "Windows 10 ..." en equipos que en realidad
    corren Windows 11 -- confirmado en una VM de prueba real (reporte
    generado mostrando "Windows 10 Enterprise Evaluation (Build
    22621.3880)", cuando el build 22621 es en realidad Windows 11 22H2).
    Windows 10 y 11 comparten la misma rama de versión "10.0.xxxxx", así
    que Microsoft nunca actualizó `ProductName` al pasar de uno a otro; la
    única forma confiable de diferenciarlos es el número de build (ver
    `_WINDOWS_11_MIN_BUILD`), no el texto de esa clave.

    Devuelve `product_name` tal cual si no pudo interpretar
    `build_number`, o si `product_name` no contiene "Windows 10" (para no
    tocar nada en casos ya correctos, o en ediciones/idiomas con un texto
    distinto que no se pueda adivinar con un simple reemplazo)."""
    try:
        build_int = int(str(build_number).split(".")[0])
    except (TypeError, ValueError):
        return product_name
    if build_int >= _WINDOWS_11_MIN_BUILD and "Windows 10" in product_name:
        return product_name.replace("Windows 10", "Windows 11", 1)
    return product_name


def get_windows_version() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                product_name = winreg.QueryValueEx(key, "ProductName")[0]
                build_number = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
                build_display = build_number
                try:
                    ubr = winreg.QueryValueEx(key, "UBR")[0]
                    build_display = f"{build_number}.{ubr}"
                except FileNotFoundError:
                    pass
            product_name = _fix_windows_11_product_name(product_name, build_number)
            return f"{product_name} (Build {build_display})"
        except Exception:
            pass
    return platform.platform() or "No disponible"


# Cualquier caracter que no sea seguro para un nombre de archivo de
# Windows (espacios, barras, dos puntos, etc.) -- pensado para sanear el
# número de serie (viene de WMI, no lo controlamos nosotros) antes de
# usarlo como parte del nombre del reporte, ver `_sanitize_for_filename`.
_FILENAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_for_filename(value: str) -> str:
    """Reemplaza cualquier caracter no seguro para un nombre de archivo
    (espacios, `/`, `\\`, `:`, etc.) por `_`. Si no queda nada usable
    (por ejemplo, el equipo no reporta ningún número de serie y
    `get_serial_number()` devuelve "No disponible" -- que además tiene un
    espacio en el medio), devuelve un valor de respaldo en vez de armar un
    nombre de archivo vacío o roto."""
    cleaned = _FILENAME_UNSAFE_RE.sub("_", (value or "").strip())
    return cleaned or "SERIE_DESCONOCIDA"


FAILED_VERSION_LABEL = "FALLO"

# Caso especial dentro de las que fallaron: un ítem que necesita que el
# técnico reinicie el equipo antes de reintentar (ej. SAP GUI 7.8 con
# código 144/145 -- ver `exit_code_messages` en `config/apps.json` --, o
# NetFX35/BFirst cuando `_is_reboot_pending()` detecta un reinicio
# pendiente antes de correr DISM, ver `app/netfx35_setup.py`). En vez del
# genérico `FAILED_VERSION_LABEL` ("FALLO"), estos se distinguen en el
# reporte con `REBOOT_PENDING_VERSION_LABEL` -- así el técnico que
# revisa el reporte (no necesariamente el mismo que instaló) ve de un
# vistazo cuáles ítems fallidos solo necesitan un reinicio y reintentar,
# sin tener que ir a `logs/` a averiguarlo.
REBOOT_PENDING_VERSION_LABEL = "FALLO (Reinicio Pendiente)"

# Frase que cualquier mensaje de error "a propósito" del catálogo (un
# `exit_code_messages` en apps.json, o una excepción lanzada a mano en
# algún paso "python") debe incluir -- las dos palabras, en cualquier
# orden y sin importar mayúsculas/minúsculas -- para que
# `is_reboot_pending_message()` lo reconozca como un caso de "necesita
# reinicio", no un fallo real sin resolver. Deliberadamente laxo (dos
# palabras sueltas, no una frase exacta) para no depender de que todo
# mensaje futuro use exactamente el mismo orden de palabras ("Reinicio
# Pendiente" vs "Pendiente reinicio"); seguro porque estos mensajes
# siempre son texto que ESTA APP redacta a propósito (nunca stdout/stderr
# crudo de un instalador de terceros, que jamás contendría estas dos
# palabras juntas por casualidad).
_REBOOT_PENDING_WORDS = ("reinicio", "pendiente")


def is_reboot_pending_message(message: str) -> bool:
    """`True` si `message` (el mensaje de error que ve el técnico en el
    tooltip de la casilla) indica que el ítem necesita que el equipo
    reinicie antes de reintentar -- ver `_REBOOT_PENDING_WORDS` arriba
    para el criterio exacto."""
    lowered = (message or "").lower()
    return all(word in lowered for word in _REBOOT_PENDING_WORDS)


def generate_report(
    records: list[tuple[str, str, datetime.datetime, bool]], section_label: str = ""
) -> tuple[Path, Path]:
    """Genera el reporte de instalación. `records` es la lista de TODAS las
    apps que se intentaron instalar, correctas o no:
    (nombre_a_mostrar, version_a_mostrar, hora en que terminó, si tuvo
    éxito). El nombre/versión ya vienen resueltos (detectados del propio
    instalador cuando fue posible, o del catálogo si no).

    Las que fallaron (`success=False`) SÍ aparecen en el reporte -- a
    diferencia de antes, que solo listaba las correctas -- pero con
    `FAILED_VERSION_LABEL` ("FALLO") en la columna de versión en vez de la
    versión real (que nunca llegó a instalarse), y resaltadas en rojo y
    negrita en el HTML (ver `_write_html`) para que se distingan de un
    vistazo. El detalle del error en sí sigue viviendo solo en `logs/` (el
    reporte no tiene espacio para mensajes largos de error).

    `section_label` (opcional, ej. "LTP_CSS") identifica de qué pantalla
    viene el reporte cuando hay más de un catálogo en la app; se agrega al
    nombre del archivo y al título para no mezclarlos con los de APPS.

    El nombre del archivo se identifica por el **número de serie** del
    equipo (`get_serial_number()`, vía WMI -- `Win32_BIOS.SerialNumber`),
    no por el nombre de equipo/hostname: a diferencia del hostname (que
    puede cambiar, o quedar en un nombre genérico "DESKTOP-XXXXX" si la
    unión al dominio falla, ver `app/domain_join.py`), el número de serie
    es un identificador de hardware fijo, así que sirve para encontrar el
    reporte de un equipo puntual sin depender de cómo se llamaba en ese
    momento. El nombre del equipo (hostname) SÍ se sigue mostrando dentro
    del reporte, en la tabla de datos del equipo -- esto solo cambia el
    nombre del ARCHIVO. Devuelve (ruta_html, ruta_csv)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now()
    computer_name = get_computer_name()
    serial = get_serial_number()
    asset_tag = get_asset_tag()
    windows_version = get_windows_version()

    stamp = timestamp.strftime("%Y%m%d_%H%M%S")
    label_part = f"{section_label}_" if section_label else ""
    serial_for_filename = _sanitize_for_filename(serial)
    base_name = f"reporte_{label_part}{serial_for_filename}_{stamp}"
    html_path = REPORTS_DIR / f"{base_name}.html"
    csv_path = REPORTS_DIR / f"{base_name}.csv"

    # Para un ítem fallido, `version` normalmente se descarta y se
    # reemplaza por el genérico FAILED_VERSION_LABEL ("FALLO") -- la
    # versión real nunca llegó a instalarse. La ÚNICA excepción: si quien
    # armó el registro ya decidió que este fallo puntual es un caso de
    # "reinicio pendiente" y pasó `REBOOT_PENDING_VERSION_LABEL` como
    # `version` (ver `MainWindow._on_item_finished`, que usa
    # `is_reboot_pending_message()` para decidirlo), se respeta tal cual
    # en vez de pisarlo -- así el reporte distingue "FALLO" de "FALLO
    # (Reinicio Pendiente)".
    rows = [
        (
            name,
            version if (success or version == REBOOT_PENDING_VERSION_LABEL) else FAILED_VERSION_LABEL,
            ts.strftime("%Y-%m-%d %H:%M:%S"),
            success,
        )
        for name, version, ts, success in records
    ]

    _write_html(html_path, computer_name, serial, asset_tag, windows_version, rows, timestamp, section_label)
    _write_csv(csv_path, computer_name, serial, asset_tag, windows_version, rows)

    return html_path, csv_path


def _app_row_html(name: str, version: str, fecha: str, success: bool) -> str:
    """UNA fila de la tabla de aplicaciones. Si `success` es False, se
    envuelve en la clase CSS `row-failed` (texto en rojo y negrita, ver la
    hoja de estilos embebida en `_write_html`) -- `version` ya viene como
    `FAILED_VERSION_LABEL` ("FALLO") para estas filas, resuelto en
    `generate_report`, no acá."""
    tr_open = "<tr>" if success else '<tr class="row-failed">'
    return f"{tr_open}<td>{html.escape(name)}</td><td>{html.escape(version)}</td><td>{html.escape(fecha)}</td></tr>"


def _write_html(
    path: Path,
    computer_name: str,
    serial: str,
    asset_tag: str,
    windows_version: str,
    rows: list[tuple[str, str, str, bool]],
    timestamp: datetime.datetime,
    section_label: str = "",
) -> None:
    title_suffix = f" — {html.escape(section_label)}" if section_label else ""
    if rows:
        rows_html = "\n".join(_app_row_html(name, version, fecha, success) for name, version, fecha, success in rows)
    else:
        rows_html = (
            '<tr><td colspan="3" style="text-align:center;color:#888;">'
            "No se instaló ninguna aplicación</td></tr>"
        )

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Reporte de instalación - {html.escape(computer_name)}</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; background: #f4f3f1; color: #202020; padding: 24px; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .subtitle {{ color: #555; margin-bottom: 20px; }}
  table.header-info {{ border-collapse: collapse; margin-bottom: 24px; }}
  table.header-info td {{ padding: 4px 12px 4px 0; vertical-align: top; }}
  table.header-info td.label {{ font-weight: 600; white-space: nowrap; }}
  table.apps {{ border-collapse: collapse; width: 100%; background: white; }}
  table.apps th {{ background: #16267a; color: white; text-align: left; padding: 8px 12px; }}
  table.apps td {{ padding: 8px 12px; border-bottom: 1px solid #ddd; }}
  table.apps tr:nth-child(even) {{ background: #f8f8f7; }}
  table.apps tr.row-failed td {{ color: #c0392b; font-weight: 700; }}
</style>
</head>
<body>
  <h1>Reporte de instalación — FS_APP_STN{title_suffix}</h1>
  <div class="subtitle">Generado el {timestamp.strftime('%Y-%m-%d %H:%M:%S')}</div>

  <table class="header-info">
    <tr><td class="label">Nombre del equipo:</td><td>{html.escape(computer_name)}</td></tr>
    <tr><td class="label">Número de serie:</td><td>{html.escape(serial)}</td></tr>
    <tr><td class="label">Asset Tag:</td><td>{html.escape(asset_tag)}</td></tr>
    <tr><td class="label">Versión de Windows:</td><td>{html.escape(windows_version)}</td></tr>
  </table>

  <table class="apps">
    <thead>
      <tr><th>Nombre de la aplicación</th><th>Versión de la aplicación</th><th>Fecha de instalación</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


def _write_csv(
    path: Path,
    computer_name: str,
    serial: str,
    asset_tag: str,
    windows_version: str,
    rows: list[tuple[str, str, str, bool]],
) -> None:
    # El CSV no tiene forma de mostrar color/negrita (es texto plano) --
    # las filas que fallaron se distinguen igual que en el HTML por el
    # valor "FALLO" en la columna de versión (ya resuelto en
    # `generate_report`), simplemente sin remarcarlas visualmente. Por eso
    # se descarta acá el 4to elemento (`success`) de cada fila: el CSV
    # solo tiene 3 columnas.
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Nombre del equipo", computer_name])
        writer.writerow(["Numero de serie", serial])
        writer.writerow(["Asset Tag", asset_tag])
        writer.writerow(["Version de Windows", windows_version])
        writer.writerow([])
        writer.writerow(["Nombre de la aplicacion", "Version de la aplicacion", "Fecha de instalacion"])
        writer.writerows((name, version, fecha) for name, version, fecha, _success in rows)
