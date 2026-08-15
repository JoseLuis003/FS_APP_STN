"""Pasos posteriores a instalar Shares 5.0 (ítem `shares_5_0` del catálogo
LTP / CSS), portados a Python desde el `.bat` que ya se usaba a mano
("LTP setting.bat"). A diferencia de `app/shares_config_apply.py` (que
depende de los valores de CIUDAD/HOSTNAME que carga el técnico en el panel)
y de `app/shortcuts.py` (que se corre después de aplicar esa configuración),
esto corre automáticamente como un paso más de la cola de instalación,
justo después del `.msi` de Shares 5.0 -- no depende de ningún campo del
panel.

En el mismo orden que el `.bat` original:

1. Da control total (Everyone) a `C:\\LTP`, recursivo -- `icacls ... /grant
   Everyone:(OI)(CI)F`.
2. Copia las fuentes que necesita Shares (`*.fon`, `*.ttf`) desde
   `C:\\LTP\\Fonts` (donde ya las deja el `.msi`) a `C:\\Windows\\Fonts`.
   Esta copia se hace con la función nativa de Windows `CopyFileW`
   (`kernel32.dll`, vía `ctypes`) y no con `shutil.copy` -- en un equipo
   real con Windows 11 se confirmó que `shutil.copy` (que abre origen y
   destino a través de la capa de E/S de Python) puede fallar con
   `OSError: [Errno 22] Invalid argument` justo al copiar hacia
   `C:\\Windows\\Fonts` (carpeta especial de Shell), mientras que la copia
   nativa de Windows -- el mismo mecanismo de fondo que usaba el `copy` de
   CMD en el `.bat` original, y que sigue funcionando sin problema -- no
   tiene ese problema. Ver `_win32_copy_file()` más abajo. Si la fuente ya
   estaba copiada (misma fuente, mismo tamaño -- por ejemplo, al
   reintentar la instalación en un equipo ya configurado antes), no se
   vuelve a copiar: además de ser innecesario, Windows puede tener esa
   fuente ya cargada/mapeada como fuente activa del sistema, y en ese
   estado `CopyFileW` no puede sobrescribirla (`WinError 1224`, visto en
   un equipo real).
3. Importa `C:\\LTP\\Fonts\\ALCFONXP.REG` con `regedit /s` (registra esas
   fuentes en el sistema).
4. Borra el acceso directo que el propio instalador de Shares deja en el
   escritorio del usuario actual ("Shares LTPGUI32.exe.lnk") -- a
   diferencia de los pasos anteriores, si no existe no es un error (es
   limpieza best-effort, igual que el `Del` del `.bat` original, que
   tampoco frena el resto del script si el archivo no está).
5. Registra (desregistra y vuelve a registrar) los 5 controles OCX que usa
   Shares: COMCTL32, mscomctl, comdlg32, msadodc y tabctl32, todos dentro
   de `C:\\LTP`.

Si cualquiera de los pasos 1, 2, 3 o 5 falla (o falta un archivo que
debería estar ahí), se lanza `SharesSetupError` y el resto de la cola de
instalación se detiene ahí, igual que con cualquier otro paso del catálogo
que falla -- ver `app/installer.py` (`installer_type: "python"`,
`_PYTHON_STEP_HANDLERS`)."""
from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path

# Carpeta donde el .msi de Shares 5.0 deja todo instalado.
LTP_DIR = Path(r"C:\LTP")

# Carpeta con las fuentes y el .REG que trae el propio instalador de Shares.
FONTS_SRC_DIR = LTP_DIR / "Fonts"

# Carpeta de fuentes del sistema -- destino de la copia (ver docstring del
# módulo: "%WINDIWR%" en el .bat original era un typo de "%WINDIR%").
WINDOWS_FONTS_DIR = Path(r"C:\Windows\Fonts")

# Archivo de registro que registra esas fuentes en Windows.
FONT_REG_FILE = FONTS_SRC_DIR / "ALCFONXP.REG"

# Acceso directo que deja el propio instalador de Shares en el escritorio
# del usuario actual, y que hay que limpiar (no es un error si ya no está).
STALE_SHORTCUT_NAME = "Shares LTPGUI32.exe.lnk"

# Controles OCX que usa Shares, en el mismo orden que el .bat original.
# Todos viven directo dentro de C:\LTP.
OCX_FILES = [
    "COMCTL32.OCX",
    "mscomctl.ocx",
    "comdlg32.ocx",
    "msadodc.ocx",
    "tabctl32.ocx",
]


class SharesSetupError(Exception):
    """Error esperado en alguno de los pasos posteriores a instalar
    Shares 5.0. El mensaje ya viene listo para mostrárselo tal cual al
    técnico."""


