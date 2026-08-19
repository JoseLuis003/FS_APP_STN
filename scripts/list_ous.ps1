[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DomainName,
    [Parameter(Mandatory = $true)][string]$BaseDN,
    [Parameter(Mandatory = $true)][string]$Username
)

# list_ous.ps1
# ------------
# Script "delgado" (mismo patron que join_domain.ps1): toda la logica de
# que hacer con el resultado vive en Python (app/domain_join.py). Este
# script solo:
#   1) Lee la contrasena desde stdin (nunca por argumento de linea de
#      comandos -- mismo motivo de seguridad que join_domain.ps1). A
#      diferencia de join_domain.ps1 (que arma un PSCredential/SecureString
#      para Add-Computer), acá se pasa como texto plano al constructor de
#      DirectoryEntry -- esa clase de .NET no tiene overload que acepte
#      SecureString, así que no hay forma de evitarlo en este caso puntual;
#      sigue sin pasarse nunca por argumento ni quedar en disco.
#   2) Se conecta por LDAP a $BaseDN (ej.
#      "OU=Workstations_Copa,DC=copaair,DC=com") con esas credenciales, SIN
#      necesitar el modulo RSAT de Active Directory (que no viene instalado
#      por defecto en un equipo recien provisionado -- justo el escenario
#      de esta app): usa directamente las clases System.DirectoryServices
#      de .NET, disponibles en cualquier Windows.
#   3) Busca todas las OUs (objectClass=organizationalUnit) bajo esa rama,
#      recursivamente, e imprime UNA linea por cada una encontrada:
#        OU|<nombre>|<distinguishedName completo>
#      y al final, exactamente una de estas lineas (igual que
#      join_domain.ps1), para que Python la interprete:
#        RESULT_OK
#        RESULT_BAD_CREDENTIALS
#        RESULT_ERROR: <detalle>
#
# La deteccion de "credenciales invalidas" usa el mismo codigo nativo de
# Win32 1326 (ERROR_LOGON_FAILURE) que join_domain.ps1 -- duplicado acá (no
# importado de un modulo comun) por el mismo precedente de scripts
# self-contained del proyecto.
#
# IMPORTANTE (bug real de campo corregido): a diferencia de Add-Computer
# (join_domain.ps1), que lanza un System.ComponentModel.Win32Exception
# "de verdad" con .NativeErrorCode, un bind LDAP fallido vía
# DirectoryEntry.RefreshCache() (ADSI) lanza en cambio un
# System.DirectoryServices.DirectoryServicesCOMException (hereda de
# COMException, NO de Win32Exception) -- confirmado en campo: con
# credenciales incorrectas, el técnico veía el error crudo de PowerShell
# sin procesar: 'The following exception occurred while retrieving
# member "RefreshCache": "The user name or password is incorrect."'
# (PowerShell envuelve así cualquier fallo al invocar un miembro --
# propiedad o método -- sobre un objeto ADSI/DirectoryEntry, pero
# conserva la excepción real en .InnerException). Como
# Test-BadCredentialsError solo buscaba Win32Exception, nunca la
# encontraba, y el error caía en la rama genérica RESULT_ERROR en vez de
# RESULT_BAD_CREDENTIALS -- por eso la UI no ofrecía reintentar
# credenciales, solo mostraba el texto crudo. Corregido revisando también
# COMException/DirectoryServicesCOMException (ver Test-BadCredentialsError).

$ErrorActionPreference = "Stop"
$password = $null
$searcher = $null
$directoryEntry = $null
$results = $null

function Test-BadCredentialsError {
    param([System.Exception]$Exception)
    $current = $Exception
    while ($null -ne $current) {
        if ($current -is [System.ComponentModel.Win32Exception] -and $current.NativeErrorCode -eq 1326) {
            return $true
        }
        # Ver el comentario grande más arriba: DirectoryEntry.RefreshCache()
        # lanza un COMException (o su subclase DirectoryServicesCOMException),
        # nunca un Win32Exception -- hay que revisarlo por separado.
        if ($current -is [System.Runtime.InteropServices.COMException]) {
            # .ErrorCode es el HRESULT completo (ej. 0x8007052E para
            # credenciales inválidas) -- sus 16 bits bajos son el MISMO
            # código nativo de Win32 (1326) que usa join_domain.ps1, sin
            # importar el idioma de Windows del controlador de dominio.
            if (($current.ErrorCode -band 0xFFFF) -eq 1326) {
                return $true
            }
            # Respaldo adicional, solo para DirectoryServicesCOMException:
            # el "extended error" que devuelve el controlador de dominio
            # para credenciales inválidas siempre incluye "data 52e" (52e
            # hex = 1326) en ExtendedErrorMessage -- un código numérico
            # fijo de Active Directory, no un texto que cambie de idioma.
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

    $ldapPath = "LDAP://$DomainName/$BaseDN"
    $directoryEntry = New-Object System.DirectoryServices.DirectoryEntry($ldapPath, $Username, $password)
    # ADSI no valida las credenciales hasta el primer acceso real -- se
    # fuerza acá con RefreshCache() (en vez de esperar a que lo haga el
    # searcher de abajo) para que un usuario/contrasena invalidos salgan
    # como RESULT_BAD_CREDENTIALS y no como un RESULT_ERROR generico.
    $directoryEntry.RefreshCache()

    $searcher = New-Object System.DirectoryServices.DirectorySearcher($directoryEntry)
    $searcher.Filter = "(objectClass=organizationalUnit)"
    $searcher.SearchScope = [System.DirectoryServices.SearchScope]::Subtree
    $searcher.PropertiesToLoad.AddRange(@("ou", "distinguishedName")) | Out-Null
    $searcher.PageSize = 1000

    $results = $searcher.FindAll()
    foreach ($item in $results) {
        $ouName = $item.Properties["ou"][0]
        $dn = $item.Properties["distinguishedname"][0]
        Write-Output "OU|$ouName|$dn"
    }

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
    # plano no debe quedar viva mas tiempo del necesario (mismo criterio
    # que join_domain.ps1).
    $password = $null
    if ($null -ne $results) { $results.Dispose() }
    if ($null -ne $searcher) { $searcher.Dispose() }
    if ($null -ne $directoryEntry) { $directoryEntry.Dispose() }
    [System.GC]::Collect()
}
