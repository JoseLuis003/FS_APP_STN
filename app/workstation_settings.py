"""Paso "AJUSTES NECESARIOS" del catálogo APPS (2da columna, id
`ajustes_necesarios`), portado de `Scripts\\AJUSTES_NECESARIOS.bat`.

El `.bat` original tiene 2 partes bien distintas:

1. Un primer bloque (~40 líneas) que edita un montón de claves de
   registro bajo prefijos `HKLM\\TK_DEFAULT`, `HKLM\\TK_NTUSER`,
   `HKLM\\TK_SOFTWARE` y `HKLM\\TK_SYSTEM` (deshabilitando Windows
   Defender, Cortana e historial de búsqueda). Esos hives "TK_" NO
   existen en una sesión normal de Windows a menos que algo los haya
   montado antes con `reg load` -- y este `.bat` nunca hace eso -- así
   que, tal como está, esas ~40 líneas casi seguro fallaban en silencio
   (el `>nul 2>&1` al final de cada línea oculta el error) y nunca
   llegaron a aplicar nada. Confirmado con el técnico: se trata como
   código muerto y NO se porta a Python.
2. El resto del `.bat` (lo que sí porta este módulo), con 2 tipos de
   pasos:

   - **Ajustes de preferencia** (Chrome, Edge, SysMain, apps en 2do
     plano, transparencia del taskbar, IPv6, Delivery Optimization): se
     aplican en modo "mejor esfuerzo" -- si alguno falla (por ejemplo, un
     servicio que no existe en esa edición de Windows), se registra en el
     detalle de retorno y se sigue con el resto, sin detener la acción
     completa. Igual que hacía el `.bat` original (que nunca revisaba el
     código de salida de ninguno de estos).
   - **Pasos críticos** (copiar las fotos de cuenta de usuario, importar
     la política local con `LGPO.exe`): a diferencia del resto, estos SÍ
     detienen la acción y lanzan `WorkstationSettingsError` si fallan --
     son la parte que de verdad configura algo (no una preferencia de
     "mejor esfuerzo" sin impacto real si no se aplica).

Los `PING -n 5 127.0.0.1` que el `.bat` original intercalaba entre
bloques (una espera de ~4 segundos, probablemente para darle tiempo a
alguna directiva de grupo a asentarse) no se replican acá -- cada `reg
add`/`sc` es síncrono y no depende de ese tiempo de espera artificial."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Carpeta de instaladores (relativa a `installers_base_path`) donde viven
# los recursos propios de Copa que usa este paso -- la misma carpeta
# "Copaair" que también usa "Shortcuts" (`app/shortcuts.py`).
COPAAIR_SOURCE_REL = r"Scripts\Copaair"

# Fotos de cuenta de usuario que trae esa carpeta, en el mismo orden que
# el .bat original.
ACCOUNT_PICTURE_NAMES = [
    "user.png",
    "user-32.png",
    "user-40.png",
    "user-48.png",
    "user-192.png",
]
ACCOUNT_PICTURES_DEST_DIR = Path(r"C:\ProgramData\Microsoft\User Account Pictures")

# LGPO.exe (Local Group Policy Object Utility, de Microsoft) y la carpeta
# de política local que importa -- ambos dentro de la misma carpeta
# "Copaair".
LGPO_EXE_NAME = "LGPO.exe"
LGPO_BACKUP_SUBDIR = "LocalGPO"

_TIMEOUT_SECONDS = 60
_LGPO_TIMEOUT_SECONDS = 5 * 60

# Evita que Windows le abra su propia ventana de consola a cada comando
# que corre `_run()` (quedaría en blanco y parecería colgado) -- ver la
# explicación completa en `NO_CONSOLE_WINDOW`, `app/installer.py`.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class WorkstationSettingsError(Exception):
    """Error esperado en uno de los pasos CRÍTICOS de "AJUSTES NECESARIOS"
    (copiar las fotos de cuenta, importar la política local con
    `LGPO.exe`). El mensaje ya viene listo para mostrárselo tal cual al
    técnico. Los ajustes de preferencia (Chrome/Edge/SysMain/etc.) NUNCA
    lanzan esto -- son "mejor esfuerzo", ver docstring del módulo."""


def _run(cmd: list[str], timeout: int = _TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Corre `cmd` y devuelve el `CompletedProcess` tal cual, sin lanzar
    nada -- lo interpreta cada llamador según si ese paso es "mejor
    esfuerzo" o crítico (ver `_apply_best_effort` vs los pasos críticos
    más abajo, que sí revisan el resultado)."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NO_CONSOLE_WINDOW)


def _describe_failure(result: subprocess.CompletedProcess) -> str:
    detail = (result.stderr or result.stdout or "").strip()[:300]
    msg = f"código de salida {result.returncode}"
    if detail:
        msg += f" -- {detail}"
    return msg


def _apply_best_effort(label: str, cmd: list[str], results: list[str]) -> None:
    """Corre `cmd` en modo "mejor esfuerzo": el resultado (OK u omitido,
    con el motivo) se agrega a `results`, pero nunca se lanza una
    excepción -- un ajuste de preferencia que no aplica en este equipo
    (ej. un servicio que no existe en esta edición de Windows) no debe
    frenar el resto de la acción."""
    try:
        result = _run(cmd)
    except subprocess.TimeoutExpired:
        results.append(f"{label}: omitido (tiempo de espera agotado)")
        return
    except OSError as exc:
        results.append(f"{label}: omitido (no se pudo ejecutar -- {exc})")
        return

    if result.returncode != 0:
        results.append(f"{label}: omitido ({_describe_failure(result)})")
    else:
        results.append(f"{label}: OK")


def _reg_add_cmd(key: str, value_name: str, value_type: str, data: str) -> list[str]:
    return ["reg", "add", key, "/v", value_name, "/t", value_type, "/d", data, "/f"]


def apply_preference_tweaks() -> list[str]:
    """Aplica los ajustes de preferencia del `.bat` (Chrome, Edge, SysMain,
    apps en 2do plano, transparencia, IPv6, Delivery Optimization), todos
    en modo "mejor esfuerzo" -- ver docstring del módulo. Devuelve el
    detalle de cada uno (aplicado u omitido), nunca lanza una excepción."""
    results: list[str] = []

    _apply_best_effort(
        "Chrome: BackgroundModeEnabled",
        _reg_add_cmd(r"HKLM\SOFTWARE\Policies\Google\Chrome", "BackgroundModeEnabled", "REG_DWORD", "0"),
        results,
    )
    _apply_best_effort(
        "Chrome: HardwareAccelerationModeEnabled",
        _reg_add_cmd(r"HKLM\SOFTWARE\Policies\Google\Chrome", "HardwareAccelerationModeEnabled", "REG_DWORD", "0"),
        results,
    )
    _apply_best_effort(
        "Edge: BackgroundModeEnabled",
        _reg_add_cmd(r"HKLM\SOFTWARE\Policies\Microsoft\Edge", "BackgroundModeEnabled", "REG_DWORD", "0"),
        results,
    )
    _apply_best_effort(
        "Edge: HardwareAccelerationModeEnabled",
        _reg_add_cmd(r"HKLM\SOFTWARE\Policies\Microsoft\Edge", "HardwareAccelerationModeEnabled", "REG_DWORD", "0"),
        results,
    )
    _apply_best_effort(
        "Edge: StartupBoostEnabled",
        _reg_add_cmd(r"HKLM\SOFTWARE\Policies\Microsoft\Edge", "StartupBoostEnabled", "REG_DWORD", "0"),
        results,
    )
    _apply_best_effort("SysMain: detener servicio", ["sc", "stop", "SysMain"], results)
    _apply_best_effort("SysMain: deshabilitar arranque", ["sc", "config", "SysMain", "start=", "disabled"], results)
    _apply_best_effort(
        "Apps en 2do plano: LetAppsRunInBackground",
        _reg_add_cmd(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsRunInBackground", "REG_DWORD", "2"),
        results,
    )
    _apply_best_effort(
        "Transparencia de la barra de tareas: desactivar",
        _reg_add_cmd(
            r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
            "UseOLEDTaskbarTransparency",
            "REG_DWORD",
            "0",
        ),
        results,
    )
    _apply_best_effort(
        "IPv6: deshabilitar componentes",
        _reg_add_cmd(r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents", "REG_DWORD", "255"),
        results,
    )
    _apply_best_effort(
        "Delivery Optimization: modo de descarga",
        _reg_add_cmd(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization", "DODownloadMode", "REG_DWORD", "0"),
        results,
    )
    return results


def copy_account_pictures(
    installers_base_path: str,
    dest_dir: Path = ACCOUNT_PICTURES_DEST_DIR,
) -> str:
    """Paso CRÍTICO: copia las 5 fotos de cuenta de usuario
    (`ACCOUNT_PICTURE_NAMES`) desde la carpeta "Copaair" a `dest_dir` (por
    defecto `C:\\ProgramData\\Microsoft\\User Account Pictures`). Lanza
    `WorkstationSettingsError` si la carpeta de origen o alguna de las 5
    fotos no aparece donde se espera."""
    source_dir = Path(installers_base_path) / COPAAIR_SOURCE_REL
    if not source_dir.exists():
        raise WorkstationSettingsError(f"No se encontró la carpeta '{source_dir}'.")

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for name in ACCOUNT_PICTURE_NAMES:
        source_file = source_dir / name
        if not source_file.exists():
            raise WorkstationSettingsError(f"No se encontró la foto de cuenta '{source_file}'.")
        try:
            shutil.copy2(source_file, dest_dir / name)
        except OSError as exc:
            raise WorkstationSettingsError(f"No se pudo copiar '{source_file}' a '{dest_dir}': {exc}")
        copied.append(name)

    return f"{len(copied)} foto(s) de cuenta copiadas a {dest_dir}"


def apply_local_gpo(installers_base_path: str, timeout: int = _LGPO_TIMEOUT_SECONDS) -> str:
    """Paso CRÍTICO: corre `LGPO.exe /g <LocalGPO>` (la carpeta de
    política local que importa, ambos dentro de "Copaair") -- es la
    herramienta oficial de Microsoft para aplicar un backup de política
    de grupo local. Lanza `WorkstationSettingsError` si `LGPO.exe` o la
    carpeta de backup no aparecen donde se espera, se agota el tiempo de
    espera, o termina con un código de salida distinto de 0."""
    source_dir = Path(installers_base_path) / COPAAIR_SOURCE_REL
    lgpo_exe = source_dir / LGPO_EXE_NAME
    lgpo_backup_dir = source_dir / LGPO_BACKUP_SUBDIR

    if not lgpo_exe.exists():
        raise WorkstationSettingsError(f"No se encontró '{lgpo_exe}'.")
    if not lgpo_backup_dir.exists():
        raise WorkstationSettingsError(f"No se encontró la carpeta de política local '{lgpo_backup_dir}'.")

    try:
        result = _run([str(lgpo_exe), "/g", str(lgpo_backup_dir)], timeout=timeout)
    except subprocess.TimeoutExpired:
        raise WorkstationSettingsError(f"Tiempo de espera agotado ({timeout // 60} min) ejecutando '{lgpo_exe}'.")
    except OSError as exc:
        raise WorkstationSettingsError(f"No se pudo ejecutar '{lgpo_exe}': {exc}")

    if result.returncode != 0:
        raise WorkstationSettingsError(f"'{lgpo_exe}' terminó con {_describe_failure(result)}")

    return f"política local importada desde {lgpo_backup_dir}"


def apply_workstation_settings(installers_base_path: str) -> str:
    """Corre los ajustes de preferencia (mejor esfuerzo) y después los 2
    pasos críticos, en ese orden -- pensado para colgarse como paso
    `installer_type: "python"` del ítem `ajustes_necesarios` en
    `apps.json` (ver `app/installer.py`).

    Devuelve un mensaje con el detalle de cada ajuste de preferencia
    (aplicado u omitido) y de los 2 pasos críticos. Lanza
    `WorkstationSettingsError` si copiar las fotos de cuenta o importar la
    política local fallan -- los ajustes de preferencia nunca lo hacen."""
    preference_details = apply_preference_tweaks()
    pictures_detail = copy_account_pictures(installers_base_path)
    gpo_detail = apply_local_gpo(installers_base_path)

    return "; ".join(preference_details + [pictures_detail, gpo_detail])