def _run_checked(cmd: list[str], step_label: str) -> subprocess.CompletedProcess:
    """Corre `cmd` y lanza `SharesSetupError` si no se pudo ejecutar, se
    agotó el tiempo de espera, o terminó con código de salida distinto de
    0. Común a los 3 pasos de este módulo que invocan una herramienta de
    línea de comandos (icacls, regedit, regsvr32)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5 * 60)
    except subprocess.TimeoutExpired:
        raise SharesSetupError(f"{step_label}: tiempo de espera agotado (5 min).")
    except OSError as exc:
        raise SharesSetupError(f"{step_label}: no se pudo ejecutar -- {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"{step_label}: terminó con código de salida {result.returncode}"
        if detail:
            msg += f" -- {detail}"
        raise SharesSetupError(msg)
    return result


def _grant_full_control(ltp_dir: Path = LTP_DIR) -> str:
    """Paso 1 del .bat: `icacls C:\\LTP /grant Everyone:(OI)(CI)F`."""
    _run_checked(["icacls", str(ltp_dir), "/grant", "Everyone:(OI)(CI)F"], "icacls")
    return f"permisos Everyone en {ltp_dir}"


def _win32_copy_file(src: Path, dst: Path) -> None:
    """Copia `src` a `dst` con la función nativa de Windows `CopyFileW`
    (`kernel32.dll`, vía `ctypes`) en vez de `shutil.copy`.

    Motivo: en un equipo real con Windows 11 se confirmó que
    `shutil.copy` -- que abre origen y destino a través de la capa de E/S
    de Python -- puede fallar con `OSError: [Errno 22] Invalid argument`
    específicamente al copiar hacia la carpeta especial `C:\\Windows\\Fonts`.
    El `.bat` original nunca tuvo ese problema porque usaba el `copy` de
    CMD, que -- igual que Explorer, xcopy o robocopy -- por debajo llama a
    esta misma función de la API de Win32. Llamar a `CopyFileW`
    directamente evita el problema en vez de solo intentar sortearlo con
    otro mecanismo que tenga la misma limitación."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CopyFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_bool]
    kernel32.CopyFileW.restype = ctypes.c_bool
    if not kernel32.CopyFileW(str(src), str(dst), False):
        raise ctypes.WinError()


# Códigos de error de Windows que CopyFileW puede devolver cuando el
# archivo destino ya existe y ya está en uso por el propio sistema como
# fuente activa -- ver el segundo `except` de `_copy_fonts()` más abajo.
#
# - 1224 (ERROR_USER_MAPPED_FILE): el archivo ya está mapeado en memoria
#   -- típico de una fuente propia (ej. ALCFONT.FON) que este mismo paso
#   ya instaló en una corrida anterior sobre el mismo equipo.
# - 32 (ERROR_SHARING_VIOLATION): "The process cannot access the file
#   because it is being used by another process" -- visto en un equipo
#   real al copiar ARIALN.TTF (Arial Narrow), una fuente que Windows 11 ya
#   trae instalada de fábrica con ese mismo nombre de archivo; al ser una
#   fuente del sistema en uso constante por GDI/DirectWrite, Windows la
#   mantiene bloqueada de forma mucho más agresiva que una fuente propia
#   poco usada como ALCFONT.FON, por eso da este otro código en vez de
#   1224.
#
# En ambos casos el archivo ya existe y Windows ya lo está usando como
# fuente -- en la práctica, la fuente ya está "instalada" (sea la nuestra
# o una del propio Windows con el mismo nombre), así que no tiene sentido
# frenar toda la instalación por esto.
ERROR_USER_MAPPED_FILE = 1224
ERROR_SHARING_VIOLATION = 32
_FONT_IN_USE_WINERRORS = (ERROR_USER_MAPPED_FILE, ERROR_SHARING_VIOLATION)


