[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DomainName,
    [Parameter(Mandatory = $true)][string]$OUPath,
    [Parameter(Mandatory = $true)][string]$Username,
    [Parameter(Mandatory = $false)][string]$NewName = ""
)

# join_domain.ps1
# ----------------
# Script "delgado": toda la logica de reintentos, mensajes al tecnico, etc.
# vive en Python (app/domain_join.py). Este script solo:
#   1) Lee la contrasena desde stdin (nunca por argumento de linea de
#      comandos, para que no quede visible en el Administrador de tareas ni
#      en ningun log).
#   2) Intenta Add-Computer (uniendo al dominio en la OU indicada, y
#      renombrando el equipo en el mismo paso si se indico -NewName).
#   3) Imprime EXACTAMENTE una de estas lineas a stdout y termina con el
#      codigo de salida correspondiente, para que Python interprete el
#      resultado de forma simple e independiente del idioma de Windows:
#        RESULT_OK
#        RESULT_BAD_CREDENTIALS
#        RESULT_ERROR: <detalle>
#
# La deteccion de "credenciales invalidas" usa el codigo de error nativo de
# Win32 1326 (ERROR_LOGON_FAILURE), NO el texto del mensaje de excepcion,
# porque el texto cambia segun el idioma de Windows pero el codigo no.

$ErrorActionPreference = "Stop"
$password = $null
$securePassword = $null
$credential = $null

function Test-BadCredentialsError {
    param([System.Exception]$Exception)
    $current = $Exception
    while ($null -ne $current) {
        if ($current -is [System.ComponentModel.Win32Exception] -and $current.NativeErrorCode -eq 1326) {
            return $true
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

    $securePassword = ConvertTo-SecureString -String $password -AsPlainText -Force
    $credential = New-Object System.Management.Automation.PSCredential ($Username, $securePassword)

    $addComputerParams = @{
        DomainName  = $DomainName
        Credential  = $credential
        OUPath      = $OUPath
        Force       = $true
        ErrorAction = "Stop"
    }
    if (-not [string]::IsNullOrWhiteSpace($NewName)) {
        # Add-Computer soporta renombrar el equipo en el mismo paso que lo
        # une al dominio -- evita una segunda llamada (Rename-Computer) que
        # tendria que volver a autenticarse contra el dominio.
        $addComputerParams["NewName"] = $NewName
    }

    Add-Computer @addComputerParams

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
    # Limpieza de variables sensibles en memoria -- la contrasena en texto
    # plano no debe quedar viva mas tiempo del necesario.
    $password = $null
    if ($null -ne $securePassword) { $securePassword.Dispose() }
    $securePassword = $null
    $credential = $null
    [System.GC]::Collect()
}
