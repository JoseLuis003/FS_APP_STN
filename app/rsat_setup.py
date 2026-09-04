"""Instala "RSAT: Active Directory Domain Services and Lightweight
Directory Services Tools" (el snap-in "Active Directory Users and
Computers", `dsa.msc`, y el módulo de PowerShell `ActiveDirectory`) vía
DISM -- SIEMPRE contra Windows Update/WSUS (`/Online` sin `/Source` ni
`/LimitAccess`), a diferencia de `app/netfx35_setup.py` (que sigue
usando archivos locales, nunca internet).

Pedido explícito de campo (2026-09-04), después de investigar a fondo
el error 0x800f0912 documentado más abajo: se abandona por completo el
enfoque anterior (instalar desde los `.cab` locales de
`RSAT-ActiveDirectory-Offline\\`, sacados de la ISO oficial de
Microsoft "Languages and Optional Features"). Motivo -- confirmado con
un caso real de campo:

1. El paquete "Microsoft-Windows-ActiveDirectory-DS-LDS-Tools-FoD-Package"
   NO es estático: cada tanda de actualizaciones acumulativas de Windows
   lo revisa (`dism /online /Get-Packages` en un equipo real mostró 5
   versiones sucesivas del mismo paquete, de 10.0.26100.1742 hasta
   10.0.26100.9168, todas dentro de la MISMA rama de servicing). El
   `.cab` de la ISO "Languages and Optional Features" es una foto fija
   del día que salió esa ISO (equivalente a la versión más vieja,
   10.0.26100.1742) -- nunca se actualiza, sin importar cuántas veces se
   vuelva a descargar la misma ISO (confirmado: una descarga nueva de esa
   misma ISO, meses después, trajo el `.cab` bytes-idénticos al que ya
   había).
2. DISM exige que el paquete offline que se le da coincida (o supere) el
   nivel de servicing que ya tiene el equipo para ESE componente
   puntual -- un `.cab` más viejo que lo que el equipo ya trae aplicado
   por Windows Update queda descartado como fuente inválida, con el
   mismo 0x800f0912 ("The source files could not be found using
   available local sources") que si el archivo no existiera. Por eso el
   error volvía a pasar sin importar qué tan reciente fuera la ISO
   descargada, ni si el problema real era 24H2 vs 25H2 (build 26100 vs
   26200) -- esa fue la hipótesis inicial, y resultó ser una pista falsa.
3. Se investigó si había forma de "cosechar" un `.cab` actualizado desde
   un equipo ya parchado (donde el mismo paquete sí instala bien vía
   Windows Update, porque Microsoft resuelve dinámicamente la revisión
   correcta) -- no existe ningún mecanismo oficial ni de comunidad para
   reempaquetar un paquete ya instalado (WinSxS/CBS) de vuelta a un
   `.cab` redistribuible. Tampoco UUPdump.net sirve para esto: arma solo
   el sistema operativo base, no el contenido de Features on Demand.
   La recomendación oficial de Microsoft para flotas sin internet en
   24H2/25H2+ es WSUS + Configuration Manager con sincronización UUP
   local (mantiene el contenido de FOD al día automáticamente) -- eso es
   una decisión de infraestructura de Copa, fuera del alcance de este
   módulo.

Dado que no hay forma de mantener un `.cab` offline que no quede
obsoleto, y que instalar vía Windows Update SÍ funcionó en la prueba de
campo (la misma capability, en el mismo equipo, por esta vía), se
decidió que este paso siempre intente contra Windows Update/WSUS.
Equipos sin salida a internet van a seguir sin poder instalar RSAT por
este medio (ver el mensaje de error más abajo) -- pero esto ya era
cierto con el enfoque offline (el `.cab` desactualizado tampoco
funcionaba ahí), así que no es una regresión: simplemente ya no se
finge que hay una alternativa 100% offline que en la práctica no
funciona."""
from __future__ import annotations

import re
import subprocess

from app.reboot_pending import is_reboot_pending as _is_reboot_pending

# A diferencia del enfoque offline anterior (una copia local, rápida),
# esto ahora depende de la red -- Windows Update puede tardar bastante
# más en resolver y bajar el paquete. Mismo orden de magnitud que
# "Windows-Updates-w11" (ver DEFAULT_STEP_TIMEOUT_SECONDS/timeout_seconds
# en app/config.py), no los 600s (10 min) que alcanzaban para una copia
# local.
_TIMEOUT_SECONDS = 1800

# Mismo criterio que el resto de la app para este código (ver
# SUCCESS_CODES en app/installer.py): 3010 = éxito, pide reiniciar.
_SUCCESS_CODES = {0, 3010}

# Evita que Windows le abra su propia ventana de consola a `dism.exe`
# (quedaría en blanco y parecería colgado) -- ver la explicación
# completa en `NO_CONSOLE_WINDOW`, `app/installer.py`.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Nombre de la "capability" que instala esto -- el mismo que usaría
# `Add-WindowsCapability -Name ...` en PowerShell, pero acá se usa DISM
# directo (sin depender de un módulo de PowerShell aparte).
_CAPABILITY_NAME = "Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0"

# Código de salida 0x800f0912 ("The source files could not be found
# using available local sources") -- ya NO significa "build de Windows
# distinto" (esa era la hipótesis vieja, descartada -- ver el docstring
# del módulo). Yendo siempre contra Windows Update/WSUS, este mismo
# código típicamente indica que el equipo no tiene salida a internet, o
# que una política de la organización ("Specify settings for optional
# component installation and component repair", ver
# HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Servicing)
# apunta a un WSUS que no tiene sincronizado el contenido de Features on
# Demand.
_SOURCE_MISMATCH_RETURNCODE = 2148469010  # 0x800f0912, como entero (DISM/Python lo reportan así)
_IMAGE_VERSION_RE = re.compile(r"Image Version:\s*([\d.]+)")


