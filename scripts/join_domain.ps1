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

# Caso real de campo: Add-Computer con -NewName a veces une el equipo al
# dominio CORRECTAMENTE pero el renombrado (parte del mismo comando)
# falla aparte, con un mensaje compuesto tipo: "Computer 'DESKTOP-XXXXX'
# was successfully joined to the new domain 'copaair.com', but renaming
# it to 'HDQITJB01' failed with the following error message: The
# directory service is busy." -- "the directory service is busy"
# (ERROR_DS_BUSY) es una condicion tipicamente TRANSITORIA del
# controlador de dominio (carga/replicacion justo despues de crear el
# objeto de equipo), no un fallo permanente. Antes de este cambio, este
# caso se reportaba como fallo total (`RESULT_ERROR`) sin aclarar que el
# equipo YA habia quedado unido al dominio (con el nombre generico de
# Windows) -- ver `Invoke-RenameWithRetry` mas abajo para el reintento.
#
# No usa un codigo de error nativo fijo (a diferencia de
# Test-BadCredentialsError) porque este mensaje lo compone el propio
# cmdlet de PowerShell combinando 2 resultados en un solo texto, no es un
# Win32Exception con NativeErrorCode -- se detecta por las 2 frases clave
# en ingles (los equipos de Copa corren Windows en ingles). Si algun
# equipo tuviera Windows en otro idioma y este texto no calzara, el
# comportamiento cae de vuelta al mensaje de error generico de siempre
# (no hay reintento, pero tampoco se rompe nada).
function Test-PartialJoinRenameFailure {
    param([System.Exception]$Exception)
    $current = $Exception
    while ($null -ne $current) {
        $msg = $current.Message
        if ($msg -match "(?i)successfully joined" -and $msg -match "(?i)renaming.*failed") {
            return $true
        }
        $current = $current.InnerException
    }
    return $false
}

# Reintenta Rename-Computer -- la herramienta que Microsoft documenta para
# renombrar un equipo que YA esta unido al dominio (a diferencia de
# Add-Computer -NewName, pensado para unir + renombrar en el mismo paso
# de un equipo que TODAVIA no esta en el dominio; ver
# https://learn.microsoft.com/powershell/module/microsoft.powershell.management/rename-computer).
# 3 intentos con una pausa entre uno y otro le da tiempo a la condicion
# transitoria ("the directory service is busy") a resolverse sola.
function Invoke-RenameWithRetry {
    param(
        [string]$NewName,
        [PSCredential]$Credential,
        [int]$MaxAttempts = 3,
        [int]$DelaySeconds = 10
    )
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Rename-Computer -NewName $NewName -DomainCredential $Credential -Force -ErrorAction Stop
            return $true
        }
        catch {
            if ($attempt -ge $MaxAttempts) {
                return $false
            }
            Start-Sleep -Seconds $DelaySeconds
        }
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
        # une al dominio -- de lograrse los dos juntos, evita una segunda
        # llamada a Rename-Computer. Si el renombrado en particular
        # fallara con "the directory service is busy" (transitorio), el
        # bloque catch de abajo SI reintenta con Rename-Computer aparte
        # (ver `Invoke-RenameWithRetry`) -- el equipo para entonces ya
        # esta unido al dominio, asi que esa segunda llamada no necesita
        # volver a autenticarse contra el dominio para la union en si,
        # solo para la operacion de renombrado.
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
    if ((-not [string]::IsNullOrWhiteSpace($NewName)) -and (Test-PartialJoinRenameFailure -Exception $ex)) {
        # El equipo YA quedo unido al dominio -- solo el renombrado fallo
        # (tipicamente transitorio, ver Test-PartialJoinRenameFailure).
        # Se reintenta el renombrado por separado antes de darse por
        # vencido.
        if (Invoke-RenameWithRetry -NewName $NewName -Credential $credential) {
            Write-Output "RESULT_OK"
            exit 0
        }
        $detail = $ex.Message -replace "[\r\n]+", " "
        Write-Output ("RESULT_ERROR: El equipo se unio al dominio '$DomainName' correctamente, pero no se " +
            "pudo renombrar a '$NewName' pese a varios intentos (ultimo detalle: $detail). El equipo quedo " +
            "unido al dominio con su nombre anterior -- podes reintentar el renombrado mas tarde (Configuracion " +
            "> Sistema > Cambiar nombre de este equipo, con credenciales de dominio), o volver a marcar esta " +
            "casilla en unos minutos para que este asistente lo reintente.")
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
