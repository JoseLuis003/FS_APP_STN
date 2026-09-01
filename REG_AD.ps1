# REG_AD.ps1
# ----------
# Se corre como el ÚLTIMO paso del ítem "REGISTRO EN AD" (config/apps.json),
# DESPUÉS de:
#   1. El hotfix WindowsTH-KB2693643-x64.msu (paso principal del ítem).
#   2. El paso "rsat_ad_tools_setup" (ver app/rsat_setup.py) -- instala RSAT
#      (el módulo de PowerShell "ActiveDirectory" que usan los cmdlets de
#      abajo) desde los archivos locales que vienen junto a los demás
#      instaladores, nunca desde Windows Update.
#
# Registra el equipo en Active Directory:
#   1. "ManagedBy" del objeto de equipo <- el usuario de dominio que corre
#      FS_APP_STN.exe en este momento (ver más abajo).
#   2. "Description" del objeto de equipo <- el número de serie del equipo.
#
# CAMBIOS respecto del script original (corregidos a pedido explícito):
#
# - Se quitó `PowerShell Set-ExecutionPolicy RemoteSigned`: lanzaba un
#   SEGUNDO proceso de PowerShell desde adentro de este script, innecesario
#   (FS_APP_STN.exe ya invoca este .ps1 con `-ExecutionPolicy Bypass`, ver
#   `_resolve_step_command` en app/installer.py) y riesgoso -- sin `-Force`,
#   `Set-ExecutionPolicy` puede mostrar un aviso de confirmación que se
#   queda esperando una respuesta que nunca llega en una ejecución
#   desatendida (este script no tiene consola interactiva -- corre con
#   `capture_output=True` desde Python), colgando el paso hasta agotar el
#   timeout de 30 minutos.
#
# - Se quitó `Add-WindowsCapability -Name Rsat.ActiveDirectory.DS-LDS.Tools
#   ... -Online`: quedó redundante -- ahora RSAT se instala en su PROPIO
#   paso (`rsat_ad_tools_setup`, ANTES que este script, ver
#   app/rsat_setup.py) usando `dism.exe /Add-Capability` con los .cab
#   locales (`-LimitAccess`, nunca Windows Update). La versión que tenía
#   este script (`-Online` sin `-Source`/`-LimitAccess`) intentaría salir a
#   Windows Update directo -- muchas estaciones de Copa no tienen esa
#   salida a internet.
#
# - Se quitó el `Read-Host` interactivo que pedía el usuario por teclado:
#   este script corre de forma DESATENDIDA (sin consola para que el técnico
#   escriba una respuesta), así que `Read-Host` se quedaría esperando para
#   siempre hasta agotar el timeout del paso.
#
# - CAMBIO (pedido explícito de campo, revisado): el usuario para
#   "ManagedBy" YA NO se toma de `$env:USERNAME` -- en la práctica esa era
#   la cuenta local GENÉRICA con la que corre FS_APP_STN.exe (ej. "CM"), no
#   el usuario final que va a ser dueño del equipo, así que "ManagedBy"
#   quedaba mal asignado en AD. Ahora la pantalla APPS tiene un campo de
#   texto al lado de esta casilla (`self.owner_user_edit`, ver
#   `REGISTRO_AD_ITEM_ID` en `app/ui/main_window.py`) donde el técnico
#   escribe el usuario de dominio real del dueño (ej. "jperez") -- ese
#   valor le llega a este script en la variable de entorno
#   `FS_APP_STN_AD_OWNER_USER` (`subprocess.run`, que usa `InstallWorker`
#   para correr este paso, hereda el entorno del proceso padre, así que no
#   hace falta pasarlo como argumento de línea de comandos). Si por algún
#   motivo esa variable no estuviera (ej. alguien corre este script a mano,
#   fuera de la app), se cae de vuelta a `$env:USERNAME` como antes -- para
#   no depender de un solo mecanismo y dejar el registro de AD sin hacer.
#
# - `Get-WmiObject` (obsoleto) reemplazado por `Get-CimInstance` -- mismo
#   cmdlet que ya usa `get_serial_number()` en app/report.py, para que el
#   número de serie salga siempre igual en toda la app.
#
# - Se agregó manejo de errores explícito (`$ErrorActionPreference = "Stop"`
#   + try/catch + `exit 0`/`exit 1`): antes, si `Get-ADUser` no encontraba
#   el usuario, o el equipo no estaba unido al dominio, o faltaban permisos,
#   el script podía terminar con un código de salida ambiguo. Ahora
#   cualquier error se manda a stderr (queda en el log de instalación,
#   `logs/install_<fecha>.log`) y el paso queda marcado como fallo real, en
#   vez de reportarse como éxito sin haber registrado nada.

$ErrorActionPreference = "Stop"

try {
    $usuario = $env:FS_APP_STN_AD_OWNER_USER
    if ([string]::IsNullOrWhiteSpace($usuario)) {
        $usuario = $env:USERNAME
    }
    $computer = $env:COMPUTERNAME

    $mgr = Get-ADUser -Identity $usuario -Server copaair.com
    Get-ADComputer -Identity $computer -Server copaair.com | Set-ADComputer -ManagedBy $mgr

    $sn = (Get-CimInstance -ClassName Win32_BIOS).SerialNumber
    Set-ADComputer -Identity $computer -Server copaair.com -Description $sn

    Write-Output "Equipo '$computer' registrado en AD -- ManagedBy: $usuario, Description: $sn"
    exit 0
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
