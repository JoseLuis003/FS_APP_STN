"""Creación de accesos directos (.lnk) en el escritorio público.

Cuando termina de aplicarse la configuración de Shares (ver
`app/shares_config_apply.py` y `LtpCssWindow._run_shares_configuration()`),
hay que dejar 2 accesos directos en `C:\\Users\\Public\\Desktop` -- ahí (y
no en el escritorio del usuario que inició sesión) para que se vean sin
importar con qué cuenta se entre al equipo: uno para `LTPGUI32.exe` ("LTP
SHARES") y otro para `LTPHPS32.exe` ("LiteGUI").

Es el equivalente en Python del código VB.NET que ya existía (usaba
`WScript.Shell` vía COM, con `CreateObject`); acá se hace lo mismo con
`pywin32` (`win32com.client.Dispatch("WScript.Shell")`, el mismo objeto
COM, solo que invocado desde Python en vez de VB.NET).

El valor de CIUDAD se arma en los argumentos ya resuelto (viene del campo
CIUDAD del panel), pero "%COMPUTERNAME%" se deja tal cual, como texto
literal -- NO se reemplaza por el nombre real del equipo. Así lo hacía
también el original en VB.NET (esos "%COMPUTERNAME%" quedaban como texto
fijo dentro del string de Arguments, sin ninguna expansión de VB.NET de por
medio): es LTPGUI32.exe / LTPHPS32.exe quien expande esa variable de
entorno al arrancar, no el acceso directo ni quien lo crea.
"""
from __future__ import annotations

from pathlib import Path

# Carpeta del escritorio público -- visible para cualquier usuario del
# equipo, sin importar con qué cuenta se inició sesión (a diferencia de
# `objShell.SpecialFolders("Desktop")` en el original, que apunta al
# escritorio del usuario actual; los accesos directos en sí se crean
# siempre en Public Desktop, igual que hacía el VB.NET original).
PUBLIC_DESKTOP = Path(r"C:\Users\Public\Desktop")

# Carpeta donde viven los ejecutables de Shares una vez instalado.
LTP_DIR = Path(r"C:\LTP")

# Definición de los 2 accesos directos, en el mismo orden y con los mismos
# valores que el código VB.NET original (CreateShortCut / CreateShortCutHPGUI).
_SHORTCUT_DEFS = [
    {
        "filename": "LTP SHARES.lnk",
        "description": "LTPGUI32",
        "target": LTP_DIR / "LTPGUI32.exe",
        "arguments": lambda ciudad: f" /ACM /CC{ciudad} /W%COMPUTERNAME% /SU%COMPUTERNAME%",
    },
    {
        "filename": "LiteGUI.lnk",
        "description": "LTPGUI32",
        "target": LTP_DIR / "LTPHPS32.exe",
        "arguments": lambda ciudad: f" /ACM /W%COMPUTERNAME% /SU%COMPUTERNAME% /CC{ciudad}",
    },
]


class ShortcutError(Exception):
    """Error esperado al crear un acceso directo (ej. no se pudo invocar
    COM, ruta inválida). El mensaje ya viene listo para mostrárselo tal
    cual al técnico."""


def _create_shortcut(
    shortcut_path: Path,
    target_path: Path,
    arguments: str,
    description: str,
    working_directory: Path,
    window_style: int = 1,
) -> None:
    """Crea UN acceso directo (.lnk) vía COM (`WScript.Shell`), igual que
    hacía el VB.NET original. Import perezoso de `win32com.client` -- ese
    módulo (parte de `pywin32`) solo existe en Windows, y esta app se
    desarrolla y prueba en Linux/Mac; importarlo recién adentro de la
    función (en vez de al tope del archivo) permite que el resto del
    módulo se pueda importar y probar sin pywin32 instalado, mockeando
    esta función directamente en los tests."""
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.Arguments = arguments
    shortcut.Description = description
    shortcut.WorkingDirectory = str(working_directory)
    shortcut.WindowStyle = window_style
    shortcut.Save()


def create_ltp_shares_shortcuts(ciudad: str, public_desktop: Path = PUBLIC_DESKTOP) -> str:
    """Crea los 2 accesos directos de Shares ("LTP SHARES" y "LiteGUI") en
    `public_desktop` (por defecto `C:\\Users\\Public\\Desktop`), con el
    valor de CIUDAD ya resuelto en sus argumentos.

    Devuelve un mensaje corto de éxito para el estado de la pantalla.
    Lanza `ShortcutError` si algo falla -- el llamador decide cómo
    mostrarlo (igual que el resto de errores de esta pantalla)."""
    ciudad = (ciudad or "").strip()
    if not ciudad:
        raise ShortcutError(
            "El campo CIUDAD está vacío -- hace falta un valor para armar los accesos directos de Shares."
        )

    created: list[str] = []
    for shortcut_def in _SHORTCUT_DEFS:
        shortcut_path = Path(public_desktop) / shortcut_def["filename"]
        try:
            _create_shortcut(
                shortcut_path=shortcut_path,
                target_path=shortcut_def["target"],
                arguments=shortcut_def["arguments"](ciudad),
                description=shortcut_def["description"],
                working_directory=LTP_DIR,
            )
        except Exception as exc:  # COM puede lanzar varios tipos de error distintos
            raise ShortcutError(f"No se pudo crear el acceso directo '{shortcut_path}': {exc}") from exc
        created.append(str(shortcut_path))

    return f"Accesos directos creados: {', '.join(created)}"
