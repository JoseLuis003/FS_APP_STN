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

import shutil
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


def _copy_fonts(fonts_src_dir: Path = FONTS_SRC_DIR, fonts_dst_dir: Path = WINDOWS_FONTS_DIR) -> str:
    """Paso 2 del .bat: copia `*.fon` y `*.ttf` desde `fonts_src_dir` (ya
    instaladas ahí por el .msi de Shares 5.0) a `fonts_dst_dir`. Lanza
    `SharesSetupError` si `fonts_src_dir` no existe -- si no hay ningún
    archivo `.fon`/`.ttf` adentro, no es un error (nada que copiar)."""
    if not fonts_src_dir.exists():
        raise SharesSetupError(f"No se encontró la carpeta de fuentes: {fonts_src_dir}")

    copied: list[str] = []
    for pattern in ("*.fon", "*.ttf"):
        for font_file in sorted(fonts_src_dir.glob(pattern)):
            try:
                shutil.copy(font_file, fonts_dst_dir / font_file.name)
            except OSError as exc:
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


def run_ltp_shares_post_install() -> str:
    """Corre los 5 pasos de arriba en orden, uno detrás del otro -- se
    detiene en el primer paso que falle (no reintenta ni sigue con los
    siguientes), igual que cualquier secuencia de `extra_steps` del
    catálogo. Pensado para colgarse como paso `installer_type: "python"`
    del ítem `shares_5_0` en `ltp_css_apps.json` (ver
    `app/installer.py`).

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
