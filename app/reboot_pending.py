"""Detecta si Windows quedó en "reinicio pendiente" (típicamente porque se
acaba de instalar una actualización de Windows, o una característica/
capability vía DISM) -- extraído a su propio módulo porque lo necesitan 2
consumidores distintos:

1. `app/netfx35_setup.py` y `app/rsat_setup.py`: ambos usan DISM
   (`/Enable-Feature` y `/Add-Capability` respectivamente), que comparte el
   mismo almacén de componentes (CBS) -- si el equipo está en reinicio
   pendiente, DISM no puede tomar el lock del CBS y se queda COLGADO hasta
   agotar su propio timeout (10 minutos) en vez de fallar rápido. Revisar
   esto ANTES de invocar DISM evita ese cuelgue y da un mensaje claro al
   instante.

   Caso real de campo que motivó este chequeo (log de instalación,
   2026-08-19): en la misma corrida, "Windows-Updates-w11" instaló
   actualizaciones reales de Windows y terminó apenas 15 segundos antes de
   que "BFirst" (que depende de NetFX35) intentara correr DISM -- se quedó
   colgado los 10 minutos completos hasta que `subprocess.run` lo mató por
   timeout. Volvió a pasar más tarde en la misma corrida con el ítem
   independiente "NetFX35" (36 minutos después, sin que nada más se
   hubiera instalado de por medio) -- descartando que fuera una
   finalización breve en curso: el equipo había quedado en reinicio
   pendiente por la actualización de Windows.

2. `app/ui/main_window.py`: además de que cada paso individual lo revisa
   antes de correr DISM (caso 1), la pantalla APPS muestra un aviso
   ("banner") ANTES de que el técnico intente instalar NetFX35/RSAT/
   REGISTRO EN AD/BFirst mientras el equipo está en ese estado -- pedido
   explícito de campo (reporte 2026-09-02) tras un caso real donde estos
   4 ítems fallaron en la misma corrida por reinicio pendiente y el
   técnico no tenía forma de saberlo de antemano sin leer el log de cada
   uno. Ver `MainWindow._refresh_reboot_pending_banner`.

`is_reboot_pending()` revisa los 3 indicadores estándar de Windows de que
hay un reinicio pendiente (cualquiera de los 3 alcanza):

- `...\\Component Based Servicing\\RebootPending`: existe SOLO si una
  operación de CBS (la misma que usa DISM) dejó al equipo esperando un
  reinicio para completarse.
- `...\\WindowsUpdate\\Auto Update\\RebootRequired`: existe cuando Windows
  Update instaló algo que requiere reiniciar para terminar de aplicarse --
  justo el caso real de arriba.
- `...\\Session Manager\\PendingFileRenameOperations`: un VALOR (no solo
  la existencia de la clave) con archivos pendientes de renombrar o borrar
  al reiniciar.

Fuente: "Determine Pending Reboot Status -- PowerShell Style!" (Microsoft
Scripting Blog/DevBlogs), que documenta estos mismos 3 indicadores como la
forma estándar de detectar un reinicio pendiente en Windows:
https://devblogs.microsoft.com/scripting/determine-pending-reboot-statuspowershell-style-part-1/
"""
from __future__ import annotations

import sys

_REBOOT_PENDING_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
)
_PENDING_FILE_RENAME_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager"
_PENDING_FILE_RENAME_VALUE = "PendingFileRenameOperations"


def is_reboot_pending() -> bool:
    """Devuelve `False` sin lanzar nada fuera de Windows (no hay `winreg`)
    o si no se pudo leer alguna de las claves por cualquier motivo (mismo
    criterio conservador que el resto de la app para datos "informativos"
    del equipo, ver `app/report.py`: mejor asumir que no hay reinicio
    pendiente y dejar que el paso lo intente / que el técnico no vea un
    aviso de más, que bloquear/alarmar por un error al leer el registro)."""
    if sys.platform != "win32":
        return False
    import winreg

    for key_path in _REBOOT_PENDING_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path):
                return True
        except OSError:
            continue

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _PENDING_FILE_RENAME_KEY) as key:
            value, _value_type = winreg.QueryValueEx(key, _PENDING_FILE_RENAME_VALUE)
            if value:
                return True
    except OSError:
        pass

    return False
