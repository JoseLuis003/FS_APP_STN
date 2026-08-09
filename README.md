# FS_APP_STN — FS APP PORTABLE (versión Python)

Reemplazo en Python del instalador desatendido que originalmente estaba en
VB.NET. La app abre en una **portada** ("FS APP PORTABLE") con 3 botones —
APPS, LTP / CSS y DOMINIO. APPS y LTP / CSS llevan cada uno a su propio
catálogo de aplicaciones en checkboxes, que permite seleccionar varias,
instalarlas de forma silenciosa una por una, y va quitando de la lista cada
ítem que termina de instalarse correctamente (igual que la app original).
DOMINIO todavía no tiene una sección definida — muestra un aviso de
"próximamente" al presionarlo.

## Portada (`app/ui/home_window.py`)

- Barra superior con los 3 botones de navegación (APPS, LTP / CSS,
  DOMINIO), y debajo la imagen de campaña completa, sin recortar.
- **APPS**: abre el catálogo de instalación original (ver sección
  "Catálogo de instalación (botón APPS)"). Usa `config/apps.json`.
- **LTP / CSS**: abre un segundo catálogo de instalación, independiente del
  de APPS (ver sección "Catálogo LTP / CSS"). Usa `config/ltp_css_apps.json`.
- Ambas ventanas se crean una sola vez y se reutilizan si se vuelve a
  entrar (no se reconstruye el catálogo cada vez).
- **DOMINIO**: muestra un mensaje de "próximamente" — para activarlo hay
  que definir primero qué pantalla o función debe abrir.
- La imagen de fondo (`assets/home_background.png`) es material de
  campaña interna de Copa Airlines; si se necesita cambiarla, basta con
  reemplazar ese archivo (se muestra completa, sin recortar, con barras de
  color sólido a los lados si la proporción no coincide exactamente con la
  ventana).
- La ventana de la portada abre con tamaño fijo (515×580 píxeles) para que
  nunca se estire a ocupar toda la pantalla, sin importar la resolución del
  equipo. Para cambiarlo, edita `FIXED_WIDTH`/`FIXED_HEIGHT` en
  `app/ui/home_window.py`.

## Catálogo de instalación (botón APPS)

- **NUEVO**: selecciona el catálogo típico de equipo nuevo (ver
  `NUEVO_PRESET_IDS` en `app/ui/main_window.py`).
- **UNSELECT**: deselecciona todo.
- **MTO**: selecciona el catálogo de mantenimiento (ISOView, Cortana,
  Toolbox Print, ShortCut-MTO — ver `MTO_PRESET_IDS`).
- **AJUSTES**: configura la carpeta base de instaladores (con selector de
  carpeta) y da acceso a "Editar versiones de las aplicaciones..." y
  "Agregar aplicación..." (ver secciones abajo).
- **ATRAS**: regresa a la portada (FS APP PORTABLE). Reutiliza la misma
  ventana de instalación si se vuelve a entrar por APPS (no recarga el
  catálogo desde cero).
- Al presionar INSTALAR se instala directo, sin diálogo de confirmación
  previo.
