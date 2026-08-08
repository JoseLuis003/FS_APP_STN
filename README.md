# FS_APP_STN — Instalador desatendido (versión Python)

Reemplazo en Python del instalador desatendido que originalmente estaba en
VB.NET. Muestra un catálogo de aplicaciones en checkboxes agrupados por
columnas, permite seleccionar varias, instalarlas de forma silenciosa una
por una, y va quitando de la lista cada ítem que termina de instalarse
correctamente (igual que la app original).

## Estado actual

- **NUEVO**: selecciona el catálogo típico de equipo nuevo (ver
  `NUEVO_PRESET_IDS` en `app/ui/main_window.py`).
- **UNSELECT**: deselecciona todo.
- **MTO**: selecciona el catálogo de mantenimiento (ISOView, Cortana,
  Toolbox Print, ShortCut-MTO — ver `MTO_PRESET_IDS`).
- **AJUSTES**: configura la carpeta base de instaladores (con selector de
  carpeta) y da acceso a "Editar versiones de las aplicaciones..." y
  "Agregar aplicación..." (ver secciones abajo).
- El botón **ATRAS** de la app original no se incluyó (no aplicaba a este
  flujo).
- Al presionar INSTALAR se instala directo, sin diálogo de confirmación
  previo.
- Mientras se instala algo, junto al texto "Instalando: ..." aparece una
  barra de progreso (modo indeterminado, ya que los instaladores silenciosos
  no reportan un % real de avance). Desaparece automáticamente al terminar.
- Al terminar una instalación se genera automáticamente un **reporte**
  (ver sección abajo) y se abre en el navegador.
- El nombre y la versión que se ven en cada checkbox y en el reporte salen
  del campo `label`/`version` de `config/apps.json`.

## Actualizar la versión de una aplicación (sin editar JSON a mano)

AJUSTES → "Editar versiones de las aplicaciones..." abre una tabla con
todas las apps del catálogo y su versión actual. Cualquier compañero de
soporte puede buscar la aplicación, escribir la versión nueva y presionar
Guardar — se actualiza `config/apps.json` automáticamente (solo el campo
`version`, no toca instalador ni argumentos) y el cambio queda activo de
inmediato, sin reiniciar la app ni tocar ningún archivo a mano.

## Agregar una aplicación nueva al catálogo (sin editar JSON a mano)

AJUSTES → "Agregar aplicación..." permite que cualquier compañero de soporte
sume al catálogo una aplicación que todavía no está en la lista:

1. Escribe el nombre a mostrar y selecciona el archivo instalador
   (`.exe`, `.msi`, `.ps1` o `.bat`) con "Examinar...". El tipo de instalador
   se detecta solo según la extensión del archivo.
2. Presiona "Detectar" para que la app sugiera los switches de instalación
   silenciosa típicos, buscando firmas conocidas dentro del propio archivo
   (Inno Setup, NSIS, InstallShield, WiX, etc. — para `.msi` siempre sugiere
   `/qn /norestart`, que es el estándar de Windows Installer). **Esto es solo
   una sugerencia, no una garantía** — el técnico debe confirmar que el
   switch realmente instala en silencio antes de dejarlo en uso (probándolo
   él mismo), y puede escribir manualmente otro switch si "Detectar" no
   reconoce el instalador o si el sugerido no funciona.
3. Elige en qué columna debe aparecer y, opcionalmente, la versión.
4. Al presionar "Agregar": si el instalador ya estaba dentro de la carpeta
   base de instaladores, se guarda esa ruta relativa; si estaba en otro
   lugar (por ejemplo, en el Escritorio), la app lo copia automáticamente a
   una subcarpeta nueva dentro de la carpeta base para que quede accesible
   igual que el resto del catálogo.

La aplicación nueva aparece de inmediato en la lista principal al cerrar
AJUSTES, sin reiniciar la app ni tocar `apps.json` a mano.

## Reporte de instalación

Al terminar de instalar (o intentar instalar) las aplicaciones seleccionadas,
la app genera un reporte en `reports/`, en dos formatos:

- `reporte_<equipo>_<fecha>.html`: para verlo o imprimirlo (se abre solo en
  el navegador al terminar).
- `reporte_<equipo>_<fecha>.csv`: para importarlo a Excel u otra
  herramienta de IT.

El encabezado incluye:

- Nombre del equipo
- Número de serie
- Asset Tag
- Versión de Windows (con build number)

Estos 4 datos se obtienen del propio equipo en el momento de generar el
reporte (número de serie y Asset Tag vía WMI/PowerShell — `Win32_BIOS` y
`Win32_SystemEnclosure`; versión de Windows vía el registro). Si algo no se
puede leer (por ejemplo, corriendo fuera de Windows), se muestra "No
disponible" en vez de fallar.

Debajo va la tabla con una fila por cada aplicación que se instaló
correctamente: nombre, versión (tomada del campo `version` de
`config/apps.json` — actualízalo con la versión real de cada paquete) y
fecha/hora de instalación. Las aplicaciones que fallaron no aparecen en el
reporte (quedan marcadas en rojo en la pantalla y registradas en `logs/`).

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
│   ├── report.py             # genera el reporte HTML/CSV al terminar
│   └── ui/
│       ├── main_window.py    # ventana principal
│       └── styles.py         # hoja de estilos (QSS)
├── config/
│   ├── apps.json             # catálogo de aplicaciones (editable)
│   └── settings.json         # ruta de instaladores, modo, etc. (editable)
├── logs/                     # se crea automáticamente, un log por día
└── reports/                  # se crea automáticamente, un reporte por instalación
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

## `config/settings.json` es local de cada equipo (no se sincroniza por git)

`config/settings.json` guarda la carpeta de instaladores configurada en
AJUSTES, que normalmente es distinta en cada equipo (ej. una letra de USB
distinta en cada máquina). Por eso **no está versionado** — está en
`.gitignore` — para que un `git pull` nunca choque con el ajuste local de
otra persona ni sobreescriba el tuyo.

- `config/settings.example.json` sí está versionado, como plantilla de
  referencia (no lo usa la app en tiempo de ejecución).
- Si `config/settings.json` no existe (por ejemplo, en una copia recién
  clonada), la app arranca con valores por defecto sin fallar; solo hay que
  configurar la carpeta correcta una vez desde AJUSTES → "Examinar...".
- Si ya tenías un `config/settings.json` con tu ruta y actualizas a una
  versión del proyecto posterior a este cambio, `git pull` puede eliminarlo
  al dejar de rastrearlo — si eso pasa, simplemente vuelve a configurar la
  carpeta desde AJUSTES (una sola vez).

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
- `enabled: false`: deja el ítem visible pero deshabilitado (por ejemplo,
  para un ítem que aún no está listo para desplegarse).
- `version`: la versión del paquete que se instala; aparece tal cual en el
  reporte final de instalación (ver sección "Reporte de instalación").

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
