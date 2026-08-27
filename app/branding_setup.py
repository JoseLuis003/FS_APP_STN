"""Paso "BackGround" del catálogo APPS (2da columna, id `background`),
portado de `Scripts\\IMAGEN-STN\\background.bat`. A pesar del nombre del
ítem, el `.bat` no toca el fondo de pantalla del escritorio -- deja
configurado BGInfo (el resumen de datos del equipo que aparece superpuesto
sobre el escritorio) y la imagen de la pantalla de bloqueo (lock screen)
con el branding de Copa. En el mismo orden que el `.bat` original:

1. Copia `CMINFO.bgi` (la plantilla de BGInfo) a `C:\\Windows\\BGINFO\\`
   (crea la carpeta si no existe).
2. Marca el EULA de BGInfo como aceptado
   (`HKCU\\Software\\Sysinternals\\BGInfo` -> `EulaAccepted=1`), para que
   no muestre el diálogo de aceptación la primera vez que corre.
3. Registra `bginfo.exe` para que arranque con Windows
   (`HKLM\\...\\CurrentVersion\\Run` -> `CMINFO=...`), con la misma línea
   de comandos que el `.bat` original (`/TIMER:0 /SILENT /NOLICPROMPT`).
4. Da control total (Everyone) a `C:\\Windows\\BGINFO`, igual que hacía
   `icacls` en el `.bat` original.
5. Copia `lockscreen.jpg` a `C:\\Windows\\Web\\Screen\\`.
6. Configura esa imagen como pantalla de bloqueo vía las 3 claves de
   `PersonalizationCSP` que ya usaba el `.bat` original.

A diferencia del `.bat` original (que no revisaba el código de salida de
ninguno de sus pasos), acá cualquier paso que falle (archivo de origen
faltante, `icacls` con código de salida distinto de 0, etc.) lanza
`BrandingSetupError` y detiene el resto de la cola -- mismo criterio que
el resto de esta app."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Nombres/rutas de los 2 archivos que trae la carpeta de instaladores
# (junto al propio `background.bat`), relativos a `installers_base_path`.
SOURCE_DIR_REL = r"Scripts\IMAGEN-STN"
BGINFO_TEMPLATE_NAME = "CMINFO.bgi"
LOCKSCREEN_IMAGE_NAME = "lockscreen.jpg"

# Carpeta destino de BGInfo -- creada por este mismo paso si no existe.
BGINFO_DIR = Path(r"C:\Windows\BGINFO")

# Carpeta destino de la imagen de pantalla de bloqueo -- ya existe de
# fábrica en Windows, pero se crea igual por las dudas (ver `_copy_file`).
LOCKSCREEN_DIR = Path(r"C:\Windows\Web\Screen")

_TIMEOUT_SECONDS = 60

# Evita que Windows le abra su propia ventana de consola a cada comando
# que corre `_run_checked()` (quedaría en blanco y parecería colgado)
# -- ver la explicación completa en `NO_CONSOLE_WINDOW`,
# `app/installer.py`.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class BrandingSetupError(Exception):
    """Error esperado al aplicar el paso "BackGround" (BGInfo + pantalla
    de bloqueo). El mensaje ya viene listo para mostrárselo tal cual al
    técnico."""


def _run_checked(cmd: list[str], step_label: str) -> None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, creationflags=_NO_CONSOLE_WINDOW
        )
    except subprocess.TimeoutExpired:
        raise BrandingSetupError(f"{step_label}: tiempo de espera agotado.")
    except OSError as exc:
        raise BrandingSetupError(f"{step_label}: no se pudo ejecutar -- {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"{step_label}: terminó con código de salida {result.returncode}"
        if detail:
            msg += f" -- {detail}"
        raise BrandingSetupError(msg)


def _copy_file(src: Path, dst_dir: Path, step_label: str) -> Path:
    if not src.exists():
        raise BrandingSetupError(f"{step_label}: no se encontró '{src}'.")
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_file = dst_dir / src.name
    try:
        shutil.copy2(src, dst_file)
    except OSError as exc:
        raise BrandingSetupError(f"{step_label}: no se pudo copiar '{src}' a '{dst_file}': {exc}")
    return dst_file


def _reg_add(key: str, value_name: str, value_type: str, data: str, step_label: str) -> None:
    _run_checked(["reg", "add", key, "/v", value_name, "/t", value_type, "/d", data, "/f"], step_label)


def apply_branding_setup(installers_base_path: str, bginfo_dir: Path = BGINFO_DIR, lockscreen_dir: Path = LOCKSCREEN_DIR) -> str:
    """Corre los 6 pasos de arriba en orden, uno detrás del otro -- se
    detiene en el primero que falle. Pensado para colgarse como paso
    `installer_type: "python"` del ítem `background` en `apps.json` (ver
    `app/installer.py`).

    Devuelve un mensaje corto de éxito con el detalle de cada paso, listo
    para mostrar en el estado de la pantalla. Lanza `BrandingSetupError`
    si algún paso falla."""
    source_dir = Path(installers_base_path) / SOURCE_DIR_REL

    bgi_dst = _copy_file(source_dir / BGINFO_TEMPLATE_NAME, bginfo_dir, "copiar CMINFO.bgi")

    _reg_add(
        r"HKCU\Software\Sysinternals\BGInfo",
        "EulaAccepted",
        "REG_DWORD",
        "1",
        "reg add EulaAccepted",
    )

    bginfo_exe = bginfo_dir / "bginfo.exe"
    run_command = f'"{bginfo_exe}" "{bgi_dst}" /TIMER:0 /SILENT /NOLICPROMPT'
    _reg_add(
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "CMINFO",
        "REG_SZ",
        run_command,
        "reg add CMINFO (autorun)",
    )

    _run_checked(["icacls", str(bginfo_dir), "/grant", "Everyone:(OI)(CI)F"], "icacls BGINFO")

    lockscreen_dst = _copy_file(source_dir / LOCKSCREEN_IMAGE_NAME, lockscreen_dir, "copiar lockscreen.jpg")

    _reg_add(
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP",
        "LockScreenImageStatus",
        "REG_DWORD",
        "0",
        "reg add LockScreenImageStatus",
    )
    _reg_add(
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP",
        "LockScreenImagePath",
        "REG_SZ",
        str(lockscreen_dst),
        "reg add LockScreenImagePath",
    )
    _reg_add(
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP",
        "LockScreenImageUrl",
        "REG_SZ",
        str(lockscreen_dst),
        "reg add LockScreenImageUrl",
    )

    return (
        f"BGInfo instalado en {bginfo_dir} (plantilla {bgi_dst.name}); "
        f"pantalla de bloqueo configurada con {lockscreen_dst}"
    )


# --------------------------------------------------------------------------
# Paso extra de "BGInfo" del catálogo APPS (1ra columna, id `bginfo`),
# portado de `BGinfo\bginfo.bat`. A diferencia de `apply_branding_setup()`
# arriba (que copia sus propios archivos porque nada más lo hace),
# `BGinfo/BGTool.exe` -- el instalador principal del ítem `bginfo` -- ya
# deja `bginfo.exe` y `CMINFO.BGI` copiados en `C:\Windows\BGINFO` por su
# cuenta; este paso solo necesita las mismas 2 claves de registro que
# `apply_branding_setup()` (EulaAccepted + autorun), con una línea de
# comandos más simple (`/timer:0`, sin `/SILENT /NOLICPROMPT`).
# --------------------------------------------------------------------------

# El .bat original usa el nombre en mayúsculas ("CMINFO.BGI") -- Windows no
# distingue mayúsculas/minúsculas, pero se preserva tal cual por fidelidad.
BGINFO_STANDALONE_TEMPLATE_NAME = "CMINFO.BGI"


def apply_bginfo_registration(installers_base_path: str = "", bginfo_dir: Path = BGINFO_DIR) -> str:
    """Corre las 2 claves de registro de `bginfo.bat` (paso extra del
    ítem `bginfo`, DESPUÉS de que `BGinfo/BGTool.exe` ya copió
    `bginfo.exe`/`CMINFO.BGI` a `bginfo_dir`). No copia ningún archivo ni
    toca permisos -- a diferencia de `apply_branding_setup()`, eso ya lo
    hizo el propio instalador principal de este ítem.

    `installers_base_path` se recibe (y se ignora) solo porque
    `InstallWorker` le pasa ese argumento a TODO paso `installer_type:
    "python"` por igual (ver `app/installer.py`) -- este paso no depende
    de la carpeta de instaladores, ya que opera sobre `bginfo_dir` (una
    ruta fija del equipo).

    Lanza `BrandingSetupError` si algún `reg add` falla."""
    _reg_add(
        r"HKCU\Software\Sysinternals\BGInfo",
        "EulaAccepted",
        "REG_DWORD",
        "1",
        "reg add EulaAccepted",
    )

    bginfo_exe = bginfo_dir / "bginfo.exe"
    bgi_file = bginfo_dir / BGINFO_STANDALONE_TEMPLATE_NAME
    run_command = f'"{bginfo_exe}" "{bgi_file}" /timer:0'
    _reg_add(
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "CMINFO",
        "REG_SZ",
        run_command,
        "reg add CMINFO (autorun)",
    )

    return f"BGInfo registrado para iniciar con Windows ({run_command})"