- Arriba del botón INSTALAR siempre se ve la ruta exacta desde la que la
  app está leyendo los instaladores en ese momento ("Instalando desde:
  ..."), en **verde con "✓ Carpeta encontrada"** si esa carpeta existe
  ahora mismo, o en **rojo con "⚠ Carpeta NO encontrada"** si no — así el
  técnico sabe de un vistazo si puede darle INSTALAR con confianza, sin
  tener que intentarlo y enterarse después por el log que la carpeta no
  estaba. Este indicador se revisa solo cada pocos segundos (por ejemplo,
  si conectas la USB después de abrir la app).
- Mientras se instala algo, junto al texto "Instalando: ..." aparece una
  barra de progreso (modo indeterminado, ya que los instaladores silenciosos
  no reportan un % real de avance). Desaparece automáticamente al terminar.
- Al terminar una instalación se genera automáticamente un **reporte**
  (ver sección abajo) y se abre en el navegador.
- El nombre y la versión que se ven en cada checkbox y en el reporte salen
  del campo `label`/`version` de `config/apps.json`.

## Editar, actualizar o eliminar una aplicación del catálogo (sin tocar JSON a mano)

AJUSTES → "Editar versiones de las aplicaciones..." abre una tabla con
todas las apps del catálogo, con tres formas de modificarlas:

- **Versión**: escribe la versión nueva en esa columna y presiona Guardar
  (se guarda como "N/D" si queda vacía). Solo toca el campo `version`, no
  el instalador ni los argumentos.
- **Actualizar instalador...**: reemplaza el instalador de esa app por un
  archivo nuevo (por ejemplo, la versión más reciente descargada del
  fabricante). Copia el archivo elegido a la misma carpeta que ya tenía esa
  app dentro de `CM APPS\APPS`, borra el instalador anterior si tenía otro
  nombre de archivo, y pide la versión nueva. Aplica de inmediato — no hace
  falta presionar Guardar.
- **Eliminar**: pide confirmación, quita la app del catálogo y borra su
  carpeta completa dentro de `CM APPS\APPS`. También aplica de inmediato y
  no se puede deshacer.

Cualquier compañero de soporte puede hacer esto sin reiniciar la app ni
tocar ningún archivo a mano; los cambios de instalador o eliminación se
reflejan en la lista principal en cuanto se cierra AJUSTES.

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
   base de instaladores (`CM APPS\APPS`, ver sección siguiente), se guarda
   esa ruta relativa; si estaba en otro lugar (por ejemplo, en el
   Escritorio), la app lo copia automáticamente a una subcarpeta nueva
   dentro de `CM APPS\APPS` — en la MISMA unidad desde la que se está
   ejecutando la app en ese momento (el disco local o la USB), para que
   quede accesible igual que el resto del catálogo sin depender de rutas
   externas.

La aplicación nueva aparece de inmediato en la lista principal al cerrar
AJUSTES, sin reiniciar la app ni tocar `apps.json` a mano.

## Catálogo LTP / CSS (`app/ui/ltp_css_window.py`)

Segunda pantalla de catálogo, independiente de APPS, a la que se entra
desde la portada con el botón LTP / CSS. Usa su propio archivo de catálogo
(`config/ltp_css_apps.json`, mismo formato que `apps.json`) y por ahora
solo tiene los botones ATRAS e INSTALAR (sin NUEVO/UNSELECT/MTO/AJUSTES —
se pueden agregar más adelante si hace falta). Reutiliza el mismo motor de
instalación y la misma carpeta base (`installers_base_path`, ver "Carpeta
de instaladores por defecto" más abajo) que APPS, así que los instaladores
de LTP / CSS también van dentro de `CM APPS\APPS`. A diferencia de APPS,
esta pantalla no genera reporte HTML/CSV al terminar — no hace falta aquí.

El catálogo y el panel de "Shares Configuracion" van dentro de un área con
scroll: ATRAS e INSTALAR quedan siempre fijos y completos abajo, sin
importar cuánto contenido haya arriba ni qué tan chica sea la pantalla del
técnico. El fondo de esa área con scroll se define en
`app/ui/styles.py` (reglas `QScrollArea` / `QScrollArea > QWidget >
QWidget`), no con un stylesheet local en `ltp_css_window.py` — ponerlo ahí
rompía el resaltado azul de los checkboxes marcados que viven adentro. Si
en algún momento aparece un fondo negro/oscuro detrás del catálogo (por
ejemplo con Windows en modo oscuro), es esta regla la que hay que revisar.

El tamaño inicial de la ventana (`_initial_window_size()`) se recorta al
espacio disponible de la pantalla del técnico (`QScreen.availableGeometry()`,
que ya descuenta la barra de tareas) en vez de usar siempre un tamaño fijo
de 950×780: en monitores grandes abre a ese tamaño "ideal", pero en
pantallas más chicas (o con escalado de Windows alto, donde 950×780
lógicos pueden verse bastante más grandes en píxeles físicos) se ajusta
para que la ventana entre completa y ATRAS/INSTALAR no queden inalcanzables
detrás de la barra de tareas. El contenido que no quepa en esa altura se
ve haciendo scroll (ver el punto anterior).

**Grupos exclusivos (selección única, tipo radio button):** algunos ítems
del catálogo pueden marcarse como mutuamente excluyentes agregándoles el
campo `"exclusive_group"` con el mismo valor de texto — por ejemplo,
GEMALTO / 3M / DESKO comparten `"exclusive_group": "lector_tarjetas"`
porque son formas alternativas de leer tarjetas y no tiene sentido
instalar más de una en el mismo equipo. Los ítems que comparten un
`exclusive_group` se dibujan juntos en una sola fila, y al marcar uno se
desmarcan y deshabilitan automáticamente los demás del grupo (se vuelven a
habilitar si se desmarca). Este mecanismo vive en
`app/ui/catalog_widgets.py` y lo puede usar cualquier catálogo (APPS
también, si algún día lo necesita) — basta con agregar el campo
`exclusive_group` a los ítems correspondientes en el JSON.

**Panel "Shares Configuracion" (`app/ui/shares_config_panel.py`):** al
marcar la casilla "Shares Configuracion" del catálogo aparece debajo un
panel con tres secciones — SETTING's, DEVICES y CRT's — y desaparece si se
vuelve a desmarcar. Dentro de SETTING's:

- **HOSTNAME** y **CIUDAD** vienen marcados y con un valor precargado
  (HOSTNAME toma el nombre real del equipo con `socket.gethostname()`;
  CIUDAD toma las primeras 3 letras de ese mismo nombre, en mayúsculas),
  pero el técnico puede editar ese valor libremente. CIUDAD no permite
  escribir más de 3 caracteres (es un código de ciudad, ej. "PTY").
- Los 4 campos **LNIATA** (CRT, ATB, BTP, DCP) empiezan desmarcados y
  vacíos, y aceptan letras y números (alfanumérico) hasta un máximo de 6
  caracteres, para evitar errores de tecleo.
- **CONTINGENCIA** es solo una casilla, sin campo asociado.
- En todos los campos con casilla, el campo de texto solo se puede editar
  mientras su casilla esté marcada (se deshabilita al desmarcarla, pero
  conserva lo escrito).

Al presionar INSTALAR y aplicarse la configuración con éxito, la casilla
"Shares Configuracion" se oculta (igual que cualquier ítem completado) y
el panel se cierra junto con ella. Los 4 campos LNIATA se limpian (casilla
y texto) para la próxima vez, porque son valores de un solo uso; HOSTNAME
y CIUDAD SÍ quedan tal cual, porque identifican al equipo y no cambian
entre corridas.

Las secciones DEVICES (BGR, OCR — WGE deshabilitado por ahora) y CRT's (2,
4) por ahora son casillas simples, sin ninguna regla especial todavía.
Esta es la segunda de varias condiciones que se están agregando "por
partes" a la pantalla LTP / CSS (la primera fue el grupo exclusivo
GEMALTO/3M/DESKO, arriba); las siguientes se irán sumando según se vayan
definiendo.

