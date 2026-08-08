# FS_APP_STN — Instalador desatendido (versión Python)

Reemplazo en Python del instalador desatendido que originalmente estaba en
VB.NET. Muestra un catálogo de aplicaciones en checkboxes agrupados por
columnas, permite seleccionar varias, instalarlas de forma silenciosa una
por una, y va quitando de la lista cada ítem que termina de instalarse
correctamente (igual que la app original).

## Estado actual (v1 - punto de partida)

Como no se contaba con el código fuente original en VB.NET, esta versión se
reconstruyó a partir de las capturas de pantalla compartidas. Cubre el flujo
principal (checklist → instalar → progreso → desaparece al completar), pero
hay 3 botones cuyo comportamiento exacto no se pudo inferir solo de las
capturas y quedaron como marcador (`TODO` en `app/ui/main_window.py`):

- **NUEVO**
- **ATRAS**
- **MTO**

Cuéntame qué deben hacer exactamente y los conecto en la próxima iteración.

`AJUSTES` sí quedó funcional: abre un diálogo para configurar la carpeta
base donde están los instaladores y si se pide confirmación antes de
instalar.

## Estructura del proyecto

```
FS_APP_STN/
├── main.py                 # punto de entrada
├── requirements.txt
├── build.spec               # spec de PyInstaller (onefile, sin consola)
├── build.bat                 # script de compilación para Windows
├── app/
│   ├── config.py             # carga/guarda apps.json y settings.json
│   ├── installer.py          # motor de instalación (subprocess + QThread)
│   └── ui/
│       ├── main_window.py    # ventana principal
│       └── styles.py         # hoja de estilos (QSS)
├── config/
│   ├── apps.json             # catálogo de aplicaciones (editable)
│   └── settings.json         # ruta de instaladores, modo, etc. (editable)
└── logs/                     # se crea automáticamente, un log por día
```

## Catálogo de aplicaciones (`config/apps.json`)

Cada aplicación se define así:

```json
{
  "id": "crowdstrike",
  "label": "Crowdstrike",
  "installer": "Crowdstrike/WindowsSensor.exe",
  "silent_args": "/install /quiet /norestart",
  "installer_type": "exe",
  "default_checked": true,
  "enabled": true
}
```

- `installer`: ruta **relativa** a `installers_base_path` (definido en
  `settings.json`, editable también desde el botón AJUSTES).
- `installer_type`: `exe`, `msi` (se ejecuta con `msiexec /i`) o `script`
  (`.ps1` se ejecuta con PowerShell, `.bat`/`.cmd` directo).
- `silent_args`: los parámetros de instalación silenciosa reales de cada
  instalador (varían por fabricante — hay que verificarlos contra el
  instalador real, los que traje son solo ejemplos razonables).

## Instalar desde un USB (sin copiar nada al disco local)

`installers_base_path` acepta cualquier ruta absoluta, incluida una unidad
USB (ej. `E:\Instaladores`). La app ejecuta cada instalador directo desde
ahí — no copia nada al disco local.

Para usarlo: conecta el USB, abre AJUSTES → "Examinar..." y selecciona la
carpeta de instaladores dentro del USB. Un indicador confirma si la ruta
existe en ese momento. Como Windows puede asignarle una letra de unidad
distinta al USB cada vez que lo conectas (`E:`, `F:`, etc.), puede que haya
que re-seleccionar la carpeta si cambia de equipo o de puerto — la app
también avisa con un mensaje claro si al presionar INSTALAR la carpeta
configurada ya no se encuentra.
- `enabled: false`: deja el ítem visible pero deshabilitado, igual que
  "Self Audit" en la captura original.

**Importante:** los valores de `installer` y `silent_args` que dejé son
placeholders basados en convenciones típicas de cada fabricante (Dell,
CrowdStrike, Adobe, etc.). Hay que revisarlos uno por uno contra los
instaladores reales que usa Copa antes de usar esto en producción.

## Cómo correrlo (desarrollo)

```bash
pip install -r requirements.txt
python main.py
```

## Cómo generar el .exe

**Importante:** PyInstaller genera un ejecutable para el sistema operativo
en el que se corre — para producir un `.exe` de Windows hay que ejecutar
esto en una máquina Windows (no se puede generar un .exe de Windows desde
Linux/Mac).

En una máquina Windows con Python 3.10+ instalado:

```bat
build.bat
```

o manualmente:

```bat
pip install -r requirements.txt
pip install pyinstaller
pyinstaller build.spec
```

El resultado queda en `dist\FS_APP_STN.exe`. La carpeta `config/` se agrega
al bundle vía `build.spec`, pero como PyInstaller en modo `--onefile` la
descomprime en una carpeta temporal en cada ejecución, **para que los
técnicos puedan editar `apps.json`/`settings.json` sin recompilar**, copia
manualmente la carpeta `config` junto al `.exe` en `dist/` — la app la
detecta automáticamente ahí (ver `app/config.py::get_app_root`).

## Logs

Cada instalación queda registrada en `logs/install_YYYY-MM-DD.log` con
hora, comando ejecutado y código de salida (0 y 3010 se consideran éxito;
3010 = éxito con reinicio pendiente).

## Próximos pasos sugeridos

1. Confirmar los `silent_args` reales de cada instalador contra los
   paquetes que usa Copa.
2. Definir el comportamiento de NUEVO / ATRAS / MTO.
3. Decidir si el modo de instalación debe poder ser paralelo (varias a la
   vez) en vez de secuencial — hoy corre una por una para evitar
   contención de recursos.
4. Firmar el .exe o empaquetarlo con un certificado, si la política interna
   lo exige para ejecutar en los equipos de usuarios.
