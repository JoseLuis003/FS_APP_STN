"""Ítem especial "Copa ID (Asset Tag)" (columna 1 de APPS, junto a los
demás ítems de Dell -- DELL Command Update, DELL Optimizer, DELL
OwnerTag): a diferencia de cualquier otro ítem del catálogo, éste no es
solo un checkbox -- tiene un campo de texto al lado donde el técnico
escribe (o confirma) el Asset Tag de 6 dígitos que se va a grabar en el
BIOS del equipo vía Dell Command | Configure (`cctk.exe --asset=<valor>`).

Mismo patrón que "Shares Configuracion"/"AppShell Configuracion" en LTP
/ CSS (ver `app/ui/ltp_css_window.py`): un ítem que NO pasa por el motor
de instalación genérico (`InstallWorker`) -- se saca de la cola normal
en `MainWindow._on_installar()` (ver `app/ui/main_window.py`) y se
aplica aparte, sincrónico en el hilo de la UI (no depende de ningún
otro ítem de la cola, así que no hace falta diferirlo a
`_on_queue_finished()` como sí hace falta con Shares/AppShell
Configuracion), porque necesita un valor dinámico (el texto que escribió
el técnico) que el motor genérico no tiene forma de pasarle a un
instalador.

El campo se prellena, al abrir la pantalla, con el Asset Tag que YA
tenga configurado el equipo (`detect_current_asset_tag()`, vía WMI --
reutiliza `app.report.get_asset_tag()`, la misma consulta que ya usa el
reporte de instalación: `Win32_SystemEnclosure.SMBIOSAssetTag`, sin
duplicar la lógica de WMI/PowerShell). Si el equipo no tiene ninguno
configurado, o lo que devuelve WMI no es un Asset Tag válido de 6
dígitos (por ejemplo, un equipo nuevo de fábrica trae texto genérico
como "Default string", o queda vacío), la UI deja el campo VACÍO con el
placeholder "NO SETUP" en vez de prellenarlo con un valor que de todos
modos no pasaría la validación."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.report import get_asset_tag

# Un Asset Tag válido es EXACTAMENTE 6 dígitos numéricos -- ni más ni
# menos, sin espacios ni letras (pedido explícito).
_ASSET_TAG_RE = re.compile(r"^\d{6}$")

_TIMEOUT_SECONDS = 120

# Ruta del ejecutable de Dell Command | Configure, relativa a
# `installers_base_path` (mismo criterio que el resto del catálogo: NO
# se descarga ni se asume una ruta absoluta -- tiene que venir junto a
# los demás instaladores).
_CCTK_RELATIVE_PARTS = ("Copa_ID", "cctk.exe")

# Evita que Windows le abra su propia ventana de consola a `cctk.exe`
# (quedaría en blanco y parecería colgado) -- ver la explicación
# completa en `NO_CONSOLE_WINDOW`, `app/installer.py`.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class CopaIdSetupError(Exception):
    """Error al grabar el Asset Tag vía cctk.exe. El mensaje ya viene
    listo para mostrárselo tal cual al técnico."""


def is_valid_asset_tag(value: str) -> bool:
    """Un Asset Tag válido es EXACTAMENTE 6 dígitos numéricos. Se usa
    tanto en la UI (validar antes de habilitar INSTALAR) como acá adentro
    (no confiar ciegamente en que la UI ya validó, ver
    `apply_copa_id_asset_tag`)."""
    return bool(_ASSET_TAG_RE.match((value or "").strip()))


def detect_current_asset_tag() -> str | None:
    """Devuelve el Asset Tag YA configurado en este equipo (vía WMI), o
    `None` si no hay ninguno configurado o lo que devuelve WMI no es un
    Asset Tag válido de 6 dígitos (ver `is_valid_asset_tag`) -- en
    cualquiera de esos casos, la UI debe dejar el campo vacío con el
    placeholder "NO SETUP" en vez de prellenarlo con un valor que de
    todos modos no pasaría la validación (por ejemplo "No disponible",
    que es lo que devuelve `get_asset_tag()` si la consulta WMI falla o
    viene vacía, o "Default string", un valor de fábrica no numérico que
    traen algunos equipos Dell sin configurar)."""
    raw = get_asset_tag()
    candidate = (raw or "").strip()
    if is_valid_asset_tag(candidate):
        return candidate
    return None


def apply_copa_id_asset_tag(asset_tag: str, installers_base_path: str) -> str:
    """Graba `asset_tag` en el BIOS del equipo vía Dell Command |
    Configure: corre
    `<installers_base_path>\\Copa_ID\\cctk.exe --asset=<asset_tag>`.

    Lanza `CopaIdSetupError` si `asset_tag` no son exactamente 6 dígitos
    (no debería pasar -- la UI ya lo valida antes de llegar acá, pero se
    revisa igual para no confiar ciegamente en el llamador), si no se
    encuentra `cctk.exe` en la ruta esperada (por ejemplo, la carpeta
    `Copa_ID` no vino copiada junto con los demás instaladores -- bug
    real reportado en campo: sin este chequeo, `subprocess.run` fallaba
    con el mensaje crudo de Windows `[WinError 2] The system cannot find
    the file specified`, que no le dice al técnico QUÉ archivo falta ni
    DÓNDE se esperaba encontrarlo, a diferencia del resto del catálogo
    -- ver `_resolve_installer_path`/`installer_path.exists()` en
    `app/installer.py`, que sí arma un mensaje claro con la ruta
    completa), o si `cctk.exe` no se pudo ejecutar por otro motivo, o si
    terminó con un código de salida distinto de 0."""
    asset_tag = (asset_tag or "").strip()
    if not is_valid_asset_tag(asset_tag):
        raise CopaIdSetupError(
            f"El Asset Tag '{asset_tag}' no es válido -- debe ser exactamente 6 dígitos numéricos."
        )

    # `Path(...).joinpath(...)` (no `ntpath.join`/concatenación de string):
    # así `.exists()` funciona con las reglas de ruta del sistema operativo
    # que de verdad está corriendo la app (mismo criterio que
    # `_resolve_installer_path` en app/installer.py) -- en producción
    # (Windows) es idéntico a antes, pero además es comprobable en Linux
    # (donde corren las pruebas automáticas de este proyecto).
    cctk_path = Path(installers_base_path).joinpath(*_CCTK_RELATIVE_PARTS)
    if not cctk_path.exists():
        raise CopaIdSetupError(
            f"No se encontró 'cctk.exe' en: {cctk_path} -- confirma que la carpeta "
            "'Copa_ID' con el ejecutable de Dell Command | Configure esté copiada "
            "junto con los demás instaladores."
        )

    command = [str(cctk_path), f"--asset={asset_tag}"]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, creationflags=_NO_CONSOLE_WINDOW
        )
    except subprocess.TimeoutExpired:
        raise CopaIdSetupError("cctk.exe (Copa ID / Asset Tag): tiempo de espera agotado.")
    except OSError as exc:
        raise CopaIdSetupError(f"cctk.exe (Copa ID / Asset Tag): no se pudo ejecutar -- {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"cctk.exe terminó con código {result.returncode} al grabar el Asset Tag '{asset_tag}'"
        if detail:
            msg += f" -- {detail}"
        raise CopaIdSetupError(msg)

    return f"Asset Tag '{asset_tag}' grabado correctamente vía cctk.exe"
