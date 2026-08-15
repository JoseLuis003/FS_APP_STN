# FS_APP_STN — FS APP PORTABLE (versión Python)

Reemplazo en Python del instalador desatendido que originalmente estaba en
VB.NET. La app abre en una **portada** ("FS APP PORTABLE") con 3 botones —
APPS, LTP / CSS y DOMINIO. APPS y LTP / CSS llevan cada uno a su propio
catálogo de aplicaciones en checkboxes, que permite seleccionar varias,
instalarlas de forma silenciosa una por una, y va quitando de la lista cada
ítem que termina de instalarse correctamente (igual que la app original).
DOMINIO une el equipo al dominio `copaair.com` (ver sección "Pantalla
DOMINIO").

## Portada (`app/ui/home_window.py`)

- Barra superior con los 3 botones de navegación (APPS, LTP / CSS,
  DOMINIO), y debajo la imagen de campaña completa, sin recortar.
- **APPS**: abre el catálogo de instalación original (ver sección
  "Catálogo de instalación (botón APPS)"). Usa `config/apps.json`.
- **LTP / CSS**: abre un segundo catálogo de instalación, independiente del
  de APPS (ver sección "Catálogo LTP / CSS"). Usa `config/ltp_css_apps.json`.
- **DOMINIO**: abre la pantalla de unión al dominio `copaair.com` (ver
  sección "Pantalla DOMINIO").
- Las tres ventanas se crean una sola vez y se reutilizan si se vuelve a
  entrar (no se reconstruyen cada vez).
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
(`config/ltp_css_apps.json`, mismo formato que `apps.json`) y tiene los
botones ATRAS, AJUSTES e INSTALAR (sin NUEVO/UNSELECT/MTO — no hacen falta
en esta pantalla). Reutiliza el mismo motor de instalación y la misma
carpeta base (`installers_base_path`, ver "Carpeta de instaladores por
defecto" más abajo) que APPS, así que los instaladores de LTP / CSS también
van dentro de `CM APPS\APPS`. A diferencia de APPS, esta pantalla no genera
reporte HTML/CSV al terminar — no hace falta aquí.

**AJUSTES** reutiliza exactamente el mismo diálogo que APPS
(`app.ui.main_window.SettingsDialog`, con "Editar versiones de las
aplicaciones..." y "Agregar aplicación..." — ver las dos secciones de
arriba, "Editar, actualizar o eliminar..." y "Agregar una aplicación
nueva..."), pero pasándole `LTP_CSS_APPS_FILE` en vez de `APPS_FILE`: todo
lo que se agregue, edite o elimine desde AJUSTES en esta pantalla queda en
`config/ltp_css_apps.json`, sin tocar `config/apps.json` de APPS (son
catálogos completamente independientes). La carpeta base de instaladores
(`installers_base_path`) sí es compartida entre ambas pantallas. Las
funciones de `app/config.py` que escriben el catálogo (`add_app_item`,
`update_app_installer`, `remove_app_item`, `save_app_versions`) aceptan un
parámetro `apps_file` para esto — por defecto siguen apuntando a
`APPS_FILE`, así que el comportamiento de APPS no cambió.

**Tamaño de la ventana en la barra de título:** el título de esta ventana
incluye el ancho x alto actual en píxeles (ej. "FS APP PORTABLE - LTP / CSS
— 583 x 632 px"), actualizado en vivo en cada `resizeEvent` — así, si la
ventana se abre más grande de lo esperado en el equipo de algún técnico, se
puede ver el tamaño exacto con solo mirar la barra de título del sistema,
sin herramientas adicionales.

El catálogo y el panel de "Shares Configuracion" van dentro de un área con
scroll: ATRAS e INSTALAR quedan siempre fijos y completos abajo, sin
importar cuánto contenido haya arriba ni qué tan chica sea la pantalla del
técnico. El fondo de esa área con scroll se define en
`app/ui/styles.py` (reglas `QScrollArea` / `QScrollArea > QWidget >
QWidget`), no con un stylesheet local en `ltp_css_window.py` — ponerlo ahí
rompía el resaltado azul de los checkboxes marcados que viven adentro. Si
en algún momento aparece un fondo negro/oscuro detrás del catálogo (por
ejemplo con Windows en modo oscuro), es esta regla la que hay que revisar.

El tamaño inicial de la ventana (`_initial_window_size()`, constantes
`_DEFAULT_WIDTH` / `_DEFAULT_HEIGHT` = 583 x 632, confirmado a mano por el
técnico) se recorta al espacio disponible de la pantalla
(`QScreen.availableGeometry()`, que ya descuenta la barra de tareas) en vez
de abrir siempre a ese tamaño fijo: en pantallas más chicas (o con escalado
de Windows alto, donde ese tamaño lógico puede verse más grande en píxeles
físicos) se ajusta para que la ventana entre completa y ATRAS/INSTALAR no
queden inalcanzables detrás de la barra de tareas. Esto es solo el tamaño
INICIAL — la ventana se puede seguir agrandando o achicando con normalidad
arrastrando el borde, como cualquier ventana. El contenido que no quepa en
esa altura se ve haciendo scroll (ver el punto anterior).

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
- **CONTINGENCIA** es solo una casilla, sin campo asociado. Si está
  marcada al presionar INSTALAR, además de los dos pasos de archivo de
  abajo corre `LTP TRAVEL DOC\Contingencia.bat` (`run_contingencia_script()`
  en `app/shares_config_apply.py`) — a diferencia de esos dos pasos, esto sí
  es un proceso externo real, y su ruta es relativa a la carpeta de
  instaladores (`installers_base_path`, la misma que usa el resto del
  catálogo LTP / CSS), no a `C:\LTP\AppDatCM`. Se considera éxito el código
  de salida 0 o 3010 (igual que el resto del motor de instalación); si el
  script no existe, se agota el tiempo de espera (10 min) o termina con
  otro código, se marca como error igual que el resto de esta acción. Si la
  casilla NO está marcada, el script nunca se invoca.
- En todos los campos con casilla, el campo de texto solo se puede editar
  mientras su casilla esté marcada (se deshabilita al desmarcarla, pero
  conserva lo escrito).

Al presionar INSTALAR y aplicarse la configuración con éxito, la casilla
"Shares Configuracion" se oculta (igual que cualquier ítem completado) y
el panel se cierra junto con ella. Los 4 campos LNIATA y la casilla
CONTINGENCIA se limpian (o desmarcan) para la próxima vez, porque son
valores de un solo uso; HOSTNAME y CIUDAD SÍ quedan tal cual, porque
identifican al equipo y no cambian entre corridas. Si CONTINGENCIA falla
(por ejemplo, no se encuentra `Contingencia.bat`), la casilla queda
marcada y el resto del panel se comporta igual que cualquier otro error de
esta acción.

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

**Accesos directos de Shares (`app/shortcuts.py`):** por último, si los 2
pasos de arriba (y CONTINGENCIA, si estaba marcado) terminaron sin error,
`create_ltp_shares_shortcuts()` deja 2 accesos directos en el escritorio
público (`C:\Users\Public\Desktop`, visible para cualquier usuario del
equipo sin importar con qué cuenta se inició sesión):

- **LTP SHARES.lnk** → `C:\LTP\LTPGUI32.exe`, argumentos
  ` /ACM /CC<CIUDAD> /W%COMPUTERNAME% /SU%COMPUTERNAME%`.
- **LiteGUI.lnk** → `C:\LTP\LTPHPS32.exe`, argumentos
  ` /ACM /W%COMPUTERNAME% /SU%COMPUTERNAME% /CC<CIUDAD>`.

`<CIUDAD>` se reemplaza por el valor real del campo CIUDAD del panel, pero
`%COMPUTERNAME%` se deja tal cual, como texto literal — igual que en el
código VB.NET original del que se portó esta función: no lo expande el
acceso directo ni quien lo crea, sino `LTPGUI32.exe` / `LTPHPS32.exe` al
arrancar. Se crean con `pywin32` (`win32com.client.Dispatch("WScript.Shell")`,
el mismo objeto COM que usaba el VB.NET original vía `CreateObject`), así
que esto solo funciona en Windows — de ahí que la dependencia `pywin32` en
`requirements.txt` esté marcada como exclusiva de `sys_platform == "win32"`.
Si falla (por ejemplo, `C:\LTP` no existe todavía), se marca como error
igual que cualquier otro paso de esta acción, y el resto de la cola sigue
su curso con normalidad.

**Pasos posteriores a instalar Shares 5.0 (`app/shares_setup.py`):** el
ítem `shares_5_0` del catálogo tiene un `extra_step` con
`"installer_type": "python"` — un tipo de paso que, a diferencia del
resto, no apunta a ningún archivo instalador: `"installer"` es la clave
`"ltp_shares_post_install"`, que el motor de instalación
(`app/installer.py`, `_python_step_handlers()`) resuelve a una función de
Python real, no a un proceso externo. Esta función es el port directo a
Python del `.bat` que antes se corría a mano después de instalar Shares
5.0 ("LTP setting.bat"), en el mismo orden:

1. `icacls C:\LTP /grant Everyone:(OI)(CI)F` — da control total a
   cualquier usuario del equipo sobre esa carpeta.
2. Copia las fuentes (`*.fon`, `*.ttf`) que el propio `.msi` deja en
   `C:\LTP\Fonts` hacia `C:\Windows\Fonts`.
3. Importa `C:\LTP\Fonts\ALCFONXP.REG` con `regedit /s` (registra esas
   fuentes en Windows).
4. Borra el acceso directo que el instalador de Shares deja solo en el
   escritorio del usuario actual ("Shares LTPGUI32.exe.lnk") — a
   diferencia de los otros 4 pasos, si ya no está no se considera error
   (limpieza best-effort, igual que el `Del` del `.bat` original).
5. Desregistra y vuelve a registrar los 5 controles OCX de Shares
   (COMCTL32, mscomctl, comdlg32, msadodc, tabctl32), todos dentro de
   `C:\LTP`.

Se detiene en el primer paso que falle (falta un archivo, código de
salida distinto de 0, etc.), igual que cualquier secuencia de
`extra_steps` del catálogo — con la salvedad del paso 4, que nunca falla
por sí solo. Este tipo de paso (`"python"`) es para lógica que ya no tiene
sentido dejar como un script suelto en la carpeta compartida de
instaladores, y en cambio se porta directo a código Python empaquetado
dentro de la app, con su propio manejo de errores por paso en vez de
depender de un único código de salida de todo un `.bat`.

**Panel "AppShell Configuracion" (`app/ui/appshell_config_panel.py`):** al
marcar la casilla "AppShell Configuracion" del catálogo (columna de
AppShell) aparece debajo un panel con una sola sección, **DEVICE's**, con
5 casillas simples e independientes entre sí (no son un grupo exclusivo):
ATB, BTP, DCP, BGR y OCR. El panel desaparece si se vuelve a desmarcar la
casilla — mismo mecanismo que "Shares Configuracion" (`SharesConfigPanel`),
pero sin ninguna sección de campos de texto.

Igual que "Shares Configuracion", **"AppShell Configuracion" NO pasa por
el motor de instalación genérico**: al presionar INSTALAR,
`LtpCssWindow._on_installar()` la saca de la cola normal y la aplica
aparte con `app/appshell_config_apply.py`
(`LtpCssWindow._run_appshell_configuration`), en dos partes independientes
que se pueden aplicar juntas en la misma corrida (una casilla de cada
grupo, o de ambos, marcadas a la vez):

*ATB / BTP / DCP → INI de AppShell.* Por cada una que esté marcada, se
agrega su puerto COM y su identificador al archivo INI de configuración de
AppShell,

    C:\Program Files (x86)\DXC Technology\PssAppShell\Configurations\PrintAgent_COPA_PROD.ini

en dos líneas: `device.comport=` recibe el puerto COM del equipo (ATB →
`COM7`, BTP → `COM8`, DCP → `COM9`) y `device.list=` recibe su
identificador (ATB → `ATB1`, BTP → `BTP1`, DCP → `DCP1`). Si la línea ya
tiene algún valor después del `=` (de una corrida anterior, o de otro
equipo aplicado en la misma corrida), el nuevo valor se agrega al final
separado por una coma **sin espacio** (ej. `device.comport=COM7` pasa a
`device.comport=COM7,COM8` al aplicar también BTP); si no hay nada después
del `=`, el valor se escribe directo, sin coma. Los tres equipos se
procesan siempre en el mismo orden (ATB, BTP, DCP), sin importar en qué
orden estén marcadas las casillas en pantalla. Si el archivo INI no
existe, o si falta alguna de las dos líneas esperadas, se lanza
`AppShellConfigError`.

*BGR / OCR → Mastcom.xml.* Por cada una que esté marcada, se crea o
actualiza

    C:\Program Files (x86)\DXC Technology\PssAppShell\Mastcom\Mastcom.xml

agregando un `<Session>` con los parámetros seriales de ese lector dentro
del `<Device Type="DEVHAN">` (BGR → protocolo "Serial AEA", `COM6`,
19200 8N1, `Alias="BGR1"`; OCR → protocolo "Serial Reader", `COM9`, 9600
7E1, `Alias="RTE1"`). Si el archivo no existe todavía, se crea completo
(`Configuration`/`OPAT`/`Device`) con solo la(s) sesión(es) marcada(s). Si
ya existe, **no se borra nada de lo que ya tenía configurado**: se busca
el bloque `<Device Type="DEVHAN">` y, por cada opción marcada, si ya hay
una sesión con su mismo `Alias` (de una corrida anterior) se reemplaza
in-place (para no dejarla duplicada), y si no, se agrega al final sin
tocar ninguna otra sesión ya presente (por ejemplo, si antes se aplicó
solo BGR y ahora se marca solo OCR, la sesión BGR existente queda
intacta). Si el archivo existe pero no tiene el bloque `<Device
Type="DEVHAN">` esperado, se lanza `AppShellConfigError`.

En ambos casos, si no hay ninguna casilla del submenú marcada al presionar
INSTALAR con "AppShell Configuracion" seleccionada, también se refleja
como error. Al terminar con éxito, la casilla "AppShell Configuracion" y
su panel se ocultan (igual que cualquier ítem completado), y las casillas
que se hayan aplicado (de cualquiera de los dos grupos) se desmarcan
automáticamente (`reset_device_checks`) — así una corrida posterior no
vuelve a aplicar el mismo cambio. Si una de las dos partes falla (por
ejemplo, ATB se aplica bien pero después falla el paso de Mastcom), solo
se desmarcan las opciones que **sí** llegaron a aplicarse antes del
fallo — las que no se alcanzaron a aplicar quedan marcadas, listas para
reintentar sin perder lo que ya se guardó. La casilla "AppShell
Configuracion" se refleja como error (se desmarca, queda visible, con un
tooltip con el detalle), igual que cualquier fallo de instalación normal.

**Nota:** los ítems del catálogo LTP / CSS (EPSON UTILITY, GEMALTO, 3M,
DESKO, EPSON USB DRIVER, VIRTUAL PORT, BGR IER, CUSTOM, Shares 5.0 y
AppShell 4.00.0030) ya tienen instaladores/switches/versiones reales en
`ltp_css_apps.json`. **Shares Configuracion** y **AppShell Configuracion**
no necesitan ninguno: son casos especiales (ver más arriba) cuyo único
trabajo es desplegar sus paneles de opciones — su campo `installer` queda
vacío a propósito en ambos, porque `LtpCssWindow._on_installar()` los saca
de la cola de instalación normal antes de llegar a usarlo.

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

## Pantalla DOMINIO (`app/ui/dominio_window.py`, `app/domain_join.py`)

Une el equipo al dominio `copaair.com`. Emula el script `DomainJoined.ps1`
que ya usaba el equipo de soporte, pero corrigiendo el problema que motivó
este cambio: ese script nunca llegaba a pedir ni validar usuario/contraseña
(`$credentials` se usaba sin haberse asignado nunca), así que si la unión al
dominio fallaba, el script igual seguía con los pasos siguientes (grupos
locales, autologon, reinicio) como si nada.

**Flujo desde la UI:**

1. El técnico completa: nombre del equipo (viene prellenado con el nombre
   actual — si lo cambia, el equipo se renombra en el mismo paso que se une
   al dominio), la Unidad Organizativa (mismas 5 opciones del script
   original: ATO-BCK, ATO-COU-GTE, CGO, CTO, MTO), su usuario (solo el
   usuario, sin dominio — el prefijo `copaair\` se muestra fijo en la UI y
   Python lo antepone) y su contraseña.
2. Al presionar "UNIR AL DOMINIO", un `DomainJoinWorker` (QThread) corre en
   segundo plano para no congelar la ventana:
   - **Usuario o contraseña incorrectos**: se le avisa al técnico con un
     mensaje claro y se limpia SOLO el campo de contraseña — equipo, OU y
     usuario quedan como estaban, para que pueda corregir y reintentar sin
     volver a escribir todo.
   - **Cualquier otro error** (OU inválida, sin red, nombre de equipo
     duplicado, etc.): se muestra el detalle y no se continúa con los pasos
     siguientes.
   - **Éxito**: se agregan los grupos de soporte (`COPAAIR\GRP-Soporte Copa
     Panama` y `COPAAIR\GRP-Soporte Copa Estaciones`) al grupo local
     Administrators y se limpia el autologon local. Si este paso posterior
     falla, el equipo de todos modos YA quedó unido al dominio, así que se
     muestra como advertencia, no como fallo total.
3. **Reinicio**: a diferencia del script original (que reiniciaba sin
   preguntar), acá siempre se le pregunta al técnico antes de reiniciar. Si
   confirma, se ejecuta `shutdown /r /t 10` (10 segundos de margen).

**Cómo se distingue "credenciales incorrectas" de otros errores:** el
script `scripts/join_domain.ps1` revisa el código de error nativo de Win32
`1326` (`ERROR_LOGON_FAILURE`) dentro de la cadena de `.InnerException` de
la excepción — no el texto del mensaje, que cambia según el idioma de
Windows. El script imprime exactamente una de estas líneas a stdout, que
Python interpreta (`app/domain_join.py`):

```
RESULT_OK
RESULT_BAD_CREDENTIALS
RESULT_ERROR: <detalle>
```

**Seguridad:** la contraseña de dominio nunca se pasa como argumento de
línea de comandos (quedaría visible en el Administrador de tareas) ni se
guarda en `config/settings.json` ni en ningún otro archivo — se le pasa al
script de PowerShell únicamente por su entrada estándar (stdin), y el
técnico la vuelve a escribir cada vez que usa esta pantalla.

**Scripts de PowerShell (`scripts/`):** son "delgados a propósito" — toda
la lógica de reintentos y de qué mostrarle al técnico vive en Python; los
scripts solo ejecutan la operación de Windows y reportan el resultado.
Se empaquetan dentro del `.exe` (ver `build.spec`, carpeta `scripts/`) y se
extraen a una carpeta temporal en tiempo de ejecución, igual que `assets/`.

- `join_domain.ps1`: hace el `Add-Computer` (con `-NewName` si corresponde,
  para renombrar en el mismo paso).
- `post_join_setup.ps1`: agrega los grupos de soporte a Administrators
  (cada nombre de grupo se pasa como un solo argumento — el script original
  tenía un bug acá: `COPAAIR\GRP-Soporte Copa Panama` sin comillas se
  interpreta como varios argumentos sueltos y falla al invocarse) y limpia
  el autologon local.

**Importante:** este entorno de desarrollo no tiene Windows/PowerShell
disponible, así que la lógica de orquestación en Python está probada con
`subprocess.run` simulado (mockeado), pero la ejecución real de los `.ps1`
contra un controlador de dominio solo se puede verificar en una máquina
Windows real, unida (o no) a la red de Copa.

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
│   ├── appshell_config_apply.py # edita el INI (ATB/BTP/DCP) y Mastcom.xml (BGR/OCR) de "AppShell Configuracion"
│   ├── domain_join.py         # orquesta la unión al dominio (botón DOMINIO)
│   └── ui/
│       ├── catalog_widgets.py # columna de checkboxes + grupos exclusivos (compartido)
│       ├── home_window.py    # portada (FS APP PORTABLE): APPS / LTP-CSS / DOMINIO
│       ├── main_window.py    # catálogo de instalación (botón APPS)
│       ├── ltp_css_window.py # catálogo de instalación (botón LTP / CSS)
│       ├── shares_config_panel.py # panel SETTING's/DEVICES/CRT's de "Shares Configuracion"
│       ├── appshell_config_panel.py # panel DEVICE's (ATB/BTP/DCP/BGR/OCR) de "AppShell Configuracion"
│       ├── dominio_window.py # pantalla de unión al dominio (botón DOMINIO)
│       └── styles.py         # hoja de estilos (QSS)
├── scripts/
│   ├── join_domain.ps1        # Add-Computer + detección de credenciales inválidas (cod. 1326)
│   └── post_join_setup.ps1    # grupos locales de Administrators + limpieza de autologon
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
  `settings.json`, editable también desde el botón AJUSTES) — o, si hace
  falta, una ruta **absoluta** de Windows (`C:\Program Files\...`,
  `\\servidor\recurso\...`) que se usa tal cual, sin unirla a
  `installers_base_path`. Útil para abrir algo que un paso anterior ya dejó
  instalado en una ubicación fija (ver CUSTOM en `ltp_css_apps.json`). La
  detección es por expresión regular (`^([A-Za-z]:[\\/]|\\\\)` en
  `app/installer.py`), no con `Path.is_absolute()`, porque esa función
  cambia de comportamiento según el sistema operativo donde corre (en
  Linux, donde se prueba esta app, una ruta `C:\...` no se considera
  absoluta).
- `installer_type`: `exe`, `msi` (se ejecuta con `msiexec /i`), `msu`
  (paquete independiente de Windows Update — se ejecuta con `wusa.exe`, ya
  que a diferencia de un `.exe` no es un ejecutable en sí), `script`
  (`.ps1` se ejecuta con PowerShell; `.bat`/`.cmd` se ejecuta directo, ya
  que Windows los asocia automáticamente al intérprete de comandos incluso
  sin pasar por una shell explícita), `open` (abre el archivo con
  `os.startfile()` — un PDF, o un `.exe` ya instalado que el técnico debe
  usar manualmente — y sigue de inmediato: no es un proceso que se
  "instale" con código de salida, así que no se espera ni bloquea la cola;
  se considera éxito en cuanto la llamada no lanza un error), o `python`
  (no apunta a ningún archivo: `installer` es la clave de una función de
  Python empaquetada en la app, registrada en `_python_step_handlers()`
  dentro de `app/installer.py` — para lógica que ya no tiene sentido dejar
  como un script suelto en la carpeta de instaladores; ver `shares_5_0` /
  `app/shares_setup.py` más abajo).
- `silent_args`: los parámetros de instalación silenciosa reales de cada
  instalador (varían por fabricante).
- `extra_steps` (opcional, lista): algunas aplicaciones necesitan correr
  más de un paquete bajo UNA sola casilla — por ejemplo BGInfo (el `.exe`
  y después un `.bat`) o SAP GUI (5 pasos: 3 `.exe`, un instalador con
  espacio en el nombre de carpeta, y un `.bat` final). `installer` /
  `silent_args` / `installer_type` de arriba son siempre el PRIMER paso;
  cada elemento de `extra_steps` es un paso adicional con las mismas tres
  claves, que se ejecuta *solo si el paso anterior tuvo éxito* — si
  cualquier paso falla, el ítem completo se marca como fallido ahí mismo,
  sin intentar los pasos que quedaban. Ejemplo (BGInfo):
  ```json
  {
    "id": "bginfo",
    "label": "BGInfo",
    "installer": "BGinfo/BGTool.exe",
    "silent_args": "/accepteula",
    "installer_type": "exe",
    "extra_steps": [
      { "installer": "BGinfo/bginfo.bat", "silent_args": "", "installer_type": "script" }
    ]
  }
  ```
  Esta lógica de pasos vive en `app/installer.py` (`InstallWorker.run`,
  función `_iter_steps`). Nota: el botón "Actualizar instalador..." de
  AJUSTES (`CatalogEditorDialog`) solo reemplaza el PRIMER paso — si un
  ítem con `extra_steps` cambia de instalador en un paso que no es el
  primero, por ahora hay que editar `apps.json` a mano para ese paso.
  Ejemplo con un paso `open` y una ruta absoluta (CUSTOM en
  `ltp_css_apps.json` — abre un PDF, instala un `.exe`, abre un `.exe` ya
  instalado en una ruta fija, e instala otro `.exe`):
  ```json
  {
    "id": "custom",
    "label": "CUSTOM",
    "installer": "LTP TRAVEL DOC\\CUSTOM\\MANUAL.pdf",
    "installer_type": "open",
    "extra_steps": [
      { "installer": "LTP TRAVEL DOC\\CUSTOM\\PrinterSet_3.9.7.exe", "silent_args": "", "installer_type": "exe" },
      { "installer": "C:\\Program Files\\CUSTOM\\PrinterSet\\CePrinterSet.exe", "silent_args": "", "installer_type": "open" },
      { "installer": "LTP TRAVEL DOC\\CUSTOM\\DIW_KPM180H_221.exe", "silent_args": "", "installer_type": "exe" }
    ]
  }
  ```
  Cada elemento de `extra_steps` también puede llevar una clave `version`
  puramente informativa (no la usa el motor de instalación) cuando ese
  paso instala un paquete con su propio número de versión distinto al del
  ítem principal — útil quirúrgicamente para no perder esa referencia
  cuando, como en CUSTOM, cada paso es en realidad una aplicación distinta.

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
hora, comando ejecutado y código de salida. Se consideran éxito los
códigos 0, 3010 (éxito con reinicio pendiente) y 1638 (`ERROR_PRODUCT_VERSION`
del Windows Installer: "ya hay otra versión de este producto instalada" —
típico en paquetes vcredist cuando ya está presente una versión igual o
más nueva; no es un fallo real, no hay nada que instalar). Cuando un paso
falla, el log también registra stdout y stderr por separado (o aclara que
el instalador no escribió nada en ninguno de los dos, si así fue).

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
3. Probar la pantalla DOMINIO en una máquina Windows real, unida (o no) a
   la red de Copa — este entorno de desarrollo no tiene PowerShell/Windows
   disponible, así que solo se pudo verificar la lógica de orquestación en
   Python (con `subprocess.run` simulado) y revisar el código de los
   scripts `.ps1` manualmente.
4. Decidir si el modo de instalación debe poder ser paralelo (varias a la
   vez) en vez de secuencial — hoy corre una por una para evitar
   contención de recursos.
5. Firmar el .exe o empaquetarlo con un certificado, si la política interna
   lo exige para ejecutar en los equipos de usuarios.
