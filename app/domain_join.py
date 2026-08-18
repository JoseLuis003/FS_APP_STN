"""Lógica de unión al dominio "copaair.com" (botón DOMINIO).

Emula lo que hacía `DomainJoined.ps1` (script de PowerShell que el equipo de
soporte ya usaba), pero de forma más robusta:

- El script original nunca asignaba la variable `$credentials` que usaba en
  `Add-Computer`, así que jamás pedía usuario/contraseña de verdad y —peor—
  si la unión al dominio fallaba igual seguía con los pasos siguientes
  (grupos locales, limpiar autologon, reiniciar). Acá cada paso se detiene
  si el anterior falló.
- Distingue "usuario o contraseña incorrectos" (para que la UI le pida al
  técnico que vuelva a escribirlas) de cualquier otro error (OU inválida,
  sin red, nombre de equipo duplicado, etc.), algo que el script original no
  hacía en absoluto.
- El nombre de grupo con espacios (`COPAAIR\\GRP-Soporte Copa Panama`) se
  pasa como un solo argumento, no como texto suelto sin comillas -- el
  script original tenía ese bug y `Add-LocalGroupMember` habría fallado al
  interpretar "Copa" y "Panama" como argumentos aparte.

Toda la lógica de reintentos y de qué mostrarle al técnico vive en Python
(ver `app/ui/dominio_window.py`); este módulo solo orquesta la ejecución de
los dos scripts de PowerShell "delgados" en `scripts/` (`join_domain.ps1` y
`post_join_setup.ps1`), que se comunican con Python mediante líneas de
resultado en stdout:

    RESULT_OK
    RESULT_BAD_CREDENTIALS
    RESULT_ERROR: <detalle>

Seguridad: la contraseña de dominio NUNCA se pasa como argumento de línea de
comandos (quedaría visible en el Administrador de tareas) ni se guarda en
`config/settings.json` ni en ningún otro archivo -- se le pasa al script de
PowerShell únicamente por stdin, y el técnico la vuelve a escribir cada vez.
"""
from __future__ import annotations

import subprocess

from app.config import SCRIPTS_DIR

DOMAIN_NAME = "copaair.com"

# El técnico solo escribe su usuario (ej. "jperez"); el prefijo de dominio
# se muestra fijo en la UI y se antepone acá, para que no haya errores de
# formato ni que el técnico tenga que acordarse de escribirlo.
USERNAME_DOMAIN_PREFIX = "copaair\\"

# (etiqueta mostrada en el combo, DN completo) -- mismas 5 opciones y mismos
# DN que el script original, en el mismo orden (1-5).
OU_OPTIONS: list[tuple[str, str]] = [
    ("ATO-BCK", "OU=BACK OFFICE,OU=ESTACIONES ATO,OU=Workstations_Estaciones,OU=Workstations_Copa,DC=copaair,DC=com"),
    (
        "ATO-COU-GTE",
        "OU=OPERATIVOS (CHK\\, GTE),OU=ESTACIONES ATO,OU=Workstations_Estaciones,OU=Workstations_Copa,DC=copaair,DC=com",
    ),
    ("CGO", "OU=ESTACIONES CGO,OU=Workstations_Estaciones,OU=Workstations_Copa,DC=copaair,DC=com"),
    ("CTO", "OU=ESTACIONES CTO,OU=Workstations_Estaciones,OU=Workstations_Copa,DC=copaair,DC=com"),
    ("MTO", "OU=ESTACIONES MTO,OU=Workstations_Estaciones,OU=Workstations_Copa,DC=copaair,DC=com"),
]

# Rama del árbol de AD bajo la que se buscan las OUs cuando el técnico
# presiona "Cargar OUs desde AD" (ver `fetch_ou_list_from_ad` /
# `scripts/list_ous.ps1`) -- la misma rama común a las 5 opciones fijas de
# arriba, no todo el dominio (que traería OUs de usuarios, servidores,
# etc. sin relación con estaciones).
OU_SEARCH_BASE_DN = "OU=Workstations_Copa,DC=copaair,DC=com"

# Grupos que se agregan al grupo local Administrators una vez unido al
# dominio -- cada elemento se pasa como UN SOLO argumento (ver
# `apply_post_join_setup`), a diferencia del script original que los pasaba
# sin comillas y por eso fallaba.
LOCAL_ADMIN_GROUPS: list[str] = [
    "COPAAIR\\GRP-Soporte Copa Panama",
    "COPAAIR\\GRP-Soporte Copa Estaciones",
]

_POWERSHELL_TIMEOUT_SECONDS = 120


