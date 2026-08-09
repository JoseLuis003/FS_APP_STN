[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string[]]$AdminGroups
)

# post_join_setup.ps1
# --------------------
# Pasos posteriores a unir el equipo al dominio (ya con las credenciales
# validadas por join_domain.ps1): agregar los grupos de soporte al grupo
# local Administrators, y limpiar el autologon local (si estaba
# configurado) para que el equipo pida el logon de dominio normalmente.
#
# A diferencia del script original (DomainJoined.ps1), los nombres de grupo
# que tienen espacios se reciben como elementos de un arreglo (-AdminGroups),
# no como texto suelto sin comillas -- el script original tenia el bug de
# pasar "COPAAIR\GRP-Soporte Copa Panama" sin comillas, lo que PowerShell
# interpreta como varios argumentos posicionales sueltos y falla al
# invocarse.
#
# Imprime RESULT_OK si todo salio bien (agregar un grupo que ya era miembro
# NO se trata como error), o RESULT_ERROR: <detalle> si algo fallo.

$ErrorActionPreference = "Stop"
$errors = @()

foreach ($group in $AdminGroups) {
    try {
        Add-LocalGroupMember -Group "Administrators" -Member $group -ErrorAction Stop
    }
    catch {
        # "ya es miembro del grupo" no es un error real: el objetivo (que el
        # grupo tenga permisos de administrador local) ya esta cumplido.
        if ($_.Exception.Message -match "already a member" -or $_.CategoryInfo.Reason -eq "MemberExistsException") {
            continue
        }
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
