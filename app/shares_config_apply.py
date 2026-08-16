"""Lógica de la acción "Shares Configuracion" del catálogo LTP / CSS.

A diferencia del resto de ítems del catálogo, "Shares Configuracion" no
ejecuta un instalador tradicional (.exe/.msi/.bat): en vez de eso, edita
directamente los archivos de Shares que ya están en el equipo, usando los
valores de CIUDAD y HOSTNAME capturados en el panel
(`app/ui/shares_config_panel.py`). Los pasos, en este orden:

1. Busca, dentro de `base_dir` (por defecto `C:\\LTP\\AppDatCM`), la
   carpeta que el instalador de Shares 5.0 deja con un código "de
   fábrica" -- y la renombra al valor real de CIUDAD.

   Ese código de fábrica NO se asume fijo (antes se pensó que era "CNT";
   resultó ser "PTY" en la versión 5.0 actual del instalador, sin importar
   la ciudad real de destino de la estación -- ver historial de este
   módulo). En vez de volver a hardcodear un valor que una futura versión
   de Shares podría cambiar de nuevo, esta carpeta se **detecta
   dinámicamente**: se busca, entre las subcarpetas directas de
   `base_dir` (que no sea ya la de CIUDAD), cuál contiene un archivo que
   matchee `LTPCM<código>.XRF` (el patrón fijo que sí se mantiene entre
   versiones), sea cual sea ese código de 3 letras. Así, si una futura
   versión de Shares vuelve a cambiar el código de fábrica, esta acción
   sigue funcionando sin tocar el código de la app.

   Si CIUDAD ya coincide con el código que trae de fábrica (ej. una
   estación de Panamá con CIUDAD = "PTY"), no hace falta renombrar nada —
   se reutiliza la carpeta tal cual. Si ya se había renombrado en una
   corrida anterior (ya existe la carpeta de CIUDAD), también se reutiliza
   tal cual — así se puede volver a aplicar esta acción sin que falle por
   no encontrar la carpeta de fábrica.

   Si esa carpeta candidata tiene MÁS de un archivo `.XRF` válido adentro
   -- visto en un equipo real: un equipo reutilizado, con el archivo de
   una ciudad configurada anteriormente (ej. `LTPCMMIA.XRF`, de 2024) que
   nunca se borró, junto al archivo de fábrica recién instalado (ej.
   `LTPCMPTY.XRF`, de hoy) -- no se falla ni se adivina a ciegas: se
   asume que el más reciente (mayor fecha de modificación) es el que el
   instalador de Shares 5.0 acaba de dejar en esta corrida (cada vez que
   se reinstala, Shares reescribe su propio archivo de fábrica, así que
   su fecha queda "de ahora"), y los demás -- más viejos -- se MUEVEN
   (nunca se borran) a una subcarpeta `_config_anterior` dentro de esa
   misma carpeta, para que no sigan generando esta misma ambigüedad en la
   próxima corrida, pero sigan recuperables ahí si hiciera falta
   revisarlos (ver `_archive_older_xrf_matches`).
2. Dentro de esa carpeta, busca el archivo `LTPCM<código>.XRF` (el mismo
   que sirvió para detectarla en el paso 1) y le cambia las 3 letras del
   código por el valor de CIUDAD (ej. `LTPCMPTY.XRF` -> `LTPCMMDE.XRF` si
   CIUDAD es "MDE"). Mismo criterio de idempotencia que en el paso 1.
3. Abre ese archivo y:
   a. Reemplaza cualquier aparición del código detectado en el paso 1/2
      (ej. "PTY") en el contenido por el valor de CIUDAD.
   b. Busca la línea `<clave>=CHECKIN` (sea cual sea `<clave>`) y
      reemplaza esa clave por el valor de HOSTNAME, dejando `=CHECKIN`
      intacto (ej. `*WKSNAME=CHECKIN` -> `LTP-JB=CHECKIN`).

      La clave real de esta línea **cambió entre versiones** del
      instalador de Shares -- se había asumido `WORKSTATION_NAME`, y
      resultó ser `*WKSNAME` en un archivo real (con el asterisco
      incluido, confirmado por el técnico). En vez de volver a depender
      de un nombre de clave fijo (que una futura versión podría cambiar
      de nuevo), esta línea se **detecta dinámicamente por su VALOR de
      fábrica** (`CHECKIN`, que se mantuvo igual entre esas 2 versiones
      pese a que la clave cambió) -- mismo criterio que ya se usa para
      el código de CIUDAD en el paso 1. Si el archivo no tiene ninguna
      línea `<algo>=CHECKIN`, o tiene más de una (ambiguo), no se
      adivina: se lanza `SharesConfigError` con el detalle.

   Se hace primero (a) y después (b) — y no al revés — para que, si el
   HOSTNAME llegara a contener ese código como parte de su nombre, el
   reemplazo global del paso (a) no lo toque por accidente.

   A diferencia de la carpeta/archivo del paso 1/2 (que si ya están
   renombrados no se vuelven a tocar), el paso (b) SÍ se reaplica en
   cada corrida: como el ancla de detección (`=CHECKIN`) queda intacta a
   propósito, volver a presionar INSTALAR con un HOSTNAME distinto
   actualiza la clave al valor más reciente -- no se queda pegado para
   siempre al primer HOSTNAME que se haya aplicado.

Por último, si la casilla CONTINGENCIA del panel está marcada,
`run_contingencia_script()` corre `LTP TRAVEL DOC\Contingencia.bat` — a
diferencia de todo lo anterior, esto SÍ es un proceso externo (no una
edición de archivo) y su ruta es relativa a la carpeta base de
instaladores (`installers_base_path`, la misma que usa el resto del
catálogo LTP / CSS), no a `base_dir` (que es donde vive la configuración
de Shares en sí, típicamente `C:\LTP\AppDatCM`).

Además, `apply_udf_configuration()` edita un segundo archivo,
`LTPCMUDF.INF`, que vive dentro de la carpeta `UDF` junto al `.XRF` de
arriba (por eso se llama después de `apply_shares_configuration()`, una
vez que la carpeta ya se renombró a CIUDAD):

- Si LNIATA CRT está marcado: la línea `GROUP=F,XXXXXX` (2 líneas debajo
  del comentario "define the number of LNIATA as needed for Parent
  Sessions") cambia el valor entre comas por LNIATA CRT. Si no está
  marcado, esa línea no se toca.
- La línea `LOCATION=...` cambia su valor por CIUDAD, siempre.
- Para cada sesión adicional (ATB, BTP, DCP), si su casilla LNIATA
  correspondiente está marcada: la línea `<SUFIJO>=0,<SUFIJO>1,,` cambia
  el "0" por "1", la línea `<SUFIJO>1LNIATA=XXXXXX,` cambia su valor por
  el valor de ese campo LNIATA, y el puerto fijo de esa sesión
  (`ATB1PORT`/`BTP1PORT`/`DCP1PORT`) se corrige a su valor esperado (COM7,
  COM8 y COM10 respectivamente -- DCP usa COM10, no COM9, porque comparten
  impresoras con "AppShell Configuracion", donde OCR ya usa COM9, ver
  `app/appshell_config_apply.py`) si tiene uno distinto. Si la casilla NO
  está marcada, ninguna de esas tres líneas se toca (ni el flag, ni el
  LNIATA, ni el puerto).
- Si **BGR** está marcado: la línea `BGR=0` cambia el "0" por "1" (deja
  cualquier otra cosa que venga después en esa misma línea intacta). Si
  **OCR** está marcado: igual, pero con la línea `OCR=0`. Ninguna de las
  dos tiene un campo LNIATA ni un puerto asociado (a diferencia de
  ATB/BTP/DCP) — son casillas simples del panel "DEVICES" de "Shares
  Configuracion" (distintas de las de "AppShell Configuracion", que viven
  en `app/appshell_config_apply.py` y editan otro archivo, `Mastcom.xml`).
- Si **CRT 2** está marcado: la línea `CRT=<número>,...` cambia solo el
  número inicial a "2", sin tocar el resto de la línea (los
  identificadores de pantalla que vengan después quedan como estaban).
- Si **CRT 4** está marcado: la línea `CRT=1,CRT1P1,CRT2C1,CRT3P2,`
  (el valor de fábrica esperado) se reemplaza ENTERA por
  `CRT=4,CRT1P1,CRT2C1,CRT3C1,CRT4C1,` — a diferencia de CRT 2, acá no
  alcanza con cambiar el número: el identificador de la 3ra pantalla
  también cambia (de "P2" a "C1") y se agrega un identificador para la
  4ta. Por eso, si la línea no es EXACTAMENTE ese valor de fábrica
  esperado (por ejemplo, porque ya se había aplicado CRT 2 antes en la
  misma corrida), se lanza un error explicando qué se esperaba encontrar,
  en vez de adivinar cómo transformarla. CRT 2 y CRT 4 son mutuamente
  excluyentes en el panel (una estación tiene 2 pantallas o 4, no ambas a
  la vez) — ver `app/ui/shares_config_panel.py`.

En todos los casos se reemplaza solo el valor indicado, sin tocar las
comas ni el resto de la línea (excepto CRT 4, que sí necesita reemplazar
la línea completa — ver arriba). A diferencia del código VB.NET original,
que en varios de estos pasos usaba `On Error Resume Next` (si algo no
salía como se esperaba, seguía de largo en silencio), acá CUALQUIER paso
marcado que no encuentre lo que espera lanza `SharesConfigError` con un
mensaje claro — igual que el resto de esta pantalla.

Todos estos cambios se acumulan en memoria y el archivo se reescribe una
sola vez, al final, después de que TODOS los pasos marcados pasaron sin
error — por eso, si algún paso falla (por ejemplo, CRT 2 y CRT 4 llegaran
marcados juntos), el archivo en disco queda exactamente como estaba, sin
ningún cambio parcial aplicado."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Ruta donde vive la configuración de Shares en el equipo. Se puede pasar
# una ruta distinta a `apply_shares_configuration()` (útil para pruebas).
DEFAULT_BASE_DIR = Path(r"C:\LTP\AppDatCM")

# Prefijo/sufijo fijo del nombre de archivo que deja Shares, alrededor del
# código de 3 letras que sí puede cambiar entre versiones (ver docstring
# del módulo): "LTPCM" + <código> + ".XRF" (ej. "LTPCMPTY.XRF"). El código
# en sí ya NO se asume fijo en ningún lado de este archivo -- se detecta
# dinámicamente en cada corrida (ver `_find_xrf_file` / `_find_factory_folder`),
# precisamente para no tener que volver a tocar este código si una futura
# versión de Shares cambia otra vez qué código de fábrica usa.
FILE_PREFIX = "LTPCM"
FILE_SUFFIX = ".XRF"
_CODE_LENGTH = 3

# Subcarpeta donde se archivan (se MUEVEN, no se borran) los archivos
# `.XRF` "de más" que se encuentren dentro de una misma carpeta candidata
# (ver `_archive_older_xrf_matches`) -- típicamente el archivo de una
# ciudad configurada anteriormente en ese mismo equipo, que nunca se
# borró y quedó junto al archivo de fábrica recién instalado.
ARCHIVE_SUBDIR_NAME = "_config_anterior"

# La línea que identifica el nombre de estación dentro del .XRF (sección
# [WORKSTATIONS]) se detecta por su VALOR de fábrica, NO por el nombre de
# su clave -- esa clave ya cambió una vez entre versiones del instalador
# de Shares (se había asumido "WORKSTATION_NAME", resultó ser "*WKSNAME"
# en un archivo real), mientras que el valor "CHECKIN" se mantuvo igual
# entre esas 2 versiones. Ver el punto (b) del paso 3 en el docstring del
# módulo para el criterio completo.
WORKSTATION_PLACEHOLDER_VALUE = "CHECKIN"
_WORKSTATION_LINE_PATTERN = re.compile(
    rf"(?m)^([^\r\n=]+)={re.escape(WORKSTATION_PLACEHOLDER_VALUE)}(?=\r?\n|$)"
)


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
            "El campo HOSTNAME está vacío — hace falta un valor para la línea "
            f"'<clave>={WORKSTATION_PLACEHOLDER_VALUE}' del archivo."
        )

    base_dir = Path(base_dir)
    if not base_dir.exists():
        raise SharesConfigError(f"No se encontró la carpeta base '{base_dir}'.")

    new_folder = base_dir / ciudad
    archived_detail = ""
    if not new_folder.exists():
        # Todavía no se había aplicado esta acción antes: hay que
        # encontrar la carpeta "de fábrica" (código detectado
        # dinámicamente, ver docstring del módulo) y renombrarla.
        source_folder, archived_detail = _find_factory_folder(base_dir, ciudad)
        source_folder.rename(new_folder)

    xrf_file = _find_xrf_file(new_folder)
    factory_code = xrf_file.name[len(FILE_PREFIX) : -len(FILE_SUFFIX)]
    new_file = new_folder / f"{FILE_PREFIX}{ciudad}{FILE_SUFFIX}"
    if xrf_file != new_file:
        xrf_file.rename(new_file)

    # `newline=""` desactiva la traducción automática de saltos de línea de
    # Python: sin esto, un archivo con \r\n (típico en config de Windows) se
    # leería como \n y se reescribiría con el salto de línea del sistema
    # donde corre la app, perdiendo el formato original del .XRF.
    with new_file.open("r", encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()

    # (a) primero el reemplazo global del código detectado -> CIUDAD...
    text = text.replace(factory_code, ciudad)
    # (b) ...y después la línea '<clave>=CHECKIN' (detectada por su VALOR,
    # no por el nombre de su clave -- ver comentario de
    # `WORKSTATION_PLACEHOLDER_VALUE` más arriba), para que un HOSTNAME
    # que contenga el código de CIUDAD no se vea afectado por el
    # reemplazo de (a).
    workstation_matches = list(_WORKSTATION_LINE_PATTERN.finditer(text))
    if not workstation_matches:
        raise SharesConfigError(
            f"No se encontró ninguna línea '<clave>={WORKSTATION_PLACEHOLDER_VALUE}' en "
            f"'{new_file}' -- puede que una versión más nueva de Shares también haya "
            "cambiado ese valor de fábrica (antes 'CHECKIN'), no solo el nombre de la clave."
        )
    if len(workstation_matches) > 1:
        keys_found = ", ".join(m.group(1) for m in workstation_matches)
        raise SharesConfigError(
            f"Se encontraron {len(workstation_matches)} líneas terminadas en "
            f"'={WORKSTATION_PLACEHOLDER_VALUE}' en '{new_file}' ({keys_found}) -- no se puede "
            "saber cuál es el nombre de estación sin ambigüedad."
        )
    text = _WORKSTATION_LINE_PATTERN.sub(
        lambda _m: f"{hostname}={WORKSTATION_PLACEHOLDER_VALUE}", text, count=1
    )

    with new_file.open("w", encoding="utf-8", newline="") as f:
        f.write(text)

    detail = f"Carpeta: {new_folder} | Archivo: {new_file}"
    if archived_detail:
        detail = f"{detail} | {archived_detail}"
    return detail


def _is_xrf_filename(name: str) -> bool:
    """True si `name` matchea `LTPCM<código de _CODE_LENGTH letras>.XRF`
    (sin importar mayúsculas/minúsculas -- Windows no distingue)."""
    return (
        len(name) == len(FILE_PREFIX) + _CODE_LENGTH + len(FILE_SUFFIX)
        and name.upper().startswith(FILE_PREFIX.upper())
        and name.upper().endswith(FILE_SUFFIX.upper())
    )


def _list_xrf_matches(folder: Path) -> list[Path]:
    """Lista los archivos dentro de `folder` que matcheen
    `LTPCM<código de _CODE_LENGTH letras>.XRF`, sin lanzar ningún error --
    puede devolver una lista vacía, con un solo elemento, o con varios
    (caso ambiguo). `_find_xrf_file()` valida ese resultado y lanza error;
    `_find_factory_folder()` necesita el conteo tal cual, para distinguir
    "esta carpeta no tiene ninguno" (no es candidata, se ignora sin más)
    de "esta carpeta tiene más de uno" (si ES candidata -- tiene al menos
    un archivo de fábrica válido -- pero hay un archivo extra ahí que no
    debería estar, típicamente uno viejo de una configuración anterior que
    nunca se borró; visto en un equipo real). Antes, ambos casos se trataban
    igual (la carpeta simplemente se descartaba como candidata), lo que
    hacía que ese archivo viejo hiciera fallar la detección completa con un
    mensaje engañoso ("no se encontró ninguna carpeta... revisa que Shares
    esté instalado"), aunque sí estaba instalado."""
    return sorted(f for f in folder.iterdir() if f.is_file() and _is_xrf_filename(f.name))


def _find_xrf_file(folder: Path) -> Path:
    """Busca, dentro de `folder`, el único archivo que matchee
    `LTPCM<código>.XRF` (cualquier código de `_CODE_LENGTH` letras — no se
    asume cuál). Lanza `SharesConfigError` si no encuentra ninguno, o si
    encuentra más de uno (caso ambiguo; no debería pasar en una instalación
    normal de Shares, pero es más seguro fallar y avisar que adivinar
    cuál usar)."""
    matches = _list_xrf_matches(folder)
    if not matches:
        raise SharesConfigError(f"No se encontró ningún archivo '{FILE_PREFIX}*{FILE_SUFFIX}' dentro de '{folder}'.")
    if len(matches) > 1:
        names = ", ".join(f.name for f in matches)
        raise SharesConfigError(
            f"Se encontró más de un archivo '{FILE_PREFIX}*{FILE_SUFFIX}' dentro de '{folder}' ({names}) "
            "— no se puede saber cuál es el correcto, revisa manualmente."
        )
    return matches[0]


def _archive_older_xrf_matches(folder: Path, matches: list[Path]) -> str:
    """Cuando `folder` (una carpeta candidata real, con al menos un
    archivo `.XRF` válido) tiene MÁS de uno, se asume que el más reciente
    (mayor fecha de modificación) es el que el instalador de Shares 5.0
    acaba de dejar en esta corrida -- cada vez que se reinstala, Shares
    reescribe su propio archivo de fábrica, así que queda con fecha "de
    ahora"; los demás son de una configuración anterior de ese mismo
    equipo (otra ciudad) que nunca se borró. Esos archivos más viejos se
    MUEVEN (nunca se borran) a `folder / ARCHIVE_SUBDIR_NAME`, evitando
    colisiones de nombre si ya había algo archivado ahí de antes (se les
    agrega un sufijo numérico en vez de sobrescribir). Devuelve un detalle
    corto para el mensaje final, o cadena vacía si no había nada que
    archivar (`matches` con 0 o 1 elemento).

    Nota: esto asume que la fecha de modificación es un indicador
    confiable de cuál archivo es el vigente -- válido en el caso real que
    motivó esto (un equipo reutilizado, con un archivo mucho más viejo que
    el resto), pero si dos archivos quedaran con fechas casi idénticas
    (ej. restaurados juntos desde una imagen de disco), el más nuevo por
    apenas unos segundos "gana" de todas formas; no hay forma de detectar
    ese empate desde acá."""
    if len(matches) <= 1:
        return ""

    newest = max(matches, key=lambda f: f.stat().st_mtime)
    older = [f for f in matches if f != newest]

    archive_dir = folder / ARCHIVE_SUBDIR_NAME
    archive_dir.mkdir(exist_ok=True)

    archived_names: list[str] = []
    for f in older:
        destination = archive_dir / f.name
        if destination.exists():
            # Ya había algo archivado antes con ese mismo nombre -- se le
            # agrega un sufijo numérico en vez de sobrescribirlo (nunca se
            # pierde un archivo por esto).
            counter = 1
            while destination.exists():
                destination = archive_dir / f"{f.stem} ({counter}){f.suffix}"
                counter += 1
        f.rename(destination)
        archived_names.append(f.name)

    return (
        f"se archivó {len(archived_names)} archivo(s) '{FILE_PREFIX}*{FILE_SUFFIX}' anterior(es) "
        f"en '{archive_dir}': {', '.join(archived_names)}"
    )


def _find_factory_folder(base_dir: Path, ciudad: str) -> tuple[Path, str]:
    """Busca, entre las subcarpetas DIRECTAS de `base_dir` (que no sea ya
    la de CIUDAD), cuál contiene un archivo `LTPCM<código>.XRF` — esa es la
    carpeta "de fábrica" que Shares deja siempre, sea cual sea el código de
    3 letras que use esa versión del instalador (ver docstring del
    módulo). Devuelve `(carpeta, detalle)` — `detalle` es `""` si esa
    carpeta tenía un solo `.XRF` (caso normal), o el mensaje de
    `_archive_older_xrf_matches()` si tenía más de uno y se archivaron los
    más viejos. Lanza `SharesConfigError` si no encuentra ninguna
    candidata, o si encuentra más de una carpeta candidata (caso ambiguo
    ENTRE carpetas -- eso sí hay que revisarlo a mano, a diferencia de
    tener varios `.XRF` dentro de UNA misma carpeta, que se resuelve solo
    -- ver arriba)."""
    candidates: list[Path] = []
    archived_detail = ""
    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir() or entry.name.upper() == ciudad.upper():
            continue
        matches = _list_xrf_matches(entry)
        if len(matches) == 1:
            candidates.append(entry)
        elif len(matches) > 1:
            archived_detail = _archive_older_xrf_matches(entry, matches)
            candidates.append(entry)
        # len(matches) == 0: esta carpeta no tiene ningún .XRF -- no es
        # candidata, se ignora sin más (ej. la carpeta "Browser" que deja
        # el propio Shares junto a la de configuración).

    if not candidates:
        raise SharesConfigError(
            f"No se encontró ninguna carpeta con un archivo '{FILE_PREFIX}*{FILE_SUFFIX}' dentro de "
            f"'{base_dir}' (ni tampoco la carpeta '{ciudad}' ya configurada) — revisa que Shares 5.0 "
            "ya esté instalado en este equipo."
        )
    if len(candidates) > 1:
        names = ", ".join(c.name for c in candidates)
        raise SharesConfigError(
            f"Se encontraron varias carpetas candidatas dentro de '{base_dir}' ({names}) — no se puede "
            "saber cuál corresponde a esta estación, revisa manualmente cuál es la correcta."
        )
    return candidates[0], archived_detail


# --------------------------------------------------------------------------
# Segunda parte: LTPCMUDF.INF, dentro de la carpeta UDF (dentro de la
# carpeta ya renombrada a CIUDAD por `apply_shares_configuration()`).
# --------------------------------------------------------------------------

# Comentario que marca dónde está, 2 líneas más abajo, la línea GROUP=...
_UDF_ANCHOR_TEXT = "define the number of LNIATA as needed for Parent Sessions"
_UDF_ANCHOR_OFFSET = 2

# GROUP=F,XXXXXX -> grupo 1 = "GROUP=F,", grupo 2 = "XXXXXX" (el valor a
# reemplazar), grupo 3 = lo que venga después (ej. una coma final), tal
# cual, sin tocarlo.
_GROUP_LINE_PATTERN = re.compile(r"^(GROUP=[^,\r\n]*,)([^,\r\n]*)(.*)$")

# Búsquedas directas (no dependen de posición) para el resto de líneas.
_LOCATION_PATTERN = re.compile(r"(?m)^(LOCATION=)([^,\r\n]*)")

# Puerto fijo que le corresponde a cada sesión adicional — siempre debe
# quedar en ese valor, esté o no esté marcada la casilla LNIATA de esa
# sesión. DCP usa COM10 (no COM9): este equipo comparte impresoras con
# "AppShell Configuracion" (app/appshell_config_apply.py), donde OCR ya
# usa COM9 en Mastcom.xml -- ambos archivos son distintos, pero un mismo
# puerto físico no puede quedar asignado a dos sesiones a la vez.
_SESSION_PORTS = {
    "ATB": "COM7",
    "BTP": "COM8",
    "DCP": "COM10",
}


def _flag_pattern(suffix: str) -> re.Pattern[str]:
    # <SUFIJO>=0,<SUFIJO>1,, -> grupo 1 = "<SUFIJO>=", grupo 2 = "0" (el
    # flag a cambiar por "1"), grupo 3 = lo que sigue (",<SUFIJO>1,,"),
    # tal cual, sin tocarlo.
    return re.compile(rf"(?m)^({re.escape(suffix)}=)([^,\r\n]*)(,.*)$")


def _lniata_value_pattern(suffix: str) -> re.Pattern[str]:
    return re.compile(rf"(?m)^({re.escape(suffix)}1LNIATA=)([^,\r\n]*)")


def _port_pattern(suffix: str) -> re.Pattern[str]:
    return re.compile(rf"(?m)^({re.escape(suffix)}1PORT=)([^,\r\n]*)")


def _simple_activation_pattern(key: str) -> re.Pattern[str]:
    # <KEY>=<valor><resto opcional> -> grupo 1 = "<KEY>=", grupo 2 = el
    # valor actual (lo que sea, hasta la próxima coma o fin de línea; no
    # hace falta que sea "0" -- igual que _flag_pattern, esto es
    # idempotente: no importa cuál sea el valor actual, siempre se fuerza
    # a "1"), grupo 3 = cualquier cosa que venga después (ej. una coma y
    # más datos), tal cual, sin tocarla. A diferencia de _flag_pattern
    # (ATB/BTP/DCP), NO exige que haya una coma después -- BGR y OCR son
    # casillas simples sin su propio campo LNIATA/puerto asociado, así que
    # esa línea puede no tener nada más.
    return re.compile(rf"(?m)^({re.escape(key)}=)([^,\r\n]*)(.*)$")


# CRT=<número>,<resto> -> grupo 1 = "CRT=", grupo 2 = el número de
# pantallas actual, grupo 3 = ",<resto>" (los identificadores de pantalla)
# tal cual, sin tocarlos -- usado por CRT 2, que solo cambia ese número.
_CRT_COUNT_PATTERN = re.compile(r"(?m)^(CRT=)([^,\r\n]*)(,.*)$")

# CRT 4 no alcanza con cambiar el número: el identificador de la 3ra
# pantalla también cambia (de "P2" a "C1") y se agrega uno para la 4ta.
# Por eso, en vez de una regex genérica, se exige que la línea sea
# EXACTAMENTE este valor de fábrica esperado antes de reemplazarla entera
# -- ver `_apply_crt4` y el docstring del módulo.
_CRT4_EXPECTED_LINE = "CRT=1,CRT1P1,CRT2C1,CRT3P2,"
_CRT4_TARGET_LINE = "CRT=4,CRT1P1,CRT2C1,CRT3C1,CRT4C1,"


def _apply_crt4(text: str) -> tuple[str, bool]:
    """Busca una línea que sea EXACTAMENTE `_CRT4_EXPECTED_LINE` y la
    reemplaza entera por `_CRT4_TARGET_LINE` (conservando el salto de
    línea original, \\r\\n o \\n). Devuelve `(texto_actualizado, True)` si
    se aplicó, o `(texto_original, False)` si no se encontró esa línea
    exacta (por ejemplo, porque ya se había aplicado CRT 2 antes en la
    misma corrida, o porque esta estación no tenía el valor de fábrica
    esperado) -- el llamador decide cómo avisar (ver `apply_udf_configuration`,
    que lanza `SharesConfigError` en vez de seguir en silencio como el
    VB.NET original)."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if stripped == _CRT4_EXPECTED_LINE:
            ending = line[len(stripped):]
            lines[i] = _CRT4_TARGET_LINE + ending
            return "".join(lines), True
    return text, False


def apply_udf_configuration(
    ciudad: str,
    lniata_crt: str = "",
    crt_enabled: bool = False,
    lniata_atb: str = "",
    atb_enabled: bool = False,
    lniata_btp: str = "",
    btp_enabled: bool = False,
    lniata_dcp: str = "",
    dcp_enabled: bool = False,
    bgr_enabled: bool = False,
    ocr_enabled: bool = False,
    crt2_enabled: bool = False,
    crt4_enabled: bool = False,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> str:
    """Edita `<base_dir>/<ciudad>/UDF/LTPCMUDF.INF` (ver el docstring del
    módulo para el detalle de cada línea). Se asume que
    `apply_shares_configuration()` ya corrió antes, por eso la carpeta se
    busca directamente con el nombre de CIUDAD (no "PTY").

    LNIATA CRT, ATB, BTP y DCP solo se aplican si su respectiva casilla
    está marcada (`crt_enabled` / `atb_enabled` / `btp_enabled` /
    `dcp_enabled`); si no está marcada, esas líneas no se tocan en
    absoluto (quedan como estaban) — esto incluye el puerto fijo de cada
    sesión (ATB1PORT=COM7, BTP1PORT=COM8, DCP1PORT=COM10), que solo se
    valida/corrige cuando esa sesión está marcada.

    `bgr_enabled` / `ocr_enabled` activan BGR=1 / OCR=1 (casillas simples,
    sin campo asociado). `crt2_enabled` / `crt4_enabled` corrigen la línea
    `CRT=...` al número de pantallas correspondiente (ver docstring del
    módulo) — se espera que el panel las mantenga mutuamente excluyentes
    (`app/ui/shares_config_panel.py`), pero si igual llegaran las dos
    marcadas, se aplica primero CRT 2 y después CRT 4 (fallando con
    `SharesConfigError` en el segundo paso, ya que CRT 2 ya habría dejado
    la línea en un valor distinto al que CRT 4 espera).

    Lanza `SharesConfigError` si el archivo no aparece donde se espera, si
    alguna de las líneas requeridas no tiene el formato esperado, o si
    alguno de los LNIATA está marcado pero su campo está vacío."""
    ciudad = (ciudad or "").strip()
    lniata_crt = (lniata_crt or "").strip()
    lniata_atb = (lniata_atb or "").strip()
    lniata_btp = (lniata_btp or "").strip()
    lniata_dcp = (lniata_dcp or "").strip()

    if not ciudad:
        raise SharesConfigError("El campo CIUDAD está vacío — hace falta para ubicar la carpeta UDF.")

    udf_file = Path(base_dir) / ciudad / "UDF" / "LTPCMUDF.INF"
    if not udf_file.exists():
        raise SharesConfigError(f"No se encontró el archivo '{udf_file}'.")

    with udf_file.open("r", encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()

    updated_fields: list[str] = []

    if crt_enabled:
        if not lniata_crt:
            raise SharesConfigError("LNIATA CRT está marcado pero el campo está vacío.")
        text, group_updated = _apply_group_line(text, lniata_crt)
        if not group_updated:
            raise SharesConfigError(
                f"No se encontró la línea GROUP=... esperada {_UDF_ANCHOR_OFFSET} líneas debajo de "
                f"\"{_UDF_ANCHOR_TEXT}\" en '{udf_file}'."
            )
        updated_fields.append("GROUP")

    text, location_hits = _LOCATION_PATTERN.subn(lambda m: m.group(1) + ciudad, text)
    if location_hits == 0:
        raise SharesConfigError(f"No se encontró ninguna línea 'LOCATION=...' en '{udf_file}'.")
    updated_fields.append("LOCATION")

    sessions = [
        ("ATB", lniata_atb, atb_enabled),
        ("BTP", lniata_btp, btp_enabled),
        ("DCP", lniata_dcp, dcp_enabled),
    ]
    for suffix, lniata_value, enabled in sessions:
        if enabled:
            if not lniata_value:
                raise SharesConfigError(f"LNIATA {suffix} está marcado pero el campo está vacío.")
            text, flag_hits = _flag_pattern(suffix).subn(lambda m: m.group(1) + "1" + m.group(3), text)
            if flag_hits == 0:
                raise SharesConfigError(f"No se encontró ninguna línea '{suffix}=...' en '{udf_file}'.")
            text, lniata_hits = _lniata_value_pattern(suffix).subn(lambda m: m.group(1) + lniata_value, text)
            if lniata_hits == 0:
                raise SharesConfigError(f"No se encontró ninguna línea '{suffix}1LNIATA=...' en '{udf_file}'.")
            updated_fields.append(suffix)
            updated_fields.append(f"{suffix}1LNIATA")

            port_target = _SESSION_PORTS[suffix]
            text, port_hits = _port_pattern(suffix).subn(lambda m: m.group(1) + port_target, text)
            if port_hits == 0:
                raise SharesConfigError(f"No se encontró ninguna línea '{suffix}1PORT=...' en '{udf_file}'.")
            updated_fields.append(f"{suffix}1PORT")

    for key, enabled in (("BGR", bgr_enabled), ("OCR", ocr_enabled)):
        if enabled:
            text, hits = _simple_activation_pattern(key).subn(lambda m: m.group(1) + "1" + m.group(3), text)
            if hits == 0:
                raise SharesConfigError(f"No se encontró ninguna línea '{key}=...' en '{udf_file}'.")
            updated_fields.append(key)

    if crt2_enabled:
        text, crt2_hits = _CRT_COUNT_PATTERN.subn(lambda m: m.group(1) + "2" + m.group(3), text)
        if crt2_hits == 0:
            raise SharesConfigError(f"No se encontró ninguna línea 'CRT=...' en '{udf_file}'.")
        updated_fields.append("CRT2")

    if crt4_enabled:
        text, crt4_applied = _apply_crt4(text)
        if not crt4_applied:
            raise SharesConfigError(
                f"No se encontró la línea de fábrica esperada '{_CRT4_EXPECTED_LINE}' en '{udf_file}' -- "
                "revisa manualmente la línea CRT=... de este archivo."
            )
        updated_fields.append("CRT4")

    with udf_file.open("w", encoding="utf-8", newline="") as f:
        f.write(text)

    return f"UDF: {udf_file} ({', '.join(updated_fields)})"


def _apply_group_line(text: str, lniata_crt: str) -> tuple[str, bool]:
    """Busca el comentario ancla y, `_UDF_ANCHOR_OFFSET` líneas debajo, la
    línea GROUP=...; reemplaza el valor entre comas por `lniata_crt`, sin
    tocar el resto de la línea (incluida su terminación \\r\\n / \\n
    original). Devuelve `(texto_actualizado, True)` si se aplicó el
    cambio, o `(texto_original, False)` si no se encontró la estructura
    esperada."""
    lines = text.splitlines(keepends=True)
    anchor_index = next((i for i, line in enumerate(lines) if _UDF_ANCHOR_TEXT in line), None)
    if anchor_index is None:
        return text, False

    target_index = anchor_index + _UDF_ANCHOR_OFFSET
    if target_index >= len(lines):
        return text, False

    raw_line = lines[target_index]
    stripped = raw_line.rstrip("\r\n")
    ending = raw_line[len(stripped):]

    match = _GROUP_LINE_PATTERN.match(stripped)
    if match is None:
        return text, False

    lines[target_index] = match.group(1) + lniata_crt + match.group(3) + ending
    return "".join(lines), True


# --------------------------------------------------------------------------
# Tercera parte: CONTINGENCIA -- a diferencia de todo lo de arriba, esto no
# edita ningún archivo de configuración: corre `Contingencia.bat` como
# proceso externo. Por eso su ruta es relativa a `installers_base_path` (la
# carpeta de instaladores del catálogo LTP / CSS), no a `base_dir`.
# --------------------------------------------------------------------------

# Ruta del script, relativa a `installers_base_path`.
CONTINGENCIA_SCRIPT_REL = r"LTP TRAVEL DOC\Contingencia.bat"

# Mismo criterio que `app/installer.py`: 3010 = éxito, requiere reinicio.
_CONTINGENCIA_SUCCESS_CODES = {0, 3010}


def run_contingencia_script(installers_base_path: str) -> str:
    """Corre `Contingencia.bat` (ver `CONTINGENCIA_SCRIPT_REL`) dentro de la
    carpeta de instaladores del catálogo LTP / CSS (`installers_base_path`).

    A diferencia de `apply_shares_configuration()` / `apply_udf_configuration()`
    (que editan archivos directamente y no pueden "fallar" en tiempo de
    ejecución en el sentido de un proceso externo), esto sí lanza un proceso
    y hay que esperar su resultado -- mismo criterio de éxito que el resto
    del catálogo (`installer.py`: código 0 o 3010).

    Devuelve un mensaje corto de éxito para mostrar en el estado de la
    pantalla. Lanza `SharesConfigError` si el script no existe, se agota el
    tiempo de espera, no se pudo ejecutar, o termina con un código de salida
    que no sea de éxito -- el llamador decide cómo mostrarlo (igual que el
    resto de errores de esta pantalla)."""
    script_path = Path(installers_base_path) / CONTINGENCIA_SCRIPT_REL
    if not script_path.exists():
        raise SharesConfigError(f"No se encontró el script de Contingencia en: {script_path}")

    try:
        result = subprocess.run(
            [str(script_path)],
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            timeout=10 * 60,  # 10 minutos
        )
    except subprocess.TimeoutExpired:
        raise SharesConfigError(f"Tiempo de espera agotado (10 min) al correr '{script_path}'.")
    except OSError as exc:
        raise SharesConfigError(f"No se pudo ejecutar '{script_path}': {exc}")

    if result.returncode not in _CONTINGENCIA_SUCCESS_CODES:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        msg = f"Contingencia.bat terminó con código de salida {result.returncode}"
        if detail:
            msg += f" -- {detail}"
        raise SharesConfigError(msg)

    detail = f"código de salida {result.returncode}"
    if result.returncode == 3010:
        detail += " (requiere reinicio)"
    return f"Contingencia: {script_path} ({detail})"