class DomainJoinError(Exception):
    """Error al unir el equipo al dominio, o en los pasos posteriores
    (grupos locales, autologon). El mensaje ya viene listo para mostrarle al
    técnico."""


class BadCredentialsError(DomainJoinError):
    """El usuario o la contraseña de dominio son incorrectos. Se distingue
    del resto de errores (`DomainJoinError`) porque la UI debe pedirle al
    técnico que vuelva a ingresar sus credenciales, en vez de mostrar un
    error genérico y darse por vencida."""


class ComputerNameExistsError(DomainJoinError):
    """Ya existe en Active Directory un objeto de equipo con el nombre
    elegido -- ver `check_computer_name_available()`. Se distingue del
    resto de errores porque la UI debe mostrar la explicación completa
    (causa real + las 3 opciones del técnico) en vez de un mensaje
    genérico, y porque este error se detecta ANTES de intentar
    `Add-Computer` -- el equipo nunca llega a unirse al dominio con el
    nombre genérico de Windows cuando pasa esto (a diferencia del bug
    real que motivó este chequeo, ver el docstring de
    `check_computer_name_available`)."""


def full_username(username: str) -> str:
    """Antepone "copaair\\" al usuario que escribe el técnico. Si el
    técnico ya escribió el dominio de alguna forma (`copaair\\usuario` o
    `usuario@copaair.com`), se respeta tal cual en vez de duplicarlo."""
    username = (username or "").strip()
    if "\\" in username or "@" in username:
        return username
    return f"{USERNAME_DOMAIN_PREFIX}{username}"


def _run_powershell_script(
    script_name: str,
    args: list[str],
    stdin_text: str | None = None,
    timeout: int = _POWERSHELL_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess:
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        raise DomainJoinError(f"No se encontró el script '{script_name}' en {SCRIPTS_DIR}.")

    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path), *args]
    try:
        return subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise DomainJoinError("No se encontró PowerShell en este equipo.") from exc
    except subprocess.TimeoutExpired as exc:
        raise DomainJoinError(f"Tiempo de espera agotado ejecutando '{script_name}'.") from exc
    except OSError as exc:
        raise DomainJoinError(f"No se pudo ejecutar '{script_name}': {exc}") from exc


def _interpret_result(result: subprocess.CompletedProcess, generic_error_prefix: str) -> None:
    """Busca la línea de resultado (`RESULT_OK` / `RESULT_BAD_CREDENTIALS` /
    `RESULT_ERROR: ...`) en la salida del script y actúa en consecuencia. Si
    no aparece ninguna (el script se rompió antes de llegar a imprimirla),
    arma un mensaje de error con lo que haya en stderr/stdout."""
    stdout = result.stdout or ""
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line == "RESULT_OK":
            return
        if line == "RESULT_BAD_CREDENTIALS":
            raise BadCredentialsError("El usuario o la contraseña no son correctos.")
        if line.startswith("RESULT_ERROR:"):
            detail = line[len("RESULT_ERROR:"):].strip()
            raise DomainJoinError(detail or generic_error_prefix)

    detail = (result.stderr or stdout or "").strip()
    suffix = f": {detail}" if detail else ""
    raise DomainJoinError(f"{generic_error_prefix}{suffix} (código de salida {result.returncode}).")


