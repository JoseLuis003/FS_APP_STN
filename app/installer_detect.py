"""Sugerencia (no garantía) de los switches de instalación silenciosa de un
instalador nuevo, buscando firmas conocidas de frameworks de empaquetado
dentro del propio archivo .exe. Para .msi se puede afirmar con certeza que
los switches estándar de Windows Installer funcionan siempre.

Esto es solo un punto de partida razonable — el técnico que agrega la
aplicación debe confirmar que el switch sugerido realmente instala en
silencio antes de dejarlo en el catálogo (la única forma 100% segura de
saberlo es probándolo).
"""
from __future__ import annotations

from pathlib import Path

# (patrón de bytes a buscar en el .exe, switches sugeridos, nombre del framework)
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"Inno Setup", "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART", "Inno Setup"),
    (b"Nullsoft.NSIS", "/S", "NSIS (Nullsoft)"),
    (b"NullsoftInst", "/S", "NSIS (Nullsoft)"),
    (b"InstallShield", '/s /v"/qn"', "InstallShield"),
    (b"Wise Installation", "/s", "Wise Installer"),
    (b"WiX Toolset", "/quiet /norestart", "WiX Burn bootstrapper"),
    (b"InstallAware", "/s", "InstallAware"),
    (b"Advanced Installer", "/quiet", "Advanced Installer"),
]

_BYTES_TO_SCAN = 8_000_000  # primeros ~8MB del archivo alcanzan para encontrar la firma


def detect_silent_args(installer_path: Path, installer_type: str) -> tuple[str, str]:
    """Devuelve (switches_sugeridos, explicación).

    `switches_sugeridos` puede venir vacío si no se reconoció nada — en ese
    caso `explicación` trae sugerencias genéricas para probar a mano.
    """
    if installer_type == "msi":
        return "/qn /norestart", "Es un .msi: estos switches de Windows Installer siempre funcionan."

    if installer_type == "script":
        return "", "Los scripts (.ps1/.bat) no tienen switches de instalación; se ejecutan tal cual."

    try:
        with open(installer_path, "rb") as f:
            content = f.read(_BYTES_TO_SCAN)
    except OSError:
        content = b""

    for pattern, args, framework in _SIGNATURES:
        if pattern in content:
            return args, f'Se detectó que este instalador usa "{framework}"; este es su switch silencioso típico.'

    return "", (
        "No se pudo identificar el framework del instalador. Prueba con /S, /s, /silent, /quiet, "
        "/VERYSILENT o revisa la documentación del fabricante — y confírmalo ejecutándolo tú mismo "
        "antes de dejarlo en el catálogo."
    )
