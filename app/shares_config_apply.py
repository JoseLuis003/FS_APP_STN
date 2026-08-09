"""Lógica de la acción "Shares Configuracion" del catálogo LTP / CSS.

A diferencia del resto de ítems del catálogo, "Shares Configuracion" no
ejecuta un instalador tradicional (.exe/.msi/.bat): en vez de eso, edita
directamente los archivos de Shares que ya están en el equipo, usando los
valores de CIUDAD y HOSTNAME capturados en el panel
(`app/ui/shares_config_panel.py`). Los pasos, en este orden:

1. Busca la carpeta `CNT` dentro de `base_dir` (por defecto
   `C:\\LTP\\AppDatCM`) y la renombra al valor de CIUDAD. Si ya se había
   renombrado en una corrida anterior (ya no existe `CNT` pero sí la
   carpeta con el nombre de CIUDAD), se reutiliza tal cual — así se puede
   volver a aplicar esta acción sin que falle por no encontrar `CNT`.
2. Dentro de esa carpeta, busca el archivo `LTPCMCNT.XRF` y le cambia las
   3 últimas letras antes de la extensión ("CNT") por el valor de CIUDAD
   (ej. `LTPCMCNT.XRF` -> `LTPCMPTY.XRF` si CIUDAD es "PTY"). Mismo criterio
   de idempotencia que en el paso 1.
3. Abre ese archivo y:
   a. Reemplaza cualquier aparición de "CNT" en el contenido por el valor
      de CIUDAD.
   b. En la línea que empieza con `WORKSTATION_NAME=`, reemplaza esa clave
      por el valor de HOSTNAME, dejando el resto de la línea intacto (ej.
      `WORKSTATION_NAME=CHECKIN` -> `LTP-JB=CHECKIN`).

   Se hace primero (a) y después (b) — y no al revés — para que, si el
   HOSTNAME llegara a contener "CNT" como parte de su nombre, el reemplazo
   global del paso (a) no lo toque por accidente.
"""
from __future__ import annotations

import re
from pathlib import Path

# Ruta donde vive la configuración de Shares en el equipo. Se puede pasar
# una ruta distinta a `apply_shares_configuration()` (útil para pruebas).
DEFAULT_BASE_DIR = Path(r"C:\LTP\AppDatCM")

# Código de ciudad "de fábrica" que trae Shares antes de configurarlo.
OLD_CODE = "CNT"

# Prefijo del nombre de archivo, antes del código de ciudad.
FILE_PREFIX = "LTPCM"
FILE_SUFFIX = ".XRF"

# Clave de la línea que identifica el nombre de estación dentro del .XRF.
WORKSTATION_KEY = "WORKSTATION_NAME"
_WORKSTATION_PATTERN = re.compile(rf"(?m)^{re.escape(WORKSTATION_KEY)}(?==)")


class SharesConfigError(Exception):
    """Error esperado (ruta/archivo no encontrado, campos vacíos, etc.) al
    aplicar la configuración de Shares. El mensaje ya viene listo para
    mostrárselo tal cual al técnico."""


def apply_shares_configuration(
    hostname: str,
    ciudad: str,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> str:
    """Ejecuta los 3 pasos descritos en el docstring del módulo.

    Devuelve un mensaje corto de éxito (rutas finales) para mostrar en el
    estado de la pantalla. Lanza `SharesConfigError` si algo no se pudo
    hacer — el llamador decide cómo mostrarlo (igual que el resto de
    errores de instalación)."""
    hostname = (hostname or "").strip()
    ciudad = (ciudad or "").strip()
    if not ciudad:
        raise SharesConfigError(
            "El campo CIUDAD está vacío — hace falta un valor para renombrar la carpeta y el archivo."
        )
    if not hostname:
        raise SharesConfigError(
            "El campo HOSTNAME está vacío — hace falta un valor para la línea WORKSTATION_NAME."
        )

    base_dir = Path(base_dir)
    new_folder = _rename_or_reuse(
        old_path=base_dir / OLD_CODE,
        new_path=base_dir / ciudad,
        kind="carpeta",
    )

    old_filename = f"{FILE_PREFIX}{OLD_CODE}{FILE_SUFFIX}"
    new_filename = f"{FILE_PREFIX}{ciudad}{FILE_SUFFIX}"
    new_file = _rename_or_reuse(
        old_path=new_folder / old_filename,
        new_path=new_folder / new_filename,
        kind="archivo",
    )

    # `newline=""` desactiva la traducción automática de saltos de línea de
    # Python: sin esto, un archivo con \r\n (típico en config de Windows) se
    # leería como \n y se reescribiría con el salto de línea del sistema
    # donde corre la app, perdiendo el formato original del .XRF.
    with new_file.open("r", encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()

    # (a) primero el reemplazo global de "CNT" -> CIUDAD...
    text = text.replace(OLD_CODE, ciudad)
    # (b) ...y después la línea WORKSTATION_NAME=, para que un HOSTNAME que
    # contenga "CNT" no se vea afectado por el reemplazo de arriba.
    text = _WORKSTATION_PATTERN.sub(lambda _m: hostname, text)

    with new_file.open("w", encoding="utf-8", newline="") as f:
        f.write(text)

    return f"Carpeta: {new_folder} | Archivo: {new_file}"


def _rename_or_reuse(old_path: Path, new_path: Path, kind: str) -> Path:
    """Renombra `old_path` a `new_path` si `old_path` todavía existe; si ya
    no existe pero `new_path` sí (por una corrida anterior de esta misma
    acción), se reutiliza tal cual. Si no existe ninguno de los dos, o si
    existen ambos a la vez (algo raro que conviene revisar a mano), se
    lanza `SharesConfigError`."""
    if old_path == new_path:
        if old_path.exists():
            return old_path
        raise SharesConfigError(f"No se encontró {kind} '{old_path}'.")

    old_exists = old_path.exists()
    new_exists = new_path.exists()

    if old_exists and new_exists:
        raise SharesConfigError(
            f"Ya existen tanto '{old_path}' como '{new_path}' — revisa manualmente cuál es la correcta antes de continuar."
        )
    if old_exists:
        old_path.rename(new_path)
        return new_path
    if new_exists:
        # Ya se había aplicado esta acción antes: se reutiliza tal cual.
        return new_path
    raise SharesConfigError(f"No se encontró {kind} '{old_path}' (ni ya renombrada a '{new_path}').")