def _interpret_name_check_result(result: subprocess.CompletedProcess, computer_name: str) -> None:
    """Interpreta la salida de `check_computer_name.ps1`: junta las líneas
    `NAME_EXISTS|<DN>` (normalmente a lo sumo una, el nombre es único en
    el dominio, pero se juntan todas por si acaso) y, al llegar a
    `RESULT_OK`, lanza `ComputerNameExistsError` si se encontró alguna --
    con el DN encontrado y la explicación completa de la causa real (ver
    `check_computer_name_available`). Si no se encontró ninguna, no hace
    nada (el nombre está libre para usarse)."""
    stdout = result.stdout or ""
    found_dns: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line == "RESULT_OK":
            if not found_dns:
                return
            dn_list = "\n".join(f"  - {dn}" for dn in found_dns)
            raise ComputerNameExistsError(
                f"El nombre '{computer_name}' ya existe en Active Directory:\n{dn_list}\n\n"
                "Esto NO es un problema de este equipo ni de esta app: desde octubre de 2022, "
                "Windows bloquea por seguridad la reutilización de una cuenta de equipo ya "
                "existente (KB5020276, \"Netjoin: Domain join hardening changes\"), a menos que "
                "quien haga la unión sea quien creó esa cuenta originalmente, sea Domain/Enterprise "
                "Admin, o el dueño de esa cuenta tenga permitida la reutilización vía la directiva "
                "\"Domain controller: Allow computer account reuse during domain join\".\n\n"
                "Opciones:\n"
                "  1. Pide al equipo de Active Directory que elimine ese objeto (si es de un equipo "
                "anterior que ya no existe).\n"
                "  2. Vuelve a intentar con las credenciales de quien creó esa cuenta originalmente.\n"
                "  3. Usa un nombre distinto para este equipo."
            )
        if line == "RESULT_BAD_CREDENTIALS":
            raise BadCredentialsError("El usuario o la contraseña no son correctos.")
        if line.startswith("RESULT_ERROR:"):
            detail = line[len("RESULT_ERROR:"):].strip()
            raise DomainJoinError(detail or f"No se pudo validar si el nombre '{computer_name}' ya existe en AD.")
        if line.startswith("NAME_EXISTS|"):
            _, _, dn = line.partition("|")
            if dn:
                found_dns.append(dn)

    detail = (result.stderr or stdout or "").strip()
    suffix = f": {detail}" if detail else ""
    raise DomainJoinError(
        f"No se pudo validar si el nombre '{computer_name}' ya existe en Active Directory{suffix} "
        f"(código de salida {result.returncode})."
    )


def check_computer_name_available(computer_name: str, username: str, password: str) -> None:
    """Confirma que NO exista ya en Active Directory un objeto de equipo
    con `computer_name` -- se corre ANTES de `join_domain()` para evitar
    un bug real reportado en campo: unir el equipo con `Add-Computer
    -NewName` cuando el nombre deseado YA existía en AD terminaba
    "funcionando a medias" -- el equipo SÍ quedaba unido al dominio, pero
    con el nombre genérico de Windows (ej. "DESKTOP-XXXXX"), porque el
    renombrado (parte del mismo comando) fallaba con "The account
    already exists" -- y encima se le mostraba al técnico como un fallo
    total, sin avisarle que el equipo ya había quedado unido (con el
    nombre incorrecto).

    Importante: renombrar el equipo LOCALMENTE antes de unirlo (en vez de
    dejar que `Add-Computer -NewName` lo haga en el mismo paso) NO
    evita este bloqueo -- la causa real no es el orden de las
    operaciones. Desde octubre de 2022, Windows bloquea por seguridad
    reutilizar una cuenta de equipo ya existente en AD (KB5020276,
    "Netjoin: Domain join hardening changes"), sin importar si el intento
    de unión llega con el nombre ya puesto localmente o lo cambia en el
    mismo paso -- en ambos casos, el Controlador de Dominio rechaza la
    reutilización igual si quien se está uniendo no es el creador
    original de esa cuenta (o Domain/Enterprise Admin, o tiene la
    directiva de grupo correspondiente). Por eso este chequeo no intenta
    "arreglar" nada por su cuenta (no borra ni resetea el objeto
    encontrado -- sería una operación destructiva sobre AD sin
    intervención humana) -- solo detecta el conflicto ANTES de intentar
    `Add-Computer`, para que el equipo nunca llegue a unirse con el
    nombre genérico, y le explica al técnico la causa real y sus 3
    opciones (ver `_interpret_name_check_result`).

    Lanza `ComputerNameExistsError` si el nombre ya existe,
    `BadCredentialsError` si el usuario/contraseña son incorrectos, o
    `DomainJoinError` para cualquier otro problema (sin red, etc.). No
    devuelve nada si el nombre está libre."""
    args = [
        "-DomainName", DOMAIN_NAME,
        "-ComputerName", computer_name,
        "-Username", full_username(username),
    ]
    result = _run_powershell_script("check_computer_name.ps1", args, stdin_text=(password or "") + "\n")
    _interpret_name_check_result(result, computer_name)


def join_domain(current_name: str, new_name: str, ou_dn: str, username: str, password: str) -> None:
    """Une el equipo al dominio `copaair.com`, en la OU indicada
    (`ou_dn`, uno de los valores de `OU_OPTIONS`), renombrándolo en el mismo
    paso si `new_name` es distinto de `current_name`.

    Antes de intentar `Add-Computer`, valida con
    `check_computer_name_available()` que el nombre final (el nuevo si se
    va a renombrar, o el actual si no) no exista ya en Active Directory --
    ver el docstring de esa función para el bug real que esto evita.

    Lanza `ComputerNameExistsError` si ese nombre ya existe en AD,
    `BadCredentialsError` si el usuario/contraseña son incorrectos (la UI
    debe pedir que se vuelvan a ingresar), o `DomainJoinError` para
    cualquier otro problema (OU inválida, sin conexión al dominio, etc.)."""
    target_name = (new_name or "").strip() or (current_name or "").strip()

    check_computer_name_available(target_name, username, password)

    args = [
        "-DomainName", DOMAIN_NAME,
        "-OUPath", ou_dn,
        "-Username", full_username(username),
    ]
    if target_name and target_name.upper() != (current_name or "").strip().upper():
        args += ["-NewName", target_name]

    result = _run_powershell_script("join_domain.ps1", args, stdin_text=(password or "") + "\n")
    _interpret_result(result, "No se pudo unir el equipo al dominio")