**Qué hace "Shares Configuracion" al presionar INSTALAR
(`app/shares_config_apply.py`):** a diferencia del resto del catálogo, este
ítem no ejecuta un instalador — edita directamente los archivos de Shares
que ya están en el equipo, usando los valores actuales de CIUDAD y
HOSTNAME del panel. En orden:

1. Busca la carpeta `C:\LTP\AppDatCM\CNT` y la renombra al valor de
   CIUDAD (ej. `CNT` -> `PTY`).
2. Dentro de esa carpeta, busca `LTPCMCNT.XRF` y le cambia las 3 últimas
   letras antes de la extensión ("CNT") por el valor de CIUDAD (ej.
   `LTPCMCNT.XRF` -> `LTPCMPTY.XRF`).
3. Abre ese archivo, reemplaza cualquier otra aparición de "CNT" por el
   valor de CIUDAD, y en la línea `WORKSTATION_NAME=CHECKIN` cambia la
   clave `WORKSTATION_NAME` por el valor de HOSTNAME (queda, por ejemplo,
   `LTP-JB=CHECKIN`).

Es idempotente: si se vuelve a presionar INSTALAR después de que la
carpeta y el archivo ya quedaron renombrados, los reutiliza en vez de
fallar por no encontrar `CNT`. Si CIUDAD o HOSTNAME están vacíos, o si la
carpeta/archivo no aparecen donde se esperan, se marca como error en la
casilla (igual que un instalador que falla) y el resto de la cola sigue
su curso con normalidad.

