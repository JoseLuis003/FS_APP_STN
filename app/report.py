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


def get_windows_version() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                product_name = winreg.QueryValueEx(key, "ProductName")[0]
                build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
                try:
                    ubr = winreg.QueryValueEx(key, "UBR")[0]
                    build = f"{build}.{ubr}"
                except FileNotFoundError:
                    pass
            return f"{product_name} (Build {build})"
        except Exception:
            pass
    return platform.platform() or "No disponible"


def generate_report(records: list[tuple[str, str, datetime.datetime]]) -> tuple[Path, Path]:
    """Genera el reporte de instalación. `records` es la lista de apps que
    se instalaron correctamente: (nombre_a_mostrar, version_a_mostrar, hora
    en que terminó). El nombre/versión ya vienen resueltos (detectados del
    propio instalador cuando fue posible, o del catálogo si no).
    Devuelve (ruta_html, ruta_csv)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now()
    computer_name = get_computer_name()
    serial = get_serial_number()
    asset_tag = get_asset_tag()
    windows_version = get_windows_version()

    stamp = timestamp.strftime("%Y%m%d_%H%M%S")
    base_name = f"reporte_{computer_name}_{stamp}"
    html_path = REPORTS_DIR / f"{base_name}.html"
    csv_path = REPORTS_DIR / f"{base_name}.csv"

    rows = [(name, version, ts.strftime("%Y-%m-%d %H:%M:%S")) for name, version, ts in records]

    _write_html(html_path, computer_name, serial, asset_tag, windows_version, rows, timestamp)
    _write_csv(csv_path, computer_name, serial, asset_tag, windows_version, rows)

    return html_path, csv_path


def _write_html(
    path: Path,
    computer_name: str,
    serial: str,
    asset_tag: str,
    windows_version: str,
    rows: list[tuple[str, str, str]],
    timestamp: datetime.datetime,
) -> None:
    if rows:
        rows_html = "\n".join(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(version)}</td><td>{html.escape(fecha)}</td></tr>"
            for name, version, fecha in rows
        )
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
</style>
</head>
<body>
  <h1>Reporte de instalación — FS_APP_STN</h1>
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
    rows: list[tuple[str, str, str]],
) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Nombre del equipo", computer_name])
        writer.writerow(["Numero de serie", serial])
        writer.writerow(["Asset Tag", asset_tag])
        writer.writerow(["Version de Windows", windows_version])
        writer.writerow([])
        writer.writerow(["Nombre de la aplicacion", "Version de la aplicacion", "Fecha de instalacion"])
        writer.writerows(rows)
