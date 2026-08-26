[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DomainName,
    [Parameter(Mandatory = $true)][string]$ComputerDN,
    [Parameter(Mandatory = $true)][string]$Username,
    [Parameter(Mandatory = $true)][string]$Description
)

# set_computer_description.ps1
# -----------------------------
# Pedido explícito: al unir el equipo al dominio, dejar el número de serie
# del equipo (mismo valor que ya usa la app en el reporte y en Copa ID /
# Asset Tag, ver `app.report.get_serial_number`) en el campo "Description"
# del objeto de equipo en Active Directory -- así el equipo de soporte lo
# puede ver directo en Active Directory Users and Computers sin tener que
# abrir el equipo físicamente.
#
# `Add-Computer` (join_domain.ps1) NO tiene un parámetro `-Description`, y
# `Set-ADComputer` (el cmdlet obvio para esto) requiere el módulo RSAT de
# Active Directory, que NO está instalado en un equipo recién provisionado
# (mismo motivo por el que list_ous.ps1 / check_computer_name.ps1 usan
# ADSI en vez del módulo ActiveDirectory) -- así que este script hace el
# mismo tipo de bind directo por ADSI (`System.DirectoryServices.
# DirectoryEntry`) que esos 2 scripts, mismo patrón "delgado":
#   1) Lee la contraseña desde stdin (nunca por argumento).
#   2) Se conecta directo al objeto de equipo por su DN completo
#      (`$ComputerDN`, ej. "CN=EQUIPO01,OU=...,DC=copaair,DC=com" -- lo arma
#      Python en `apply_computer_description()`, uniendo el nombre final
#      del equipo con el DN de la OU elegida) y le pone el valor de
#      `$Description` en el atributo `description`.
#   3) Imprime exactamente una de estas líneas y termina con el código de
#      salida correspondiente, igual que los demás scripts de esta carpeta:
#        RESULT_OK
#        RESULT_BAD_CREDENTIALS
#        RESULT_ERROR: <detalle>
#
# IMPORTANTE (riesgo conocido, sin resolver a propósito en esta primera
# versión): este script se corre INMEDIATAMENTE después de que
# `join_domain.ps1` (Add-Computer) creó el objeto de equipo en Active
# Directory. En un dominio con más de un controlador de dominio, es
# posible que el controlador contra el que este script termine
# conectándose todavía no haya recibido la replicación de ese objeto
# recién creado, y el bind por DN falle con "no se pudo encontrar el
# objeto" aunque el equipo sí quedó unido correctamente. Se decidió, a
# propósito, NO agregar lógica de reintento para esta primera versión (para
# no complicar el script) -- si pasa, el resultado es una advertencia NO
# bloqueante (ver `apply_computer_description` en app/domain_join.py): el
# equipo de todos modos ya quedó unido al dominio, y el campo Description
# se puede completar manualmente después.

$ErrorActionPreference = "Stop"
$password = $null
$securePassword = $null
$credential = $null
$directoryEntry = $null

function Test-BadCredentialsError {
    # Mismo criterio que check_computer_name.ps1 / list_ous.ps1: un bind
    # ADSI fallido por credenciales incorrectas lanza
    # DirectoryServicesCOMException (hereda de COMException), no
    # Win32Exception.
    param([System.Exception]$Exception)
    $current = $Exception
    while ($null -ne $current) {
        if ($current -is [System.ComponentModel.Win32Exception] -and $current.NativeErrorCode -eq 1326) {
            return $true
        }
        if ($current -is [System.Runtime.InteropServices.COMException]) {
            if (($current.ErrorCode -band 0xFFFF) -eq 1326) {
                return $true
            }
            if ($current -is [System.DirectoryServices.DirectoryServicesCOMException] -and
                $current.ExtendedErrorMessage -match "data 52e") {
                return $true
            }
        }
        $current = $current.InnerException
    }
    return $false
}

try {
    $password = [Console]::In.ReadLine()
    if ([string]::IsNullOrEmpty($password)) {
        Write-Output "RESULT_ERROR: No se recibio la contrasena por stdin."
        exit 1
    }

    $ldapPath = "LDAP://$DomainName/$ComputerDN"
    $directoryEntry = New-Object System.DirectoryServices.DirectoryEntry($ldapPath, $Username, $password)
    # Fuerza la validación de credenciales/la existencia del objeto acá
    # (ADSI no valida nada hasta el primer acceso real) -- mismo criterio
    # que check_computer_name.ps1 / list_ous.ps1.
    $directoryEntry.RefreshCache()

    $directoryEntry.Properties["description"].Clear()
    $directoryEntry.Properties["description"].Add($Description) | Out-Null
    $directoryEntry.CommitChanges()

    Write-Output "RESULT_OK"
    exit 0
}
catch {
    $ex = $_.Exception
    if (Test-BadCredentialsError -Exception $ex) {
        Write-Output "RESULT_BAD_CREDENTIALS"
        exit 1
    }
    $detail = $ex.Message -replace "[\r\n]+", " "
    Write-Output "RESULT_ERROR: $detail"
    exit 1
}
finally {
    # Limpieza de variables sensibles en memoria -- mismo criterio que
    # join_domain.ps1 / list_ous.ps1 / check_computer_name.ps1.
    $password = $null
    if ($null -ne $securePassword) { $securePassword.Dispose() }
    $securePassword = $null
    $credential = $null
    if ($null -ne $directoryEntry) { $directoryEntry.Dispose() }
    [System.GC]::Collect()
}
