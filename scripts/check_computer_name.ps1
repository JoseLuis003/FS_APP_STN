[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DomainName,
    [Parameter(Mandatory = $true)][string]$ComputerName,
    [Parameter(Mandatory = $true)][string]$Username
)

# check_computer_name.ps1
# -----------------------
# Se corre ANTES de join_domain.ps1 (ver app/domain_join.py,
# check_computer_name_available()) para evitar el bug real reportado en
# campo: unir un equipo al dominio con Add-Computer -NewName cuando YA
# existe en Active Directory un objeto de equipo con ese mismo nombre
# terminaba en "Computer '<nombre actual>' was successfully joined to
# the new domain '...', but renaming it to '<nombre deseado>' failed
# with the following error message: The account already exists." --
# es decir, el equipo SI quedaba unido al dominio, pero con el nombre
# generico de Windows (ej. "DESKTOP-XXXXX"), no con el nombre deseado,
# y encima se le mostraba al tecnico como un fallo total (sin avisarle
# que en realidad ya habia quedado unido, aunque con el nombre
# incorrecto).
#
# La causa real NO es el orden en que se hacen el join y el renombrado
# (renombrar el equipo localmente antes de unirlo no evita este bloqueo
# -- ver el comentario largo en app/domain_join.py): desde octubre de
# 2022, Windows bloquea por seguridad la reutilizacion de una cuenta de
# equipo ya existente en AD (KB5020276, "Netjoin: Domain join hardening
# changes") a menos que el usuario que hace la union sea quien creo esa
# cuenta originalmente, sea Domain/Enterprise Admin, o el dueno de esa
# cuenta tenga permitida la reutilizacion via la directiva de grupo
# "Domain controller: Allow computer account reuse during domain
# join". Como este script no puede saber de antemano si el tecnico
# tiene alguno de esos 3 permisos, lo unico que hace es CONFIRMAR si ya
# existe un objeto de equipo con el nombre elegido -- si existe, Python
# detiene el proceso ANTES de intentar Add-Computer (nunca se llega a
# unir con el nombre generico) y le explica al tecnico la causa real y
# sus opciones.
#
# Mismo patron "delgado" que join_domain.ps1 / list_ous.ps1: toda la
# logica de que hacer con el resultado vive en Python. Este script solo:
#   1) Lee la contrasena desde stdin (nunca por argumento).
#   2) Busca por LDAP, desde la RAIZ del dominio (no solo bajo
#      Workstations_Copa: el nombre de un equipo debe ser unico en TODO
#      el dominio, el objeto en conflicto podria estar en cualquier OU,
#      incluida la carpeta "Computers" por defecto si alguien lo
#      pre-creo ahi), un objeto con `objectClass=computer` y
#      `cn=$ComputerName`.
#   3) Si encuentra alguno, imprime "NAME_EXISTS|<distinguishedName>"
#      por cada uno (normalmente solo deberia haber 1, el nombre es
#      unico, pero se imprimen todos por si acaso) ANTES de la linea de
#      resultado final, igual que list_ous.ps1 con sus lineas "OU|...".
#   4) Imprime exactamente una de estas lineas y termina con el codigo
#      de salida correspondiente:
#        RESULT_OK                 (la consulta se pudo hacer -- haya
#                                    encontrado el nombre o no, ver las
#                                    lineas NAME_EXISTS previas)
#        RESULT_BAD_CREDENTIALS
#        RESULT_ERROR: <detalle>

$ErrorActionPreference = "Stop"
$password = $null
$directoryEntry = $null
$searcher = $null
$results = $null

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

function Get-EscapedLdapFilterValue {
    # Escapa los caracteres especiales de un filtro LDAP (RFC 4515) --
    # el nombre de equipo lo escribe el tecnico a mano, asi que no hay
    # que confiar en que nunca traiga un caracter como "(" o "*".
    param([string]$Value)
    $escaped = $Value
    $escaped = $escaped -replace '\\', '\5c'
    $escaped = $escaped -replace '\*', '\2a'
    $escaped = $escaped -replace '\(', '\28'
    $escaped = $escaped -replace '\)', '\29'
    $escaped = $escaped -replace "`0", '\00'
    return $escaped
}

try {
    $password = [Console]::In.ReadLine()
    if ([string]::IsNullOrEmpty($password)) {
        Write-Output "RESULT_ERROR: No se recibio la contrasena por stdin."
        exit 1
    }

    # Raiz del dominio (ej. "copaair.com" -> "DC=copaair,DC=com") -- se
    # busca desde ahi, no desde una OU especifica, porque el nombre debe
    # ser unico en todo el dominio.
    $domainRootDN = ($DomainName.Split('.') | ForEach-Object { "DC=$_" }) -join ','
    $ldapPath = "LDAP://$DomainName/$domainRootDN"
    $directoryEntry = New-Object System.DirectoryServices.DirectoryEntry($ldapPath, $Username, $password)
    # ADSI no valida las credenciales hasta el primer acceso real -- se
    # fuerza acá con RefreshCache() para que un usuario/contrasena
    # invalidos salgan como RESULT_BAD_CREDENTIALS y no como un
    # RESULT_ERROR generico (mismo criterio que list_ous.ps1).
    $directoryEntry.RefreshCache()

    $escapedName = Get-EscapedLdapFilterValue -Value $ComputerName
    $searcher = New-Object System.DirectoryServices.DirectorySearcher($directoryEntry)
    $searcher.Filter = "(&(objectClass=computer)(cn=$escapedName))"
    $searcher.SearchScope = [System.DirectoryServices.SearchScope]::Subtree
    $searcher.PropertiesToLoad.AddRange(@("distinguishedName")) | Out-Null

    $results = $searcher.FindAll()
    foreach ($item in $results) {
        $dn = $item.Properties["distinguishedname"][0]
        Write-Output "NAME_EXISTS|$dn"
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
    # Limpieza de variables sensibles en memoria -- mismo criterio que
    # join_domain.ps1 / list_ous.ps1.
    $password = $null
    if ($null -ne $results) { $results.Dispose() }
    if ($null -ne $searcher) { $searcher.Dispose() }
    if ($null -ne $directoryEntry) { $directoryEntry.Dispose() }
    [System.GC]::Collect()
}