def _interpret_ou_list_result(result: subprocess.CompletedProcess) -> list[tuple[str, str]]:
    """Interpreta la salida de `list_ous.ps1`: junta las líneas
    `OU|<nombre>|<DN>` en la lista de resultado, y busca la misma línea
    RESULT_* que usa `join_domain.ps1` (ver `_interpret_result`) para
    reaccionar igual ante credenciales inválidas o cualquier otro error.

    Si `RESULT_OK` llega sin haber juntado ninguna línea `OU|...|...`,
    se trata como error igual -- lo más probable es que `OU_SEARCH_BASE_DN`
    ya no sea correcto (o el técnico no tenga permiso de lectura ahí), y
    dejar el combo vacío sería peor que avisarle."""
    stdout = result.stdout or ""
    ou_options: list[tuple[str, str]] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line == "RESULT_OK":
            if not ou_options:
                raise DomainJoinError(
                    f"No se encontró ninguna OU bajo '{OU_SEARCH_BASE_DN}' -- revisa la "
                    "conexión al dominio, o si esa ruta del árbol de AD sigue siendo correcta."
                )
            return ou_options
        if line == "RESULT_BAD_CREDENTIALS":
            raise BadCredentialsError("El usuario o la contraseña no son correctos.")
        if line.startswith("RESULT_ERROR:"):
            detail = line[len("RESULT_ERROR:"):].strip()
            raise DomainJoinError(detail or "No se pudo leer la lista de OUs desde Active Directory.")
        if line.startswith("OU|"):
            parts = line.split("|", 2)
            if len(parts) == 3:
                _, name, dn = parts
                ou_options.append((name, dn))

    detail = (result.stderr or stdout or "").strip()
    suffix = f": {detail}" if detail else ""
    raise DomainJoinError(
        f"No se pudo leer la lista de OUs desde Active Directory{suffix} "
        f"(código de salida {result.returncode})."
    )


def fetch_ou_list_from_ad(username: str, password: str) -> list[tuple[str, str]]:
    """Consulta Active Directory en vivo (vía LDAP, con las mismas
    credenciales que el técnico ya escribió para unirse al dominio) y
    devuelve todas las OUs encontradas bajo `OU_SEARCH_BASE_DN`, como
    (nombre, DN completo) -- el mismo formato que `OU_OPTIONS`, para poder
    reemplazar el combo de la UI con esto en vez de la lista fija de 5.

    No requiere el módulo RSAT de Active Directory (normalmente ausente en
    un equipo recién provisionado): usa directamente las clases .NET
    `System.DirectoryServices` desde PowerShell (ver `scripts/list_ous.ps1`).

    Lanza `BadCredentialsError` si el usuario/contraseña son incorrectos, o
    `DomainJoinError` para cualquier otro problema (sin red, DN base
    incorrecto/inexistente, cero OUs encontradas, etc.)."""
    args = [
        "-DomainName", DOMAIN_NAME,
        "-BaseDN", OU_SEARCH_BASE_DN,
        "-Username", full_username(username),
    ]
    result = _run_powershell_script("list_ous.ps1", args, stdin_text=(password or "") + "\n")
    return _interpret_ou_list_result(result)


def apply_post_join_setup() -> None:
    """Agrega los grupos de soporte (`LOCAL_ADMIN_GROUPS`) al grupo local
    Administrators y limpia el autologon local. Se corre DESPUÉS de que
    `join_domain()` ya validó las credenciales y unió el equipo -- si este
    paso falla, el equipo de todos modos ya quedó unido al dominio, así que
    la UI lo debe mostrar como advertencia y no como fallo total."""
    args = ["-AdminGroups", *LOCAL_ADMIN_GROUPS]
    result = _run_powershell_script("post_join_setup.ps1", args)
    _interpret_result(result, "No se pudo completar la configuración posterior a la unión al dominio")
