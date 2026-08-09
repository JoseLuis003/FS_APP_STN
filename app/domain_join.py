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


def join_domain(current_name: str, new_name: str, ou_dn: str, username: str, password: str) -> None:
    """Une el equipo al dominio `copaair.com`, en la OU indicada
    (`ou_dn`, uno de los valores de `OU_OPTIONS`), renombrándolo en el mismo
    paso si `new_name` es distinto de `current_name`.

    Lanza `BadCredentialsError` si el usuario/contraseña son incorrectos
    (la UI debe pedir que se vuelvan a ingresar), o `DomainJoinError` para
    cualquier otro problema (OU inválida, sin conexión al dominio, nombre
    de equipo duplicado, etc.)."""
    args = [
        "-DomainName", DOMAIN_NAME,
        "-OUPath", ou_dn,
        "-Username", full_username(username),
    ]
    target_name = (new_name or "").strip()
    if target_name and target_name.upper() != (current_name or "").strip().upper():
        args += ["-NewName", target_name]

    result = _run_powershell_script("join_domain.ps1", args, stdin_text=(password or "") + "\n")
    _interpret_result(result, "No se pudo unir el equipo al dominio")


def apply_post_join_setup() -> None:
    """Agrega los grupos de soporte (`LOCAL_ADMIN_GROUPS`) al grupo local
    Administrators y limpia el autologon local. Se corre DESPUÉS de que
    `join_domain()` ya validó las credenciales y unió el equipo -- si este
    paso falla, el equipo de todos modos ya quedó unido al dominio, así que
    la UI lo debe mostrar como advertencia y no como fallo total."""
    args = ["-AdminGroups", *LOCAL_ADMIN_GROUPS]
    result = _run_powershell_script("post_join_setup.ps1", args)
    _interpret_result(result, "No se pudo completar la configuración posterior a la unión al dominio")
