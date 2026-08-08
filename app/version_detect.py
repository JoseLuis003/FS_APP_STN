"""Detección automática del nombre "bonito" y la versión de cada
instalador, leyendo los metadatos que trae el propio archivo (en vez de
tener que escribirlos a mano en `config/apps.json`).

- .exe: usa la información de versión de Windows (ProductName /
  ProductVersion, o FileDescription / FileVersion si el instalador no trae
  ProductName/ProductVersion).
- .msi: lee las propiedades ProductName / ProductVersion de la base de
  datos del propio MSI (vía el COM object "WindowsInstaller.Installer").
- scripts (.ps1 / .bat): no tienen metadatos de versión, así que no se
  intenta detectar nada para ellos.

Todo esto solo aplica en Windows (usa PowerShell). Fuera de Windows (por
ejemplo al probar esta app en este entorno de desarrollo) simplemente no
detecta nada y el catálogo cae de vuelta al nombre/version manual definidos
en `config/apps.json`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Instaladores que sí tienen metadatos de version embebidos.
DETECTABLE_TYPES = {"exe", "msi"}

_SEP = "\x1f"  # separador de campos poco probable de aparecer en un nombre real
_LINE_SEP = "\x1e"  # separador de registros


def _escape_ps_single_quoted(value: str) -> str:
    # Dentro de comillas simples de PowerShell, una comilla simple se escapa duplicandola.
    return value.replace("'", "''")


def _build_script(entries: list[tuple[str, str, Path]]) -> str:
    lines = [
        "$ErrorActionPreference = 'SilentlyContinue'",
        "$results = New-Object System.Collections.Generic.List[string]",
        "$installer = $null",
    ]
    needs_msi = any(t == "msi" for _id, t, _p in entries)
    if needs_msi:
        lines.append("try { $installer = New-Object -ComObject WindowsInstaller.Installer } catch {}")

    for item_id, itype, path in entries:
        safe_id = _escape_ps_single_quoted(item_id)
        safe_path = _escape_ps_single_quoted(str(path))
        if itype == "msi":
            lines.append(
                f"""
try {{
    $db = $installer.OpenDatabase('{safe_path}', 0)
    $name = ''
    $ver = ''
    try {{
        $v = $db.OpenView("SELECT Value FROM Property WHERE Property='ProductName'")
        $v.Execute(); $r = $v.Fetch()
        if ($r) {{ $name = $r.StringData(1) }}
    }} catch {{}}
    try {{
        $v2 = $db.OpenView("SELECT Value FROM Property WHERE Property='ProductVersion'")
        $v2.Execute(); $r2 = $v2.Fetch()
        if ($r2) {{ $ver = $r2.StringData(1) }}
    }} catch {{}}
    $results.Add('{safe_id}{_SEP}' + $name + '{_SEP}' + $ver)
}} catch {{
    $results.Add('{safe_id}{_SEP}{_SEP}')
}}
"""
            )
        else:  # exe
            lines.append(
                f"""
try {{
    $vi = (Get-Item -LiteralPath '{safe_path}' -ErrorAction Stop).VersionInfo
    $name = if ($vi.ProductName) {{ $vi.ProductName.Trim() }} elseif ($vi.FileDescription) {{ $vi.FileDescription.Trim() }} else {{ '' }}
    $ver = if ($vi.ProductVersion) {{ $vi.ProductVersion.Trim() }} elseif ($vi.FileVersion) {{ $vi.FileVersion.Trim() }} else {{ '' }}
    $results.Add('{safe_id}{_SEP}' + $name + '{_SEP}' + $ver)
}} catch {{
    $results.Add('{safe_id}{_SEP}{_SEP}')
}}
"""
            )

    lines.append(f"$results -join \"{_LINE_SEP}\"")
    return "\n".join(lines)


def detect_versions(entries: list[tuple[str, str, Path]]) -> dict[str, tuple[str, str]]:
    """`entries`: lista de (item_id, installer_type, ruta_resuelta_al_instalador).

    Devuelve {item_id: (nombre_detectado, version_detectada)} solo para los
    ítems donde se pudo leer algo (nombre y/o version no vacíos). Corre TODO
    en una sola invocación de PowerShell para no pagar el costo de arrancar
    un proceso por cada instalador.
    """
    detectable = [(i, t, p) for i, t, p in entries if t in DETECTABLE_TYPES]
    if not detectable or sys.platform != "win32":
        return {}

    script = _build_script(detectable)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
    except Exception:
        return {}

    if not output:
        return {}

    detected: dict[str, tuple[str, str]] = {}
    for line in output.split(_LINE_SEP):
        parts = line.split(_SEP)
        if len(parts) != 3:
            continue
        item_id, name, version = (p.strip() for p in parts)
        if name or version:
            detected[item_id] = (name, version)
    return detected


def format_label(fallback_name: str, fallback_version: str, detected: tuple[str, str] | None) -> str:
    """Arma el texto final del checkbox: nombre detectado (o el del catálogo
    si no se detectó nada) + version al lado, entre paréntesis."""
    name = fallback_name
    version = fallback_version if fallback_version and fallback_version != "N/D" else ""

    if detected:
        detected_name, detected_version = detected
        if detected_name:
            name = detected_name
        if detected_version:
            version = detected_version

    return f"{name}  (v{version})" if version else name