def _extract_image_version(text: str) -> str | None:
    """Busca la línea "Image Version: X.X.XXXXX.XXXX" que DISM imprime en
    su propio stdout -- el build real de Windows que está corriendo en el
    equipo. Devuelve `None` si no aparece (ej. un fallo distinto que corta
    antes de que DISM llegue a imprimir esa línea)."""
    match = _IMAGE_VERSION_RE.search(text or "")
    return match.group(1) if match else None


class RsatSetupError(Exception):
    """Error esperado si no se pudo instalar RSAT (AD DS/LDS Tools). El
    mensaje ya viene listo para mostrárselo tal cual al técnico."""


# `_is_reboot_pending()` (importado arriba desde `app/reboot_pending.py`,
# compartido con `app/netfx35_setup.py`): DISM usa el mismo almacén de
# componentes (CBS) tanto para `/Enable-Feature` como para
# `/Add-Capability`, así que corre el mismo riesgo de quedarse colgado
# hasta agotar `_TIMEOUT_SECONDS` si el equipo quedó en reinicio
# pendiente, en vez de fallar rápido con un mensaje claro.


def _build_dism_command() -> list[str]:
    # Sin `/Source` ni `/LimitAccess`: a propósito, para que DISM vaya
    # siempre contra Windows Update/WSUS (ver el docstring del módulo
    # para el porqué del cambio). Ya no depende de `installers_base_path`
    # ni de ninguna carpeta local.
    return [
        "dism.exe",
        "/Online",
        "/Add-Capability",
        f"/CapabilityName:{_CAPABILITY_NAME}",
    ]


def ensure_rsat_ad_tools_installed(installers_base_path: str) -> str:
    """Instala "RSAT: Active Directory DS/LDS Tools" vía DISM, siempre
    contra Windows Update/WSUS (ver el docstring del módulo para el
    porqué se abandonó el enfoque offline). Es idempotente: si ya estaba
    instalado, DISM lo reporta como éxito igual, sin reinstalar nada.

    `installers_base_path` se recibe (como todo paso "python", ver
    `app/installer.py`) pero se ignora a propósito -- ya no hace falta
    ninguna carpeta local para esta capability (mismo patrón que
    `run_ltp_shares_post_install`, que tampoco lo usa).

    Pensado para colgarse como ítem del catálogo (`installer_type:
    "python"`, ver `config/apps.json`).

    Lanza `RsatSetupError` si DISM falla -- por ejemplo, si el equipo no
    tiene salida a internet ni a un WSUS con el contenido sincronizado,
    o si quedó con un reinicio pendiente (ver `_is_reboot_pending`, mismo
    caso real que documenta `netfx35_setup.py`: correr DISM en ese estado
    no falla rápido, se queda colgado hasta agotar `_TIMEOUT_SECONDS`
    esperando el lock del CBS)."""
    del installers_base_path  # ver docstring: ya no hace falta

    if _is_reboot_pending():
        raise RsatSetupError(
            "Reinicio Pendiente: hay un reinicio de Windows pendiente (probablemente por una "
            "actualización que se acaba de instalar) -- DISM no puede instalar RSAT hasta que el "
            "equipo reinicie. Reinicia el equipo y vuelve a marcar esta casilla."
        )

    command = _build_dism_command()
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, creationflags=_NO_CONSOLE_WINDOW
        )
    except subprocess.TimeoutExpired:
        raise RsatSetupError(f"DISM (RSAT AD DS/LDS Tools): tiempo de espera agotado ({_TIMEOUT_SECONDS // 60} min).")
    except OSError as exc:
        raise RsatSetupError(f"DISM (RSAT AD DS/LDS Tools): no se pudo ejecutar -- {exc}")

    if result.returncode not in _SUCCESS_CODES:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"No se pudo instalar RSAT (AD DS/LDS Tools) (DISM terminó con código {result.returncode})"
        if detail:
            msg += f" -- {detail}"
        if result.returncode == _SOURCE_MISMATCH_RETURNCODE:
            # Ver `_SOURCE_MISMATCH_RETURNCODE` arriba -- se busca en el
            # texto COMPLETO (no en `detail`, ya truncado a 500
            # caracteres) por si la línea "Image Version" quedara más
            # allá de ese límite en algún log futuro.
            full_output = f"{result.stdout or ''}\n{result.stderr or ''}"
            image_version = _extract_image_version(full_output)
            note = (
                "este equipo probablemente NO tiene salida a internet (o a un WSUS con el contenido "
                "de RSAT/Features on Demand sincronizado) -- DISM ya no usa ningún archivo local para "
                "esto, siempre depende de Windows Update/WSUS. Si el equipo SÍ debería tener internet, "
                "también puede ser una política de la organización ('Specify settings for optional "
                "component installation and component repair') apuntando a un WSUS sin ese contenido -- "
                "revisar HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Servicing en ese equipo."
            )
            if image_version:
                note += f" Este equipo reporta Image Version {image_version}."
            msg += f" -- {note}"
        raise RsatSetupError(msg)

    if result.returncode == 3010:
        return "RSAT (AD DS/LDS Tools) instalado vía DISM/Windows Update (pide reiniciar para terminar de aplicarse)"
    return "RSAT (AD DS/LDS Tools) ya estaba instalado (o se instaló correctamente) vía DISM/Windows Update"