Después de eso, se edita un segundo archivo dentro de la misma carpeta ya
renombrada: `<CIUDAD>\UDF\LTPCMUDF.INF` (`apply_udf_configuration()` en el
mismo módulo):

- Si **LNIATA CRT** está marcado: la línea `GROUP=F,XXXXXX` (2 líneas
  debajo del comentario "define the number of LNIATA as needed for Parent
  Sessions") cambia el valor entre las comas por el valor de LNIATA CRT
  (si está marcado pero el campo quedó vacío, se marca como error). Si no
  está marcado, esa línea no se toca.
- La línea `LOCATION=...` cambia su valor por **CIUDAD**, siempre.
- Para cada sesión adicional — **ATB**, **BTP** y **DCP** — si su casilla
  LNIATA correspondiente está marcada: la línea `<SUFIJO>=0,<SUFIJO>1,,`
  cambia el "0" por "1", la línea `<SUFIJO>1LNIATA=XXXXXX,` cambia su
  valor por el valor de ese campo (si está marcada pero el campo quedó
  vacío, se marca como error), y el puerto fijo de esa sesión se corrige a
  su valor esperado (`ATB1PORT` a `COM7`, `BTP1PORT` a `COM8`, `DCP1PORT` a
  `COM9`) si tenía uno distinto. Si la casilla NO está marcada, ninguna de
  esas tres líneas se toca (ni el flag, ni el LNIATA, ni el puerto).

En todos los casos se reemplaza solo el valor indicado, sin quitar las
comas ni tocar el resto de la línea, y es igual de idempotente que el
paso del `.XRF`.

**Importante:** igual que en `apps.json`, los valores de `installer` y
`silent_args` de `ltp_css_apps.json` son placeholders — hay que revisarlos
contra los instaladores reales (EPSON, GEMALTO, 3M, DESKO, AppShell, etc.)
antes de usar esto en producción.

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
│   ├── config.py             # carga/guarda apps.json, ltp_css_apps.json y settings.json
│   ├── installer.py          # motor de instalación (subprocess + QThread)
│   ├── installer_detect.py   # sugerencia de switches silenciosos para apps nuevas
│   ├── report.py             # genera el reporte HTML/CSV al terminar
│   ├── shares_config_apply.py # renombra/edita los archivos de Shares (acción "Shares Configuracion")
│   └── ui/
│       ├── catalog_widgets.py # columna de checkboxes + grupos exclusivos (compartido)
│       ├── home_window.py    # portada (FS APP PORTABLE): APPS / LTP-CSS / DOMINIO
│       ├── main_window.py    # catálogo de instalación (botón APPS)
│       ├── ltp_css_window.py # catálogo de instalación (botón LTP / CSS)
│       ├── shares_config_panel.py # panel SETTING's/DEVICES/CRT's de "Shares Configuracion"
│       └── styles.py         # hoja de estilos (QSS)
├── assets/
│   ├── check.png              # ícono del checkmark de los checkboxes
│   └── home_background.png    # imagen de campaña de la portada
├── config/
│   ├── apps.json               # catálogo de APPS (editable)
│   ├── ltp_css_apps.json        # catálogo de LTP / CSS (editable)
│   ├── settings.json            # ruta de instaladores, modo, etc. (local, no versionado)
│   └── settings.example.json    # plantilla de referencia (sí versionada)
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

## Carpeta de instaladores por defecto: `CM APPS\APPS`

Si no hay ninguna carpeta configurada todavía (no existe `config/settings.json`,
ver sección siguiente), la app calcula sola la carpeta de instaladores como
`CM APPS\APPS` dentro de la **misma unidad** desde la que se está ejecutando
el `.exe` en ese momento:

- Corriendo desde el disco local → `C:\CM APPS\APPS`.
- Corriendo desde una memoria USB → `E:\CM APPS\APPS` (o la letra que le
  toque a esa USB en ese equipo).

Dentro de `APPS` van las subcarpetas de cada aplicación (`APPS\GoogleChrome\ChromeSetup.exe`,
`APPS\SAPGUI\NwSapSetup.exe`, etc.), igual que antes con la carpeta
`Instaladores`. Como la ruta se recalcula sola según la unidad activa, ya no
hace falta reconfigurar nada manualmente cada vez que la USB recibe una
letra distinta — simplemente hay que asegurarse de que la carpeta `CM
APPS\APPS` con los instaladores exista en esa unidad. Si se prefiere usar
otra carpeta, se puede seguir configurando manualmente desde AJUSTES →
"Examinar...".

## `config/settings.json` es local de cada equipo (no se sincroniza por git)

`config/settings.json` guarda la carpeta de instaladores configurada en
AJUSTES, que normalmente es distinta en cada equipo (ej. una letra de USB
distinta en cada máquina). Por eso **no está versionado** — está en
`.gitignore` — para que un `git pull` nunca choque con el ajuste local de
otra persona ni sobreescriba el tuyo.

- `config/settings.example.json` sí está versionado, como plantilla de
  referencia (no lo usa la app en tiempo de ejecución).
- Si `config/settings.json` no existe (por ejemplo, en una copia recién
  clonada, o justo después de que `git pull` lo elimine al dejar de
  rastrearlo), la app arranca usando el valor calculado de `CM APPS\APPS`
  (ver arriba) sin fallar — no es obligatorio volver a configurar nada a
  mano, salvo que se quiera usar una carpeta distinta.
- Si ya tenías un `config/settings.json` con tu ruta y actualizas a una
  versión del proyecto posterior a este cambio, `git pull` puede eliminarlo
  al dejar de rastrearlo — si eso pasa, simplemente vuelve a configurar la
  carpeta desde AJUSTES (una sola vez).

## Instalar desde un USB (sin copiar nada al disco local)

`installers_base_path` acepta cualquier ruta absoluta, incluida una unidad
USB (ej. `E:\CM APPS\APPS`). La app ejecuta cada instalador directo desde
ahí — no copia nada al disco local.

Como ahora la carpeta por defecto (`CM APPS\APPS`) se calcula sola en la
unidad desde la que corre el `.exe` (ver sección "Carpeta de instaladores
por defecto" más arriba), en la mayoría de los casos **no hace falta
configurar nada**: basta con que el USB tenga el `.exe` junto a su propia
carpeta `CM APPS\APPS` con los instaladores adentro, y la app la encuentra
sola sin importar qué letra (`E:`, `F:`, etc.) le haya asignado Windows esa
vez. Si se prefiere usar otra carpeta o nombre, se puede seguir
configurando manualmente: abre AJUSTES → "Examinar..." y selecciona la
carpeta deseada. Un indicador confirma si la ruta existe en ese momento, y
la app también avisa con un mensaje claro si al presionar INSTALAR la
carpeta configurada ya no se encuentra.
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

1. Confirmar los `silent_args` y rutas de instalador reales de cada
   aplicación contra los paquetes que usa Copa, tanto en `config/apps.json`
   como en `config/ltp_css_apps.json` (los valores de LTP / CSS son
   placeholders puestos como referencia mientras se arma el catálogo).
2. Seguir agregando, "por partes", las demás condiciones de la pantalla
   LTP / CSS que todavía faltan (por ahora están implementadas la
   selección única entre GEMALTO / 3M / DESKO y el panel de "Shares
   Configuracion"; las secciones DEVICES y CRT's de ese panel todavía no
   tienen ninguna regla especial).
3. Definir qué debe hacer la sección DOMINIO de la portada (por ahora solo
   muestra un aviso de "próximamente").
4. Decidir si el modo de instalación debe poder ser paralelo (varias a la
   vez) en vez de secuencial — hoy corre una por una para evitar
   contención de recursos.
5. Firmar el .exe o empaquetarlo con un certificado, si la política interna
   lo exige para ejecutar en los equipos de usuarios.
