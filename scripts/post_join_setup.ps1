[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AdminGroups
)

# post_join_setup.ps1
# --------------------
# Pasos posteriores a unir el equipo al dominio (ya con las credenciales
# validadas por join_domain.ps1): agregar los grupos de soporte al grupo
# local Administrators, y limpiar el autologon local (si estaba
# configurado) para que el equipo pida el logon de dominio normalmente.
#
# A diferencia del script original (DomainJoined.ps1), los nombres de grupo
# que tienen espacios se reciben con comillas, no como texto suelto sin
# comillas -- el script original tenia el bug de pasar
# "COPAAIR\GRP-Soporte Copa Panama" sin comillas, lo que PowerShell
# interpreta como varios argumentos posicionales sueltos y falla al
# invocarse.
#
# IMPORTANTE (bug real de campo corregido, ver tambien
# app/domain_join.py/apply_post_join_setup): -AdminGroups recibe los
# grupos como UN SOLO string separado por comas (ej.
# "COPAAIR\GRP-A,COPAAIR\GRP-B"), NO como un arreglo [string[]] con varios
# argumentos de linea de comandos sueltos -- eso fue justamente lo que se
# probo primero y fallaba: al invocar un .ps1 con "-File", PowerShell solo
# enlazaba el PRIMER grupo a -AdminGroups, y el segundo quedaba suelto
# como si fuera un argumento posicional aparte (que este script no tiene),
# haciendo fallar TODO el script con "A positional parameter cannot be
# found..." antes de llegar siquiera a agregar el primer grupo.
#
# Imprime RESULT_OK si todo salio bien (agregar un grupo que ya era miembro
# NO se trata como error), o RESULT_ERROR: <detalle> si algo fallo.
#
# IMPORTANTE (bug real de campo, reporte 2026-09-02): `Add-LocalGroupMember`
# (cmdlet del modulo Microsoft.PowerShell.LocalAccounts) tiene un bug
# real y ampliamente reportado -- ver el issue "Add-LocalGroupMember
# fails when adding an AD group" en el repo de PowerShell en GitHub --
# que hace que falle con "Object reference not set to an instance of an
# object" (NullReferenceException DENTRO del cmdlet, no un problema de
# credenciales, de nombre mal escrito, ni de permisos) específicamente
# al agregar un GRUPO de dominio como -Member. Agregar un USUARIO de
# dominio con el mismo cmdlet SI funciona -- el bug es solo para grupos,
# que es exactamente el caso de los 3 `LOCAL_ADMIN_GROUPS`
# (`app/domain_join.py`), todos grupos "GRP-...", nunca usuarios.
#
# Se evita el cmdlet roto por completo y se usa el proveedor ADSI WinNT
# directamente (`[ADSI]"WinNT://..."`) -- una API mas vieja y de mas bajo
# nivel que Microsoft.PowerShell.LocalAccounts, sin este bug, y el mismo
# mecanismo que usaba el script original de este proceso
# (`DomainJoined.ps1`) antes de que existiera `Add-LocalGroupMember`.

$ErrorActionPreference = "Stop"
$errors = @()
$groupList = $AdminGroups -split "," | Where-Object { $_ }

# Se comprueba membresia actual por nombre (no por SID) leyendo
# directamente los miembros del grupo local Administrators via ADSI, en
# vez de intentar agregar y atrapar el error de "ya es miembro" -- ese
# error de ADSI viene como un HRESULT/COMException cuyo texto varia
# segun el idioma de Windows del equipo, así que comparar por nombre de
# antemano es mas confiable que intentar reconocer el mensaje de error.
function Test-IsLocalGroupMember {
    param(
        [Parameter(Mandatory = $true)]$LocalGroupAdsi,
        [Parameter(Mandatory = $true)][string]$MemberName
    )
    foreach ($member in $LocalGroupAdsi.psbase.Invoke("Members")) {
        $existingName = $member.GetType().InvokeMember("Name", "GetProperty", $null, $member, $null)
        if ($existingName -eq $MemberName) { return $true }
    }
    return $false
}

$localAdmins = [ADSI]"WinNT://./Administrators,group"

foreach ($group in $groupList) {
    $group = $group.Trim()
    if (-not $group) { continue }

    # Los grupos vienen como "DOMINIO\Nombre del grupo" (ver
    # LOCAL_ADMIN_GROUPS en app/domain_join.py) -- el proveedor WinNT
    # arma la ruta con "/" en vez de "\" (`WinNT://DOMINIO/Nombre`), asi
    # que hay que separar ambas partes primero.
    $parts = $group -split "\\", 2
    if ($parts.Count -ne 2) {
        $errors += "No se pudo agregar '$group' a Administrators: se esperaba el formato DOMINIO\Grupo"
        continue
    }
    $domainName, $groupName = $parts

    try {
        if (Test-IsLocalGroupMember -LocalGroupAdsi $localAdmins -MemberName $groupName) {
            # ya es miembro -- el objetivo (que el grupo tenga permisos de
            # administrador local) ya esta cumplido, no es un error real.
            continue
        }
        $domainGroup = [ADSI]"WinNT://$domainName/$groupName,group"
        $localAdmins.Add($domainGroup.Path)
    }
    catch {
        $errors += "No se pudo agregar '$group' a Administrators: $($_.Exception.Message)"
    }
}

try {
    $winlogonPath = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    Set-ItemProperty -Path $winlogonPath -Name "AutoAdminLogon" -Value "0" -Force -ErrorAction Stop
    Set-ItemProperty -Path $winlogonPath -Name "DefaultUserName" -Value "" -Force -ErrorAction Stop
    if (Get-ItemProperty -Path $winlogonPath -Name "DefaultPassword" -ErrorAction SilentlyContinue) {
        Set-ItemProperty -Path $winlogonPath -Name "DefaultPassword" -Value "" -Force -ErrorAction Stop
    }
}
catch {
    $errors += "No se pudo limpiar el autologon: $($_.Exception.Message)"
}

if ($errors.Count -gt 0) {
    $detail = ($errors -join " | ") -replace "[\r\n]+", " "
    Write-Output "RESULT_ERROR: $detail"
    exit 1
}

Write-Output "RESULT_OK"
exit 0