def _copy_fonts(fonts_src_dir: Path = FONTS_SRC_DIR, fonts_dst_dir: Path = WINDOWS_FONTS_DIR) -> str:
    """Paso 2 del .bat: copia `*.fon` y `*.ttf` desde `fonts_src_dir` (ya
    instaladas ahí por el .msi de Shares 5.0) a `fonts_dst_dir`, usando
    `_win32_copy_file()` (ver su docstring: no se usa `shutil.copy` porque
    falla con Errno 22 al copiar hacia `C:\\Windows\\Fonts` en Windows 11).
    Lanza `SharesSetupError` si `fonts_src_dir` no existe -- si no hay
    ningún archivo `.fon`/`.ttf` adentro, no es un error (nada que
    copiar).

    Si una fuente ya está copiada en `fonts_dst_dir` con el mismo tamaño
    que la de origen, no se vuelve a copiar -- se asume ya instalada (esto
    es lo normal al correr este paso más de una vez sobre el mismo
    equipo, por ejemplo al reintentar una instalación). Esto también evita
    de raíz un problema real visto en equipos con Windows 11: si el
    archivo destino ya existe, Windows puede tenerlo en uso como fuente
    activa del sistema, y `CopyFileW` no puede sobrescribir un archivo en
    ese estado -- devuelve `WinError 1224` o `WinError 32` según el caso
    (ver `_FONT_IN_USE_WINERRORS` arriba). Como red de seguridad adicional,
    si aun así se intenta copiar (por ejemplo, porque el tamaño no
    coincide -- como pasó con ARIALN.TTF, donde Windows ya traía su propia
    versión con un tamaño distinto) y Windows devuelve justo uno de esos
    errores, se trata como "ya estaba instalada" en vez de como una falla
    real."""
    if not fonts_src_dir.exists():
        raise SharesSetupError(f"No se encontró la carpeta de fuentes: {fonts_src_dir}")

    copied: list[str] = []
    for pattern in ("*.fon", "*.ttf"):
        for font_file in sorted(fonts_src_dir.glob(pattern)):
            dst_file = fonts_dst_dir / font_file.name
            if dst_file.exists() and dst_file.stat().st_size == font_file.stat().st_size:
                copied.append(font_file.name)
                continue
            try:
                _win32_copy_file(font_file, dst_file)
            except OSError as exc:
                if getattr(exc, "winerror", None) in _FONT_IN_USE_WINERRORS and dst_file.exists():
                    copied.append(font_file.name)
                    continue
                raise SharesSetupError(f"No se pudo copiar la fuente '{font_file}': {exc}")
            copied.append(font_file.name)

    return f"{len(copied)} fuente(s) copiadas a {fonts_dst_dir}" if copied else f"sin fuentes que copiar en {fonts_src_dir}"


def _import_font_registry(reg_file: Path = FONT_REG_FILE) -> str:
    """Paso 3 del .bat: `regedit /s C:\\LTP\\Fonts\\ALCFONXP.REG` (registra
    las fuentes copiadas en el paso anterior)."""
    if not reg_file.exists():
        raise SharesSetupError(f"No se encontró el archivo de registro: {reg_file}")
    _run_checked(["regedit", "/s", str(reg_file)], "regedit")
    return f"registro importado desde {reg_file}"


def _remove_stale_shortcut(shortcut_name: str = STALE_SHORTCUT_NAME) -> str:
    """Paso 4 del .bat: borra el acceso directo que deja el propio
    instalador de Shares en el escritorio del usuario actual. A diferencia
    del resto de los pasos de este módulo, que si fallan detienen la cola,
    esto es limpieza best-effort -- si el archivo ya no está, no pasa
    nada (igual que el `Del` del .bat original)."""
    shortcut_path = Path.home() / "Desktop" / shortcut_name
    try:
        shortcut_path.unlink(missing_ok=True)
    except OSError as exc:
        raise SharesSetupError(f"No se pudo borrar el acceso directo '{shortcut_path}': {exc}")
    return f"acceso directo previo eliminado (o ya no estaba): {shortcut_path}"


def _register_ocx_files(ltp_dir: Path = LTP_DIR, ocx_files: list[str] = OCX_FILES) -> str:
    """Paso 5 del .bat: desregistra y vuelve a registrar cada OCX de la
    lista (todos dentro de `ltp_dir`), con `regsvr32 /u /s` y `regsvr32 /s`
    -- mismo orden que el original."""
    for ocx_name in ocx_files:
        ocx_path = ltp_dir / ocx_name
        if not ocx_path.exists():
            raise SharesSetupError(f"No se encontró el control OCX: {ocx_path}")
        _run_checked(["regsvr32", "/u", "/s", str(ocx_path)], f"regsvr32 /u ({ocx_name})")
        _run_checked(["regsvr32", "/s", str(ocx_path)], f"regsvr32 ({ocx_name})")
    return f"{len(ocx_files)} control(es) OCX registrados en {ltp_dir}"


def run_ltp_shares_post_install(installers_base_path: str = "") -> str:
    """Corre los 5 pasos de arriba en orden, uno detrás del otro -- se
    detiene en el primer paso que falle (no reintenta ni sigue con los
    siguientes), igual que cualquier secuencia de `extra_steps` del
    catálogo. Pensado para colgarse como paso `installer_type: "python"`
    del ítem `shares_5_0` en `ltp_css_apps.json` (ver
    `app/installer.py`).

    `installers_base_path` se recibe (y se ignora) solo porque
    `InstallWorker` le pasa ese argumento a TODO paso `installer_type:
    "python"` por igual, los use o no -- ninguno de los 5 pasos de acá
    depende de la carpeta de instaladores (todos operan sobre rutas fijas
    del equipo, C:\\LTP y C:\\Windows\\Fonts).

    Devuelve un mensaje corto de éxito con el detalle de cada paso, listo
    para mostrar en el estado de la pantalla. Lanza `SharesSetupError` si
    algún paso falla."""
    details = [
        _grant_full_control(),
        _copy_fonts(),
        _import_font_registry(),
        _remove_stale_shortcut(),
        _register_ocx_files(),
    ]
    return "; ".join(details)
