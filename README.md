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
- **Imagen de fondo nítida en pantallas de alta densidad
  (`_compute_background_geometry` en `app/ui/home_window.py`):** bug
  reportado por un técnico ("la imagen de la portada se ve pixelada") en
  un equipo con escala de Windows mayor a 100% (125% / 150% / 200%, muy
  común en laptops corporativos). La causa: `_BackgroundWidget` le pedía
  a `QPixmap.scaled()` el tamaño LÓGICO de la ventana (ej. 515×580) tal
  cual, sin multiplicarlo por `devicePixelRatioF()` (la relación entre
  píxeles físicos y lógicos de la pantalla) — en una pantalla escalada,
  eso deja un resultado con menos píxeles reales de los que la pantalla
  puede mostrar, y Qt lo estira para llenar el espacio, dando el efecto
  pixelado/borroso sin importar qué tan nítida sea la imagen original.
  Ahora se escala a `tamaño_lógico × devicePixelRatioF()` (píxeles
  físicos reales) y se marca el resultado con
  `QPixmap.setDevicePixelRatio()` para que Qt lo dibuje a su tamaño
  lógico correcto, sin volver a estirarlo. En una pantalla normal (100%
  de escala, `devicePixelRatioF() == 1.0`) el comportamiento es
  idéntico a antes.

## Catálogo de instalación (botón APPS)

- **NUEVO**: selecciona el catálogo típico de equipo nuevo (ver
  `NUEVO_PRESET_IDS` en `app/ui/main_window.py`).
- **UNSELECT**: deselecciona todo.
- **MTO**: selecciona el catálogo de mantenimiento (ISOView, Cortana,
  Toolbox Print, ShortCut-MTO — ver `MTO_PRESET_IDS`).
- **AJUSTES**: configura la carpeta base de instaladores (con selector de
  carpeta, sin PIN) y da acceso a "Editar versiones de las
  aplicaciones..." y "Agregar aplicación..." (ver secciones abajo) —
  estos 2 botones sí piden un PIN (`SETTINGS_CATALOG_PIN`, ver
  `app/ui/main_window.py`) antes de abrir el diálogo correspondiente,
  porque son los únicos 2 que modifican el catálogo.
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
- Una app instalada con éxito desaparece de la lista (`checkbox.setVisible
  (False)`) y además queda DESMARCADA (`checkbox.setChecked(False)`) --
  fix de un bug real reportado en pruebas de campo: antes solo se ocultaba
  sin desmarcarse, así que quedaba marcada "por debajo", invisible; si
  después se presionaba INSTALAR de nuevo para instalar otras apps nuevas
  (de otra columna, por ejemplo), esa casilla ya instalada se colaba otra
  vez en la cola -- y como conserva su posición original en el catálogo,
  se reinstalaba PRIMERO, antes que las apps nuevas seleccionadas. Mismo
  fix aplicado en LTP / CSS (`_on_item_finished`,
  `_run_shares_configuration` y `_run_appshell_configuration` en
  `app/ui/ltp_css_window.py`) — ahí además corrige un efecto secundario
  del mismo bug en los grupos exclusivos (GEMALTO/3M/DESKO): antes, una
  vez instalado uno de ellos, los otros dos quedaban bloqueados para
  siempre (el checkbox marcado nunca llegaba a "desmarcarse" para
  liberarlos); ahora sí se rehabilitan correctamente.

### Activar Windows (`app/windows_activation.py`)

En la segunda columna del catálogo APPS, junto a los demás scripts de
puesta a punto (BackGround, AJUSTES NECESARIOS, REGISTRO EN AD,
Shortcuts, Manage Engine). Es un ítem `installer_type: "python"` (igual
que "Shares 5.0" o "AppShell Configuracion"): no apunta a un archivo, sino
a una función registrada en `app/installer.py` (`run_windows_activation`).
Porta el botón "Activador de Windows" del VB.NET original:

1. Verifica que el equipo esté unido a un dominio (`is_domain_joined()`,
   vía PowerShell — `Get-CimInstance Win32_ComputerSystem` ->
   `PartOfDomain`). Si NO lo está, se marca como error en la casilla con
   un mensaje explicando que la licencia por volumen de Copa solo aplica a
   equipos unidos al dominio `copaair.com` — a diferencia del VB.NET
   original, que en ese caso cerraba toda la aplicación
   (`Application.Exit()`), acá el resto del catálogo sigue disponible con
   normalidad.
2. Si está unido, configura la clave de producto y activa Windows contra
   el KMS interno de Copa, invocando `Scripts\slmgr.vbs` (dentro de la
   carpeta de instaladores) con `cscript //nologo` — primero
   `/ipk <clave>`, después `/ato`. Se usa `cscript`, no `wscript`, para que
   la salida de `slmgr.vbs` quede como texto normal (log/mensaje de error)
   en vez de aparecer como cuadros de diálogo emergentes.

Si `/ipk` falla, `/ato` nunca se intenta. Si cualquiera de los dos pasos
de `slmgr.vbs` termina con un código de salida distinto de 0, el mensaje
de error incluye la salida real del script (por ejemplo, el motivo por el
que rechazó la clave, o que no pudo contactar al KMS interno), para que el
técnico vea la causa concreta en vez de un mensaje genérico.

### BackGround (`app/branding_setup.py`)

Ítem `installer_type: "python"` (`branding_setup`), portado de
`Scripts\IMAGEN-STN\background.bat`. A pesar del nombre, no toca el fondo
de pantalla del escritorio: deja configurado BGInfo (el resumen de datos
del equipo superpuesto sobre el escritorio) y la imagen de la pantalla de
bloqueo, con el branding de Copa. En orden: copia `CMINFO.bgi` a
`C:\Windows\BGINFO\`, acepta el EULA de BGInfo y lo registra para que
arranque con Windows (`HKLM\...\CurrentVersion\Run`), da control total
(Everyone) a esa carpeta, copia `lockscreen.jpg` a
`C:\Windows\Web\Screen\`, y configura esa imagen como pantalla de bloqueo
vía `PersonalizationCSP`. A diferencia del `.bat` original (que nunca
revisaba el código de salida de ningún paso), acá cualquier paso que
falle detiene el resto y se marca como error.

### Shortcuts (`app/shortcuts.py`, `copy_stn_assets_and_shortcuts`)

Ítem `installer_type: "python"` (`stn_shortcuts`), portado de
`Scripts\Shortcut STN.bat`. Copia la carpeta `Copaair` completa (recursiva,
recursos compartidos con "AJUSTES NECESARIOS", ver abajo) a `C:\copaair`,
y después **TODO archivo que encuentre suelto** en `Scripts\Shortcut\` al
escritorio público, sin importar su nombre (originalmente eran 10
accesos directos ya armados -- `.lnk`/`.url`: WorldTracer, AIMS, COPA
ACADEMY, CORREO WEB, LOPA, RED, SABRE, Flight Radar24, EXCEL, WORD --
pero ya no hace falta que coincidan exactamente esos nombres: agregar,
quitar o renombrar un acceso directo en esa carpeta ya no requiere tocar
el código). Antes se exigía una lista fija de 10 nombres exactos y
fallaba si faltaba alguno (visto en pruebas reales con `LOPA.lnk`
faltante); ahora solo falla si la carpeta `Shortcut\` no existe, o si
existe pero está vacía. A diferencia de los accesos directos de Shares
(que se arman dinámicamente vía COM, ver más abajo), estos ya vienen
armados de antemano en la carpeta de instaladores — este paso solo los
copia, igual que hace `app/appshell_post_install.py` con los accesos
directos de AppShell. Siempre sobrescribe (el `.bat` original no pasaba
`/Y` en estas copias puntuales, así que en teoría preguntaba antes de
sobrescribir — sin efecto real en una instalación desatendida sin entrada
interactiva disponible).

**"ShortCut-MTO" (más abajo) sigue con una lista fija de nombres** —
a diferencia de `Scripts\Shortcut\` (exclusiva de accesos directos), la
carpeta `MTO\` comparte espacio con otros instaladores de esa misma
columna (IGView, cortona3d.msi, Toolbox Print); copiar "todo lo que haya
ahí" también copiaría esos instaladores al escritorio público, así que
para MTO no aplica el mismo cambio.

### AJUSTES NECESARIOS (`app/workstation_settings.py`)

Ítem `installer_type: "python"` (`workstation_settings`), portado de
`Scripts\AJUSTES_NECESARIOS.bat` — **sin** un primer bloque de ~40 líneas
que el `.bat` original tenía, que editaba claves de registro bajo
prefijos `HKLM\TK_DEFAULT`/`TK_NTUSER`/`TK_SOFTWARE`/`TK_SYSTEM`
(deshabilitando Windows Defender, Cortana e historial de búsqueda). Esos
hives "TK_" no existen en una sesión normal de Windows a menos que algo
los haya montado antes con `reg load` (cosa que ese `.bat` nunca hacía),
así que esas ~40 líneas casi seguro fallaban en silencio (el `>nul 2>&1`
al final de cada línea oculta el error) y nunca llegaron a aplicar nada —
confirmado con el técnico como código muerto, y por eso no se portó.

El resto del `.bat` sí se portó, con 2 tipos de pasos:

- **Ajustes de preferencia** (Chrome, Edge, SysMain, apps en 2do plano,
  transparencia de la barra de tareas, IPv6, Delivery Optimization): en
  modo "mejor esfuerzo" — si alguno falla (ej. un servicio que no existe
  en esa edición de Windows), se registra en el detalle de retorno y se
  sigue con el resto, sin detener la acción completa. Igual que hacía el
  `.bat` original (que nunca revisaba el código de salida de ninguno de
  estos, y siempre terminaba con `Exit 0` sin importar qué falló).
- **Pasos críticos** (copiar las 5 fotos de cuenta de usuario desde
  `Copaair`, e importar la política de grupo local con `LGPO.exe /g
  <backup>`, la herramienta oficial de Microsoft): a diferencia de los
  ajustes de preferencia, estos SÍ detienen la acción y la marcan como
  error si fallan — son la parte que de verdad configura algo, no una
  preferencia de "mejor esfuerzo" sin impacto real si no se aplica.

### BGInfo (`app/branding_setup.py`, `apply_bginfo_registration`)

Paso extra (`installer_type: "python"`, `bginfo_registration`) del ítem
`bginfo` (1ra columna), portado de `BGinfo\bginfo.bat`. A diferencia de
"BackGround" arriba, este paso no copia ningún archivo: el instalador
principal del ítem (`BGinfo/BGTool.exe`) ya deja `bginfo.exe` y
`CMINFO.BGI` copiados en `C:\Windows\BGINFO` por su cuenta antes de que
este paso corra. Solo faltan las mismas 2 claves de registro que usa
"BackGround" (aceptar el EULA de BGInfo y registrarlo para que arranque
con Windows), con una línea de comandos más simple que la de
"BackGround" (`/timer:0`, sin `/SILENT /NOLICPROMPT` — así estaba en el
`.bat` original). Cualquier `reg add` que falle lanza
`BrandingSetupError` y detiene la acción, mismo criterio que el resto de
la app.

### ShortCut-MTO (`app/shortcuts.py`, `copy_mto_assets_and_shortcuts`)

Ítem `installer_type: "python"` (`mto_shortcuts`), portado de
`MTO\ShortCut_MTO.bat`. Misma idea que "Shortcuts" (STN) de arriba —
copia una carpeta `Copaair` completa a `C:\copaair` y después unos
accesos directos ya armados al escritorio público — pero usando la
carpeta `Copaair` de `MTO\` (una carpeta distinta a la que usan
"Shortcuts"/"AJUSTES NECESARIOS", aunque ambas copien al mismo destino
`C:\copaair`) y solo 3 accesos directos (`MXI.lnk`, `ToolBox Remote.url`,
`TOOLBOX.lnk`), que en este caso viven sueltos directo en `MTO\` en vez
de en una subcarpeta propia como el caso STN. Ambos ítems comparten un
helper privado común (`_copy_folder_and_shortcuts`) que solo cambia de
carpeta origen y de si los accesos directos están o no en una
subcarpeta.

### BFirst (`app/shortcuts.py`, `copy_bfirst_assets_and_shortcut`)

El ítem `bfirst` (2da columna) tiene 3 pasos, en este orden:

1. **`netfx35_setup`** (`installer_type: "python"`, ahora el instalador
   PRINCIPAL del ítem — ver `app/netfx35_setup.py`,
   `ensure_netfx35_installed`). Confirmado en una VM de prueba real:
   `BFirst\setupbolapp.exe` (Bytemaster OnLine App) exige tener
   instalado Microsoft .NET Framework 3.5 SP1 ANTES de poder instalarse
   — si no está, muestra el diálogo "Microsoft .NET Framework 3.5 SP1
   needs to be installed for this installation to continue." y aborta
   (visto como código de salida 1603, sin más detalle en stdout/stderr,
   típico de un instalador MSI/InstallShield que revisa sus propios
   prerequisitos antes de arrancar). .NET Framework 3.5 viene
   DESHABILITADO por defecto en instalaciones limpias de Windows 10/11
   (a diferencia de .NET 4.x, que sí viene integrado de fábrica), así
   que hay que habilitarlo antes de intentar instalar BFirst.

   Este paso es un puerto directo de `NetFX35\INSTALL.cmd`
   (`DISM /Online /Enable-Feature /FeatureName:NetFx3 /All /LimitAccess
   /Source:"...\NetFX35\sources\sxs"` — instala SIEMPRE desde los
   archivos locales que vienen junto a los demás instaladores, nunca
   Windows Update, porque las estaciones de Copa muchas veces no tienen
   salida a internet). Única diferencia deliberada con el `.cmd`
   original: ese `.cmd` siempre terminaba con `Exit 0` sin mirar el
   código de salida real de DISM, así que un fallo real (ej. la
   carpeta `sources\sxs` no viene junto a los demás instaladores)
   quedaba enmascarado como "éxito" y recién se notaba después, cuando
   BFirst fallaba con el 1603 de siempre. `ensure_netfx35_installed()`
   sí revisa ese código de salida y lanza un error claro si falla —
   fail loud, como el resto de la app.

   El mismo handler `netfx35_setup` también sigue disponible como ítem
   independiente y manual del catálogo ("NetFX35", 3ra columna) — no se
   quita, por si hace falta correrlo solo para algún otro instalador
   que dependa de .NET 3.5 (correrlo dos veces no tiene efecto
   negativo: es idempotente, igual que el DISM que lo respalda).
2. `BFirst\setupbolapp.exe` (el instalador real de BFirst, antes el
   paso principal del ítem — ahora el 1er `extra_step`, silent switch
   `/S /v/qn` sin comillas, confirmado como correcto contra la ayuda de
   línea de comandos del propio instalador InstallShield del vendor).
3. **`bfirst_assets`** (`installer_type: "python"`, 2do `extra_step`),
   portado de `BFirst\copy.bat`. A diferencia de
   "Shortcuts"/"ShortCut-MTO" de arriba (que copian una carpeta
   `Copaair` entera, de forma recursiva), acá el origen no es una
   carpeta: es un único archivo de ícono suelto
   (`bytemaster_logoprincipalqqq.ico`) que se copia a `C:\copaair`
   (creando la carpeta si no existe), y un único acceso directo
   (`BFIRST.url`) que se copia a Public Desktop. El `.bat` original
   usaba `xcopy /S /I /E /Y` para el ícono — como el origen es un
   archivo, no una carpeta, las banderas recursivas (`/S`/`/E`) no
   tenían ningún efecto real; lo único que importaba era `/I` (crear
   `C:\Copaair` si no existía) y `/Y` (sobrescribir sin preguntar), que
   es justamente lo que hace este paso.

#### Problema real de campo: DISM colgado 10 minutos por reinicio pendiente

Detectado en un log de instalación real (2026-08-19): en la MISMA corrida,
"Windows-Updates-w11" instaló actualizaciones reales de Windows y terminó
apenas 15 segundos antes de que "BFirst" (que depende de `netfx35_setup`)
intentara correr DISM — se quedó colgado los 10 minutos completos de
`_TIMEOUT_SECONDS` hasta que `subprocess.run` lo mató por timeout. Volvió
a pasar más tarde en la misma corrida con el ítem independiente "NetFX35"
(36 minutos después, sin que nada más se hubiera instalado de por medio,
descartando que fuera solo una finalización breve en curso).

La causa: la actualización de Windows dejó al equipo con un **reinicio
pendiente**, y `DISM /Online /Enable-Feature` no puede tomar el lock del
almacén de componentes (CBS, Component-Based Servicing) hasta que ese
reinicio se complete — en vez de fallar rápido con un error claro, se
queda esperando ese lock.

`_is_reboot_pending()` (`app/netfx35_setup.py`) revisa, ANTES de llamar a
DISM, los 3 indicadores estándar de Windows de que hay un reinicio
pendiente (cualquiera de los 3 alcanza):

- `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based
  Servicing\RebootPending`: existe SOLO si una operación de CBS (la
  misma que usa DISM para `/Enable-Feature`) dejó al equipo esperando un
  reinicio para completarse.
- `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto
  Update\RebootRequired`: existe cuando Windows Update instaló algo que
  requiere reiniciar para terminar de aplicarse — justo el caso real de
  arriba.
- `HKLM\SYSTEM\CurrentControlSet\Control\Session
  Manager\PendingFileRenameOperations`: un VALOR (no solo la existencia
  de la clave) con archivos pendientes de renombrar o borrar al
  reiniciar.

Si cualquiera de los 3 está presente, `ensure_netfx35_installed()` lanza
`NetFx35SetupError` al instante, con un mensaje que empieza con
**"Reinicio Pendiente: ..."** y le pide al técnico reiniciar el equipo y
volver a marcar la casilla — en vez de colgarse otros 10 minutos con el
mismo resultado. Aplica tanto al paso `netfx35_setup` de BFirst como al
ítem independiente "NetFX35". Mismo criterio que SAP GUI 144/145 (ver
más abajo): la casilla queda en rojo como cualquier fallo, y en el
reporte final la columna de versión muestra únicamente **"Reinicio
Pendiente"** (sin el prefijo "FALLO" — no es un fallo real sin resolver,
apenas el técnico reinicie y vuelva a marcar la casilla va a terminar de
instalarse bien) en vez del "FALLO" genérico (`is_reboot_pending_message()`
en `app/report.py` detecta el mensaje por contener las palabras
"reinicio" y "pendiente", así que este caso y el de SAP GUI se
distinguen igual en el reporte con el mismo mecanismo).

### DELL Command Update (`app/dotnet_desktop_runtime_setup.py`)

El ítem `dell_command` tiene 2 pasos, en este orden:

1. **`dotnet_desktop_runtime_setup`** (`installer_type: "python"`,
   instalador PRINCIPAL del ítem — ver
   `app/dotnet_desktop_runtime_setup.py`,
   `ensure_dotnet_desktop_runtime_installed`). Confirmado en una prueba
   real de campo, en un Dell Latitude 5280 genuino (no una VM): el EXE
   de Dell Command Update 5.7.1 (`installer_type: "exe"`, silencioso
   con `/s`) terminaba con **código de salida 4**, que en el esquema
   estándar de Dell Update Package (DUP) significa "hard dependency
   error" — un prerequisito obligatorio no cumplido, que no se puede
   forzar con `/f`. Se descartó hardware no soportado (era un Dell
   genuino) y sistema operativo no soportado; la causa real, confirmada
   con reportes de la propia comunidad de Dell sobre esta misma serie
   5.x, es que el instalador de Dell Command Update exige tener ya
   instalado el **Microsoft .NET Desktop Runtime** (el ".NET" moderno —
   NO ".NET Framework 3.5", que es el prerequisito de BFirst, ver
   arriba) dentro de un rango de versión específico: entre 8.0.8 y
   8.0.17 (x64). Ni la ausencia total del runtime ni una versión más
   nueva (ej. la 8.0.18, que Microsoft ya liberó y excede el máximo que
   revisa el instalador de DCU) sirven — en ambos casos, DCU aborta
   igual con el código 4.

   `ensure_dotnet_desktop_runtime_installed()` primero revisa si ya hay
   una versión compatible instalada (mirando las subcarpetas de
   `C:\Program Files\dotnet\shared\Microsoft.WindowsDesktop.App\`, sin
   necesitar `dotnet.exe` en el PATH) — si la hay, no hace nada más
   (idempotente). Si no, instala desde un instalador offline local en
   `<installers_base_path>\DotNetDesktopRuntime\windowsdesktop-runtime-
   8.0.17-win-x64.exe` (mismo criterio que NetFX35: nunca se descarga
   nada de internet, porque muchas estaciones de Copa no tienen salida
   — hay que colocar ese `.exe` junto a los demás instaladores, dentro
   de una carpeta `DotNetDesktopRuntime`). Se eligió a propósito
   instalar la versión 8.0.17 (el tope superior que acepta DCU 5.x):
   como los runtimes de .NET conviven instalados en paralelo
   (side-by-side), agregar esta versión no reemplaza ni afecta ninguna
   otra que ya esté — sirve tanto si no había NINGÚN runtime instalado
   como si ya había uno más nuevo e incompatible.
2. El EXE real de Dell Command Update 5.7.1 (`extra_step`, sin cambios
   — sigue siendo `installer_type: "exe"` con `/s`).

### Copa ID (Asset Tag) (`app/copa_id_setup.py`)

En la columna 1 del catálogo APPS, junto a los demás ítems de Dell (DELL
Command Update, DELL Optimizer, DELL OwnerTag), el ítem `copa_id` es un
caso especial: a diferencia de cualquier otro ítem del catálogo, no es
solo un checkbox — tiene un campo de texto al lado donde el técnico
escribe (o confirma) el **Asset Tag** de 6 dígitos que se va a grabar en
el BIOS del equipo vía **Dell Command | Configure** (`cctk.exe`).

- El campo solo acepta dígitos numéricos, hasta un máximo de 6 (validador
  de Qt + `setMaxLength(6)` como respaldo — no deja escribir letras ni un
  7mo dígito).
- Al abrir la pantalla, el campo se **prellena automáticamente** con el
  Asset Tag que YA tenga configurado el equipo, consultado vía WMI
  (`Win32_SystemEnclosure.SMBIOSAssetTag`, reutilizando
  `app.report.get_asset_tag()` — la misma consulta que ya usa el reporte
  de instalación, sin duplicar lógica de PowerShell). Si el equipo no
  tiene ningún Asset Tag configurado, o lo que devuelve WMI no es un valor
  válido de 6 dígitos (por ejemplo, un equipo nuevo de fábrica trae texto
  genérico como "Default string", o la consulta WMI falla y devuelve "No
  disponible"), el campo queda **vacío** con el placeholder **"NO SETUP"**
  en vez de prellenarlo con un valor que de todos modos no pasaría la
  validación.
- Al presionar INSTALAR con la casilla de Copa ID marcada, se valida que
  el campo tenga exactamente 6 dígitos (si no, aparece un aviso y no se
  arranca nada); si pasa la validación, se ejecuta:

  ```
  <installers_base_path>\Copa_ID\cctk.exe --asset=<valor del campo>
  ```

  (hay que colocar `cctk.exe` dentro de una carpeta `Copa_ID` junto a los
  demás instaladores — nunca se descarga ni se asume una ruta absoluta,
  mismo criterio que el resto del catálogo).
- Igual que "Shares Configuracion"/"AppShell Configuracion" en LTP / CSS
  (ver más abajo), este ítem **no pasa por el motor de instalación
  genérico** (`InstallManager`/`InstallWorker`): `MainWindow._on_installar()`
  lo saca de la cola normal y lo aplica aparte, sincrónico en el hilo de
  la UI (`_run_copa_id_asset_tag`) — a diferencia de esos dos casos, no
  hace falta diferirlo a después de que termine la cola normal, porque no
  depende de que ningún otro ítem termine antes; puede aplicarse en la
  misma corrida que otras apps sin ningún orden especial.
- El resultado se refleja en la casilla exactamente igual que cualquier
  otro ítem: si `cctk.exe` termina con código de salida distinto de 0 (o
  no se pudo ejecutar, o se agotó el tiempo de espera), la casilla queda
  en **rojo, desmarcada, con el detalle del error en el tooltip** — sin
  ocultarse, para que el técnico pueda corregir el Asset Tag y reintentar.
  Si tiene éxito, la casilla se **oculta y se desmarca** (mismo fix de
  reinstalación fantasma que el resto del catálogo — ver más arriba) y el
  Asset Tag grabado queda registrado en el reporte final de instalación,
  en la columna de "versión" (reutilizada acá con otro sentido: no es un
  número de versión de software, es el valor que quedó grabado en el
  BIOS).

### SAP GUI 7.8 (`app/sap_gui_setup.py`)

El ítem `sap_gui` tiene 5 pasos: `vstor_redist.exe` (principal),
`NwSapSetup.exe`, el parche `GUI800_4-80006341.EXE`, `SAPSetupSLC.exe`, y
por último `sap_gui_setup` (`installer_type: "python"`, ver más abajo).

**Problema conocido: código de salida 144/145 en el paso 2
(`NwSapSetup.exe`)** — reportado en una prueba real de campo:
`vstor_redist.exe` (paso 1) termina OK (código 0), pero `NwSapSetup.exe`
(paso 2) falla enseguida después con el código 145, sin ningún detalle en
stdout/stderr. Confirmado contra la documentación oficial de SAP (KB
3275253, "Component VC15RT64 is in error" — termina con "RC-145: Error
report has been created and reboot is recommended" — y KB 3117684, sobre
el código 144: "COM server out of process self registration failed!
Reboot required"): estos códigos significan que el componente VC++ que
`vstor_redist.exe` acaba de instalar necesita que **Windows reinicie**
para terminar de registrar sus componentes COM antes de que
`NwSapSetup.exe` pueda continuar — instalar los dos, uno detrás del otro,
en la misma sesión, sin reiniciar en el medio, produce este fallo. Esto
solo pasa la PRIMERA vez que se instala ese componente VC++ en un equipo
(si ya estaba instalado de antes, `vstor_redist.exe` devuelve 1638 en vez
de 0, y no hace falta reiniciar).

**Solución manual** (se decidió no automatizar esto con un paso de
prerequisito tipo NetFX35/.NET Desktop Runtime — instalar todo el ítem
de una sola pasada no permite reiniciar a la mitad sin rediseñar el
motor de instalación): si "SAP GUI 7.8" falla en el paso 2, **reinicia
el equipo y vuelve a marcar la casilla "SAP GUI 7.8"** (quedó
desmarcada automáticamente al fallar, ver "Catálogo de instalación") —
la segunda vez, `vstor_redist.exe` detecta que el componente ya está
instalado (código 1638) y sigue derecho con los 4 pasos restantes sin
volver a fallar. Para que esto sea claro sin tener que buscar el código
en este README, ese paso tiene configurado un `exit_code_messages` (ver
`AppItem` en `app/config.py` y `InstallWorker.run()` en
`app/installer.py`): si falla justo con el código 144 o 145, la casilla
queda en rojo/sin marcar como cualquier fallo (sigue contando como
error en `_results`), pero el tooltip muestra
**"Reinicio Pendiente: el componente VC++ que se acaba de instalar
necesita que reinicies el equipo antes de continuar. Reinicia y vuelve
a marcar esta casilla."** en vez del genérico "código de salida 145" —
el código real de todos modos queda igual en `logs/`. `exit_code_messages`
es un mecanismo genérico (no específico de SAP GUI): cualquier paso de
cualquier ítem, en `config/apps.json` o `config/ltp_css_apps.json`,
puede definir su propio `"exit_code_messages": {"<código>": "<mensaje>"}`
para reemplazar el mensaje genérico en códigos de salida "conocidos"
puntuales.

En el **reporte final** (ver la sección "Reporte de instalación" más
abajo), este caso puntual también se distingue del resto de las fallas:
`MainWindow._on_item_finished` usa `is_reboot_pending_message()`
(`app/report.py`) para detectar que el mensaje habla de un reinicio
pendiente (busca las palabras "reinicio" y "pendiente" en el mensaje,
sin importar el orden ni mayúsculas/minúsculas — funciona con cualquier
`exit_code_messages` que las incluya, no solo con el de SAP GUI, y
también con el caso de NetFX35/BFirst más abajo), y en ese caso la
columna de versión muestra únicamente **"Reinicio Pendiente"** (sin el
prefijo "FALLO") en vez del "FALLO" genérico — así, quien revisa el
reporte (no necesariamente el mismo técnico que instaló) ve de un
vistazo cuáles ítems fallidos solo necesitan un reinicio y reintentar
(no un fallo real sin resolver), sin tener que abrir `logs/`.

Paso extra (`installer_type: "python"`, `sap_gui_setup`), el ÚLTIMO de
los 4 pasos extra del ítem `sap_gui` (después de `NwSapSetup.exe`, el
parche `GUI800_4-80006341.EXE` y `SAPSetupSLC.exe`), portado de
`SAP_GUI_7.80\Win32\copy.bat`. A diferencia de todos los pasos "python"
anteriores (que trabajan sobre carpetas de sistema o Public Desktop),
este toca el **perfil del usuario actual** (`C:\Users\<usuario>\...`,
resuelto vía la variable de entorno `%USERNAME%`, igual que el `.bat`
original):

1. Crea `AppData\Roaming\SAP\Common` dentro del perfil del usuario.
2. Copia `SAPUILandscape.xml` y `SAPUILandscapeGlobal.xml` (la
   configuración de conexiones SAP con los servidores de Copa) a esa
   carpeta.
3. Borra `SAP Logon.lnk` del escritorio del usuario (el que arma el
   propio instalador de SAP GUI ahí) — en modo "mejor esfuerzo": si no
   existe, o no se puede borrar por algún motivo, no se considera un
   error, igual que en el `.bat` original (que tampoco revisaba el
   resultado de `del`).
4. Copia el `SAP Logon.lnk` "oficial" (con branding de Copa) a Public
   Desktop, para que se vea sin importar la cuenta con la que se entre
   al equipo.

Los pasos 1, 2 y 4 sí son fail-loud; solo el borrado del paso 3 es
best-effort, por ser una limpieza cosmética sin impacto funcional si no
se logra.

### VPN (`app/vpn_setup.py`)

Paso extra (`installer_type: "python"`, `vpn_setup`) del ítem
`anyconnect` (2da columna, etiquetado "VPN"), portado de `VPN\copy.bat`.
Deja lista la configuración de conexión de Cisco AnyConnect (rebautizado
"Cisco Secure Client" en versiones recientes) después de instalar el
`.msi` principal:

1. Copia `preferences.xml` al perfil del usuario actual
   (`AppData\Local\Cisco\Cisco AnyConnect Secure Mobility Client\`,
   resuelto vía `%USERNAME%`, igual que "SAP GUI 7.8").
2. Copia `preferences_global.xml` a
   `C:\ProgramData\Cisco\Cisco AnyConnect Secure Mobility Client\`
   (configuración a nivel de equipo, no de usuario).
3. Copia la carpeta `Profile` completa (recursiva, con subcarpetas si
   las tuviera) a `...\Profile\` dentro de esa misma carpeta de
   ProgramData — a diferencia de los 2 archivos sueltos de arriba, acá
   el origen sí es una carpeta.
4. Copia el acceso directo `Cisco Secure Client.lnk` a Public Desktop.

A diferencia de "SAP GUI 7.8" (que tenía un paso de limpieza
best-effort), acá los 4 pasos son igual de necesarios para que la VPN
funcione, así que los 4 son fail-loud.

## Editar, actualizar o eliminar una aplicación del catálogo (sin tocar JSON a mano)

AJUSTES → "Editar versiones de las aplicaciones..." pide el PIN
(`SETTINGS_CATALOG_PIN`, ver `app/ui/main_window.py`) antes de abrir la
tabla -- si el PIN es incorrecto o se cancela el diálogo, no se abre
nada. Una vez dentro, es una tabla con todas las apps del catálogo, con
tres formas de modificarlas:

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

AJUSTES → "Agregar aplicación..." también pide el PIN
(`SETTINGS_CATALOG_PIN`) antes de abrir el diálogo. Una vez dentro,
permite que cualquier compañero de soporte sume al catálogo una
aplicación que todavía no está en la lista:

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

APPS (`app/ui/main_window.py`, clase `MainWindow`) usa el mismo tamaño
inicial (583 x 632, con su propia copia de `_initial_window_size()` y las
mismas constantes -- cada módulo de ventana trae la suya, por el mismo
precedente de helpers self-contained del proyecto). A diferencia de LTP /
CSS, la ventana de APPS no agrega el tamaño actual al título de la barra
del sistema.

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

Las secciones **DEVICES** (BGR, OCR) y **CRT's** (2, 4) activan flags
directamente en `LTPCMUDF.INF` (ver más
abajo), portadas del VB.NET original con 3 decisiones de diseño: solo se
usa la ruta moderna basada en CIUDAD (se descartó el fallback legado
`C:\LTP\AppDatCM\CNT - Copy\UDF` que traía el VB.NET), cualquier línea
esperada que no se encuentre falla con un mensaje claro en vez de
seguir en silencio (a diferencia del `On Error Resume Next` original), y
**CRT 2** / **CRT 4** son mutuamente excluyentes en el panel (una
estación tiene 2 pantallas o 4, no ambas a la vez — marcar una desmarca
la otra automáticamente, sin deshabilitarla). Al aplicar la configuración
con éxito, las 4 casillas (BGR, OCR, CRT 2, CRT 4) se desmarcan para la
próxima corrida, igual que los campos LNIATA y CONTINGENCIA.

Esta es la segunda de varias condiciones que se están agregando "por
partes" a la pantalla LTP / CSS (la primera fue el grupo exclusivo
GEMALTO/3M/DESKO, arriba); las siguientes se irán sumando según se vayan
definiendo.

**Orden con la cola normal:** "Shares Configuracion" edita archivos que
deja el propio instalador de "Shares 5.0" (`C:\LTP\AppDatCM\...`, ver
abajo) — si en la MISMA corrida se marcan las dos casillas juntas (para
instalar Shares 5.0 desde cero y configurarlo de una), `_on_installar()`
espera a que la cola normal (`InstallManager`) termine de instalar Shares
5.0 antes de aplicar "Shares Configuracion" (ver `_on_queue_finished()` en
`app/ui/ltp_css_window.py`) — antes de este ajuste, se aplicaba de
inmediato, sin esperar, y por lo tanto siempre fallaba buscando una
carpeta que el MSI todavía no había creado. Si Shares 5.0 ya estaba
instalado de una corrida anterior (o no se marca en esta), no cambia
nada: se aplica igual, sin cola de por medio que esperar. Mismo criterio
para "AppShell Configuracion" y "AppShell 4.00.0030" más abajo.

**Qué hace "Shares Configuracion" al presionar INSTALAR
(`app/shares_config_apply.py`):** a diferencia del resto del catálogo, este
ítem no ejecuta un instalador — edita directamente los archivos de Shares
que ya están en el equipo, usando los valores actuales de CIUDAD y
HOSTNAME del panel. En orden:

1. Busca, dentro de `C:\LTP\AppDatCM`, la carpeta que el instalador de
   Shares 5.0 deja con un código "de fábrica" y la renombra al valor de
   CIUDAD (ej. `PTY` -> `MDE`). Ese código **no está hardcodeado en el
   código de la app** — se detecta dinámicamente buscando cuál subcarpeta
   contiene un archivo `LTPCM<código>.XRF` (sea cual sea ese código de 3
   letras). Esto es a propósito: la versión 5.0 actual del instalador deja
   siempre el código "PTY" (sin importar la ciudad real de destino de la
   estación — antes se pensaba que era un placeholder genérico "CNT"), y
   si una futura versión de Shares vuelve a cambiar ese código, esta
   detección dinámica sigue funcionando sin que haga falta tocar el código
   de la app. Si la estación es justo de Panamá (CIUDAD = "PTY"), no hace
   falta renombrar nada y la carpeta se reutiliza tal cual.
2. Dentro de esa carpeta, busca el archivo `LTPCM<código>.XRF` detectado
   en el paso 1 y le cambia las 3 letras del código por el valor de CIUDAD
   (ej. `LTPCMPTY.XRF` -> `LTPCMMDE.XRF`).
3. Abre ese archivo, reemplaza cualquier otra aparición de ese código por
   el valor de CIUDAD, y busca la línea `<clave>=CHECKIN` (sea cual sea
   `<clave>`) para reemplazar esa clave por el valor de HOSTNAME, dejando
   `=CHECKIN` intacto (ej. `*WKSNAME=CHECKIN` -> `LTP-JB=CHECKIN`).

   **Esta línea también se detecta dinámicamente, igual que el código de
   CIUDAD del paso 1** — la clave real (`*WKSNAME`, con el asterisco
   incluido, confirmado contra un `.XRF` real) ya cambió una vez entre
   versiones del instalador de Shares (antes se había asumido
   `WORKSTATION_NAME`, sin verificarlo contra un archivo real). En vez de
   depender de un nombre de clave que una futura versión podría volver a
   cambiar, la app busca la línea por su **valor de fábrica** (`CHECKIN`,
   que se mantuvo igual entre esas 2 versiones pese a que la clave
   cambió) — sea cual sea el texto que tenga antes del `=`. Si el archivo
   no tiene ninguna línea `<algo>=CHECKIN`, o tiene más de una (ambiguo),
   no se adivina: se lanza un error claro en vez de dejar el archivo a
   medio configurar.

Es idempotente: si se vuelve a presionar INSTALAR después de que la
carpeta y el archivo ya quedaron renombrados, los reutiliza en vez de
fallar por no encontrar la carpeta de fábrica. La línea de nombre de
estación es la excepción: como su ancla de detección (`=CHECKIN`) queda
intacta a propósito, sí se vuelve a actualizar en cada corrida — así que
cambiar el HOSTNAME y volver a presionar INSTALAR corrige el nombre de
estación, en vez de quedar pegado para siempre al primero que se haya
aplicado.

Si una misma carpeta candidata tiene MÁS de un archivo `.XRF` válido
adentro — visto en un equipo real: un equipo reutilizado, con el archivo
`.XRF` de una ciudad configurada anteriormente en ese mismo equipo (ej.
`LTPCMMIA.XRF`, de 2024) que nunca se borró, junto al archivo de fábrica
recién instalado (ej. `LTPCMPTY.XRF`, de "ahora") — no se falla ni se
adivina a ciegas: se asume que el más reciente (mayor fecha de
modificación) es el que el instalador de Shares 5.0 acaba de dejar en esta
corrida, y los demás — más viejos — se **mueven** (nunca se borran) a una
subcarpeta `_config_anterior` dentro de esa misma carpeta, quedando
recuperables ahí si hiciera falta revisarlos más adelante (si ya había
algo archivado antes con ese mismo nombre, no se sobrescribe: se le agrega
un sufijo numérico). El detalle final menciona qué se archivó.

Si CIUDAD o HOSTNAME están vacíos, si no hay ninguna carpeta candidata (ni
la de CIUDAD ya configurada), o si hay MÁS de una carpeta candidata (caso
ambiguo ENTRE carpetas distintas — a diferencia de tener varios `.XRF`
dentro de UNA misma carpeta, este caso sí requiere revisión manual, porque
no hay ninguna fecha que ayude a saber cuál carpeta es la correcta), la
app prefiere fallar y avisar antes que adivinar cuál usar: se marca como
error en la casilla (igual que un instalador que falla) y el resto de la
cola sigue su curso con normalidad.

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
  `COM10` — no `COM9`, porque este equipo comparte impresoras con "AppShell
  Configuracion", donde OCR ya usa `COM9` en Mastcom.xml) si tenía uno
  distinto. Si la casilla NO está marcada, ninguna de esas tres líneas se
  toca (ni el flag, ni el LNIATA, ni el puerto).
- Si **BGR** está marcado: la línea `BGR=0` cambia el "0" por "1" (sin
  tocar nada más que venga después en esa línea). Si **OCR** está
  marcado: igual, pero con la línea `OCR=0`. Son casillas simples, sin
  campo LNIATA ni puerto asociado (a diferencia de ATB/BTP/DCP) — no
  confundir con las casillas BGR/OCR de "AppShell Configuracion", que
  viven en otro módulo y editan otro archivo (`Mastcom.xml`, ver más
  abajo).
- Si **CRT 2** está marcado: la línea `CRT=<número>,...` cambia solo el
  número inicial a "2", sin tocar el resto de la línea.
- Si **CRT 4** está marcado: la línea `CRT=1,CRT1P1,CRT2C1,CRT3P2,` (el
  valor de fábrica esperado) se reemplaza ENTERA por
  `CRT=4,CRT1P1,CRT2C1,CRT3C1,CRT4C1,` — a diferencia de CRT 2, acá
  cambia también el identificador de la 3ra pantalla (de "P2" a "C1") y
  se agrega uno para la 4ta, así que no alcanza con tocar el número. Si
  la línea no es EXACTAMENTE ese valor de fábrica (por ejemplo, porque ya
  se aplicó CRT 2 antes en la misma corrida), se lanza un error explicando
  qué se esperaba, en vez de adivinar cómo transformarla.

En todos los casos se reemplaza solo el valor indicado, sin quitar las
comas ni tocar el resto de la línea (excepto CRT 4, que reemplaza la
línea completa), y es igual de idempotente que el paso del `.XRF`. Todos
los cambios se acumulan en memoria y el archivo se reescribe una sola vez,
al final, después de que todos los pasos marcados pasaron sin error — si
alguno falla (ej. CRT 2 y CRT 4 llegaran marcados juntos), el archivo en
disco queda intacto, sin ningún cambio parcial aplicado.

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
   `C:\LTP\Fonts` hacia `C:\Windows\Fonts`. Esta copia usa la función
   nativa de Windows `CopyFileW` (`kernel32.dll`, vía `ctypes`,
   `_win32_copy_file()`) y no `shutil.copy` de Python — en un equipo real
   con Windows 11 se confirmó que `shutil.copy` puede fallar con `OSError:
   [Errno 22] Invalid argument` justo al copiar hacia `C:\Windows\Fonts`
   (carpeta especial de Shell), mientras que la copia nativa de Windows —
   el mismo mecanismo que usaba el `copy` de CMD en el `.bat` original, y
   que nunca tuvo este problema — funciona sin inconvenientes. Si una
   fuente ya estaba copiada (mismo tamaño que la de origen — por ejemplo
   al reintentar la instalación en un equipo ya configurado antes), no se
   vuelve a copiar: además de innecesario, en ese estado Windows ya tiene
   esa fuente cargada/mapeada como fuente activa del sistema, y
   `CopyFileW` no puede sobrescribirla — devuelve `WinError 1224` ("...a
   file with a user-mapped section open") o, si es una fuente que Windows
   ya trae de fábrica con el mismo nombre de archivo pero de otro tamaño
   (como pasó con `ARIALN.TTF`/Arial Narrow, ya incluida en Windows 11),
   `WinError 32` ("...being used by another process") — ambos vistos en
   equipos reales. Si aun así se llega a intentar la copia y Windows
   devuelve cualquiera de esos dos errores, se trata igual como "ya
   estaba instalada" en vez de como una falla.
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

**Pasos posteriores a instalar AppShell 4.00.0030
(`app/appshell_post_install.py`):** el ítem `appshell_4_00_0030` del
catálogo tiene, después del `.msi` principal y del `vcredist`, un tercer
`extra_step` con `"installer_type": "python"` — clave
`"appshell_post_install"` — que reemplaza al script `CSS permision.bat`
que se usaba antes. Seguridad de Copa bloquea la ejecución de archivos
`.bat` en los equipos, así que esta lógica se porta directo a Python, en
2 pasos:

1. `icacls "C:\Program Files (x86)\DXC Technology" /grant
   Everyone:(OI)(CI)F /t /c` — da control total a cualquier usuario sobre
   esa carpeta y todo su contenido ya existente (`/t`), necesario para que
   AppShell pueda escribir su propia configuración ahí en tiempo de
   ejecución. Equivalente a marcar "Full control" para "Everyone" a mano
   en el diálogo de Seguridad de Windows.
2. Copia los 2 accesos directos que ya trae armados el instalador de
   AppShell (`DXC_GUI_RES\PssAppShell 4.0\Start PSS AppShell PROD.lnk` y
   `...\Start PSS AppShell TEST.lnk`, junto al `.msi` y al `vcredist`) al
   escritorio público (`C:\Users\Public\Desktop`), sobrescribiendo si ya
   existían de una instalación anterior.

Se detiene en el primer paso que falle (carpeta no encontrada, `icacls`
termina con código de salida distinto de 0, falta alguno de los 2 accesos
directos, etc.), igual que cualquier secuencia de `extra_steps` del
catálogo.

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
`COM7`, BTP → `COM8`, DCP → `COM10` — no `COM9`, para no chocar con el
puerto que ya usa la sesión OCR de Mastcom.xml, ver más abajo) y
`device.list=` recibe su identificador (ATB → `ATB1`, BTP → `BTP1`, DCP →
`DCP1`). Si la línea ya
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

- `reporte_<serie>_<fecha>.html`: para verlo o imprimirlo (se abre solo en
  el navegador al terminar).
- `reporte_<serie>_<fecha>.csv`: para importarlo a Excel u otra
  herramienta de IT.

**El nombre del archivo se identifica con el número de serie del equipo**
(`get_serial_number()`, vía WMI — `Win32_BIOS.SerialNumber`), no con el
nombre de equipo/hostname (pedido explícito): a diferencia del hostname,
que puede cambiar o quedar en un nombre genérico "DESKTOP-XXXXX" si la
unión al dominio falla (ver sección DOMINIO más abajo), el número de
serie es un identificador de hardware fijo — así siempre se puede
encontrar el reporte de un equipo puntual sin depender de cómo se
llamaba en ese momento. Si el equipo no reporta ningún número de serie
(por ejemplo, corriendo fuera de Windows), se usa el valor de respaldo
`SERIE_DESCONOCIDA` en el nombre del archivo en vez de dejarlo vacío o
roto (`_sanitize_for_filename` en `app/report.py` también reemplaza
cualquier caracter que Windows no acepte en un nombre de archivo —
espacios, `/`, `\`, etc. — por `_`). El **nombre del equipo (hostname)
sigue mostrándose sin cambios dentro del reporte**, en la tabla de datos
del equipo — esto solo cambió el nombre del archivo, no su contenido.

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

**Windows 11 mostrado como "Windows 10" (`_fix_windows_11_product_name`
en `app/report.py`):** confirmado con una captura real de un reporte
generado en una VM de prueba — la versión de Windows salía como "Windows
10 Enterprise Evaluation (Build 22621.3880)", aunque el build 22621 es en
realidad Windows 11 22H2. La causa es un bug conocido (y nunca corregido)
de Windows: la clave de registro `ProductName`
(`HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion`) sigue diciendo
literalmente "Windows 10 ..." en equipos que corren Windows 11 — Windows
10 y 11 comparten la misma rama de versión "10.0.xxxxx", así que
Microsoft nunca actualizó esa clave al pasar de uno a otro. La única
forma confiable de diferenciarlos es el número de build (Windows 11
arranca en el build 22000), no el texto de `ProductName`. Por eso
`get_windows_version()` ahora corrige el texto con
`_fix_windows_11_product_name()`: si el build leído es 22000 o más y
`ProductName` todavía dice "Windows 10", se reemplaza por "Windows 11"
antes de armar el reporte — un verdadero Windows 10 (build menor a
22000) no se toca.

Debajo va la tabla con una fila por cada aplicación que se INTENTÓ
instalar, haya tenido éxito o no: nombre, versión y fecha/hora en que
terminó (correcta o con error). Las que tuvieron éxito muestran la
versión real (tomada del campo `version` de `config/apps.json` —
actualízalo con la versión real de cada paquete). Las que fallaron
(`FAILED_VERSION_LABEL`, `app/report.py`) se distinguen de un vistazo:

- En la columna de versión se muestra literalmente **"FALLO"** en vez de
  la versión real (que nunca llegó a instalarse) — salvo el caso
  especial de abajo, que muestra únicamente **"Reinicio Pendiente"**.
- En el HTML, toda la fila se resalta en **rojo y negrita**
  (`_app_row_html` / clase CSS `row-failed`) — en el CSV (texto plano,
  sin color/negrita posible) se distinguen solo por el "FALLO" (o
  "Reinicio Pendiente") en la columna de versión.

**Caso especial dentro de las que fallan — "Reinicio Pendiente"**
(`REBOOT_PENDING_VERSION_LABEL`, `app/report.py`): cuando el ítem falló
específicamente porque el equipo necesita que el técnico lo reinicie
antes de reintentar (SAP GUI 144/145, o NetFX35/BFirst cuando se
detecta un reinicio pendiente antes de correr DISM — ver esas secciones
más arriba), la columna de versión muestra únicamente "Reinicio
Pendiente" — a propósito SIN el prefijo "FALLO", porque no es un fallo
real sin resolver: el ítem va a terminar de instalarse bien apenas el
técnico reinicie y vuelva a marcar la casilla, y mostrar "FALLO" ahí
induciría a error.
`MainWindow._on_item_finished` decide esto con
`is_reboot_pending_message()`: busca las palabras "reinicio" y
"pendiente" en el mensaje de error (en cualquier orden, sin importar
mayúsculas/minúsculas) — funciona con cualquier mensaje personalizado
del catálogo (`exit_code_messages`) o lanzado a mano en un paso
"python" que las incluya, no es específico de ningún ítem puntual.

El detalle del error en sí (mensaje completo, código de salida, etc.) NO
va en el reporte — sigue viviendo únicamente en `logs/`, donde ya queda
registrado igual que antes; el reporte solo avisa QUÉ falló, no POR QUÉ
(para eso está `logs/install_<fecha>.log`).

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
   original: ATO-BCK, ATO-COU-GTE, CGO, CTO, MTO — ver más abajo cómo
   ampliar esta lista consultando el AD real), su usuario (solo el usuario,
   sin dominio — el sufijo UPN `@copaair.com` se muestra fijo en la UI y
   Python lo agrega, ver `app/domain_join.py` para el motivo de usar UPN
   en vez del nombre corto NetBIOS) y su contraseña.
2. Al presionar "UNIR AL DOMINIO", un `DomainJoinWorker` (QThread) corre en
   segundo plano para no congelar la ventana:
   - **Usuario o contraseña incorrectos**: se le avisa al técnico con un
     mensaje claro y se limpia SOLO el campo de contraseña — equipo, OU y
     usuario quedan como estaban, para que pueda corregir y reintentar sin
     volver a escribir todo.
   - **Cualquier otro error** (OU inválida, sin red, nombre de equipo
     duplicado, etc.): se muestra el detalle y no se continúa con los pasos
     siguientes.
   - **Éxito**: se agregan los grupos de soporte (`LOCAL_ADMIN_GROUPS` en
     `app/domain_join.py`: `COPAAIR\GRP-Soporte Copa Panama`,
     `COPAAIR\GRP-SoportePTY-EST` y `COPAAIR\GRP-WebDesk`) al grupo local
     Administrators y se limpia el autologon local. Si este paso posterior
     falla, el equipo de todos modos YA quedó unido al dominio, así que se
     muestra como advertencia, no como fallo total.
3. **Reinicio**: a diferencia del script original (que reiniciaba sin
   preguntar), acá siempre se le pregunta al técnico antes de reiniciar. Si
   confirma, ANTES de reiniciar de verdad se corren NetFX35 y el
   prerequisito de DELL Command Update (ver "Aprovechar el reinicio..."
   más abajo), y recién después se ejecuta `shutdown /r /t 10` (10
   segundos de margen). Si responde que no, no se instala nada extra ni
   se reinicia — el equipo queda unido al dominio, listo para que el
   técnico reinicie por su cuenta cuando quiera.

**Aprovechar el reinicio para NetFX35 y el prerequisito de DELL Command
Update (`PostJoinExtraInstallsWorker`):** pedido explícito. NetFX35 y el
.NET Desktop Runtime (el paso `dotnet_desktop_runtime_setup`, prerequisito
de "DELL Command Update" en APPS) suelen necesitar que el equipo reinicie
para terminar de activarse (ver la sección de NetFX35/BFirst más arriba).
Como la unión al dominio YA implica un reinicio, si el técnico acepta
reiniciar acá se aprovecha ESE MISMO reinicio para dejar esos 2 también
resueltos, en vez de que el técnico tenga que reiniciar una segunda vez
más tarde al marcarlos desde APPS.

Corre los 2 pasos SIEMPRE, aunque el primero falle (son independientes
entre sí), y el resultado NUNCA bloquea el reinicio: si alguno falla
(por ejemplo, por un reinicio pendiente previo sin relación con esto), se
le avisa al técnico con un mensaje aparte ("NetFX35 / .NET Desktop
Runtime: con advertencias") indicando que puede reintentarlo después
desde APPS, pero el equipo se reinicia igual — ya hace falta para
completar la unión al dominio, sin importar qué haya pasado con estos 2
pasos extra. Si el técnico responde que NO quiere reiniciar ahora, no se
corre nada de esto — quedan pendientes para hacerse normal desde APPS.

**Validación previa del nombre del equipo (`check_computer_name_available`,
`scripts/check_computer_name.ps1`):** agregada tras un bug real reportado
en una prueba de campo. Al renombrar el equipo (ej. de `DESKTOP-E2RRTIT` a
`HDQITSTN02`) en el mismo paso que se unía al dominio, si `HDQITSTN02` YA
existía como objeto de equipo en Active Directory, `Add-Computer` unía el
equipo al dominio con éxito (bajo el nombre genérico de Windows,
`DESKTOP-E2RRTIT`) pero el renombrado fallaba después con "The account
already exists" — y ese resultado se le mostraba al técnico como un fallo
TOTAL, sin avisarle que el equipo en realidad ya había quedado unido (mal
nombrado).

La causa real no es el orden en que se hacen el join y el renombrado —
renombrar el equipo localmente antes de unirlo (en vez de dejar que
`Add-Computer -NewName` lo haga en el mismo paso) NO evita este bloqueo.
Desde octubre de 2022, Windows bloquea por seguridad la reutilización de
una cuenta de equipo ya existente en AD (KB5020276, "Netjoin: Domain join
hardening changes"), a menos que quien hace la unión sea quien creó esa
cuenta originalmente, sea Domain/Enterprise Admin, o el dueño de esa cuenta
tenga permitida la reutilización vía la directiva de grupo "Domain
controller: Allow computer account reuse during domain join" — sin
importar si el nombre ya estaba puesto localmente o se cambia en el mismo
paso del join.

Por eso el fix es **validar el nombre ANTES de intentar `Add-Computer`**,
no reordenar rename/join: `join_domain()` primero llama a
`check_computer_name_available()`, que consulta por LDAP (desde la raíz
del dominio, no solo bajo `Workstations_Copa` — el nombre debe ser único
en TODO el dominio) si ya existe un objeto `computer` con ese nombre. Si
existe, se lanza `ComputerNameExistsError` — con el DN completo del objeto
encontrado y las 3 opciones del técnico (pedir a AD que elimine ese objeto,
reintentar con las credenciales del creador original, o usar un nombre
distinto) — y el equipo **nunca llega a intentar unirse** con `Add-Computer`
(a diferencia del bug real, acá no queda unido con el nombre genérico bajo
ningún escenario). La UI muestra esto en un diálogo específico
("Nombre de equipo ya existe en Active Directory", ver `_on_name_conflict`
en `app/ui/dominio_window.py`), distinto del genérico "No se pudo unir al
dominio" de cualquier otro error. Deliberadamente esta validación NO borra
ni resetea el objeto encontrado por su cuenta — sería una operación
destructiva sobre AD sin intervención humana, así que se deja en manos del
técnico/equipo de AD decidir qué hacer.

**Botón "Cargar OUs desde AD" (`fetch_ou_list_from_ad`, `scripts/list_ous.ps1`):**
las 5 OUs de `OU_OPTIONS` son una lista fija, portada tal cual del script
original — si el AD de Copa agrega, renombra o reorganiza OUs bajo
`Workstations_Copa`, esta pantalla no se entera sola. El botón junto al
combo consulta Active Directory EN VIVO (por LDAP, con el mismo
usuario/contraseña que el técnico ya escribió para la unión al dominio) y
reemplaza el combo con las OUs reales que encuentre, en vez de la lista
fija:

- Busca únicamente bajo `OU_SEARCH_BASE_DN` ("OU=Workstations_Copa,
  DC=copaair,DC=com" — la misma rama común a las 5 opciones de arriba), no
  en todo el dominio, para no traer OUs de usuarios/servidores/otras áreas
  que no tienen nada que ver con estaciones.
- No requiere el módulo RSAT de Active Directory (`Get-ADOrganizationalUnit`
  no está disponible si ese módulo no está instalado, y normalmente NO lo
  está en un equipo recién provisionado — justo el escenario de esta app):
  usa directamente las clases `System.DirectoryServices` de .NET
  (`DirectoryEntry` + `DirectorySearcher`), disponibles en cualquier
  Windows sin instalar nada adicional.
- Corre en un `FetchOuListWorker` (QThread) para no congelar la ventana,
  con el mismo manejo de resultado que `DomainJoinWorker`: credenciales
  incorrectas limpian solo la contraseña (igual que al fallar "UNIR AL
  DOMINIO"), y cualquier otro error (sin red, `OU_SEARCH_BASE_DN` ya no
  existe, cero OUs encontradas, etc.) deja el combo TAL COMO ESTABA —
  nunca lo vacía ni lo rompe, así que si la consulta falla el técnico
  puede seguir usando la lista fija de siempre sin perder nada.
- Si la OU que estaba seleccionada antes de recargar sigue apareciendo en
  la lista nueva (mismo DN), se mantiene seleccionada después de
  recargar.
- Igual que `join_domain.ps1`, la contraseña nunca se pasa como argumento
  de línea de comandos — se lee por stdin. Única diferencia: acá se pasa
  como texto plano al constructor de `DirectoryEntry` en vez de armar un
  `PSCredential`/`SecureString` como hace `Add-Computer` — esa clase de
  .NET no tiene un overload que acepte `SecureString`, así que no hay
  forma de evitarlo en este caso puntual (sigue sin pasarse nunca por
  argumento ni quedar en disco).

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

- `check_computer_name.ps1`: consulta por LDAP si ya existe un objeto
  `computer` con el nombre elegido, ANTES de intentar el join (ver más
  arriba) — para el bug real de "the account already exists".
- `join_domain.ps1`: hace el `Add-Computer` (con `-NewName` si corresponde,
  para renombrar en el mismo paso).
- `post_join_setup.ps1`: agrega los grupos de soporte a Administrators
  (cada nombre de grupo se pasa como un solo argumento — el script original
  tenía un bug acá: `COPAAIR\GRP-Soporte Copa Panama` sin comillas se
  interpreta como varios argumentos sueltos y falla al invocarse) y limpia
  el autologon local.
- `list_ous.ps1`: consulta Active Directory por LDAP (sin RSAT) y devuelve
  todas las OUs bajo `OU_SEARCH_BASE_DN` para el botón "Cargar OUs desde
  AD" (ver más arriba).

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
├── version_info.txt          # metadatos de versión de Windows del .exe (ver "Falsos positivos de antivirus")
├── app/
│   ├── config.py             # carga/guarda apps.json, ltp_css_apps.json y settings.json
│   ├── installer.py          # motor de instalación (subprocess + QThread)
│   ├── installer_detect.py   # sugerencia de switches silenciosos para apps nuevas
│   ├── report.py             # genera el reporte HTML/CSV al terminar
│   ├── shares_config_apply.py # renombra/edita los archivos de Shares (acción "Shares Configuracion")
│   ├── shares_setup.py        # paso post-instalación de Shares 5.0 (port de "LTP setting.bat")
│   ├── shortcuts.py           # crea los accesos directos de Shares (COM) + copia los de "Shortcuts" (STN)
│   ├── appshell_config_apply.py # edita el INI (ATB/BTP/DCP) y Mastcom.xml (BGR/OCR) de "AppShell Configuracion"
│   ├── appshell_post_install.py # paso post-instalación de AppShell 4.00.0030 (reemplaza "CSS permision.bat")
│   ├── copa_id_setup.py       # "Copa ID (Asset Tag)" (APPS, 1ra columna): detecta/valida el Asset Tag y corre cctk.exe --asset=
│   ├── domain_join.py         # orquesta la unión al dominio (botón DOMINIO)
│   ├── windows_activation.py  # "Activar Windows" (APPS, 2da columna): valida dominio + slmgr.vbs /ipk /ato
│   ├── branding_setup.py      # "BackGround" (APPS, 2da columna): BGInfo + pantalla de bloqueo (port de background.bat)
│   ├── workstation_settings.py # "AJUSTES NECESARIOS" (APPS, 2da columna): Chrome/Edge/SysMain/IPv6/LGPO (port de AJUSTES_NECESARIOS.bat)
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
│   ├── check_computer_name.ps1 # valida por LDAP si el nombre ya existe en AD (ANTES de unir)
│   ├── join_domain.ps1        # Add-Computer + detección de credenciales inválidas (cod. 1326)
│   ├── post_join_setup.ps1    # grupos locales de Administrators + limpieza de autologon
│   └── list_ous.ps1           # consulta OUs de AD por LDAP (botón "Cargar OUs desde AD")
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
  `ltp_css_apps.json` — instala un `.exe`, abre otro `.exe` ya instalado
  en una ruta fija por el paso anterior, e instala un tercer `.exe`):
  ```json
  {
    "id": "custom",
    "label": "CUSTOM",
    "installer": "LTP TRAVEL DOC\\CUSTOM\\PrinterSet_3.9.7.exe",
    "installer_type": "exe",
    "extra_steps": [
      { "installer": "C:\\Program Files\\CUSTOM\\PrinterSet\\CePrinterSet.exe", "silent_args": "", "installer_type": "open" },
      { "installer": "LTP TRAVEL DOC\\CUSTOM\\DIW_KPM180H_221.exe", "silent_args": "", "installer_type": "exe" }
    ]
  }
  ```
  (Este ítem tenía antes un primer paso `open` que abría un
  `MANUAL.pdf` — se quitó porque ya no hace falta; por eso el primer
  paso ahora es directamente el `.exe` de PrinterSet.)
  Cada elemento de `extra_steps` también puede llevar una clave `version`
  puramente informativa (no la usa el motor de instalación) cuando ese
  paso instala un paquete con su propio número de versión distinto al del
  ítem principal — útil quirúrgicamente para no perder esa referencia
  cuando, como en CUSTOM, cada paso es en realidad una aplicación distinta.
- `copa_id` es un caso especial, igual que `shares_configuracion`/
  `appshell_configuracion` en `ltp_css_apps.json`: `installer` queda vacío
  a propósito porque no instala nada — es un checkbox con un campo de
  texto al lado (el Asset Tag) que, al presionar INSTALAR, corre
  `Copa_ID\cctk.exe --asset=<valor>` en vez de pasar por el motor de
  instalación genérico (ver la sección "Copa ID (Asset Tag)" más arriba y
  `app/copa_id_setup.py`).

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

## Falsos positivos de antivirus

Un `.exe` empaquetado con PyInstaller sin ningún ajuste adicional es un
candidato típico a que algún antivirus (o Windows SmartScreen) lo marque
como sospechoso o directamente lo bloquee — no porque tenga código
malicioso, sino por varias señales que también usan los empaquetadores de
malware para evadir firmas. `build.spec` ya tiene 2 ajustes para reducir
esto:

1. **`upx=False`** — UPX (el compresor que PyInstaller usa por defecto)
   cambia la forma en que quedan los bytes del `.exe`, de una manera muy
   parecida a como muchos malware empaquetan el suyo para evadir firmas
   antivirus. Es de las causas más comunes de falso positivo en binarios
   de PyInstaller/Python en general. Desactivarlo deja el `.exe` más
   pesado, pero reduce bastante ese riesgo.
2. **`version='version_info.txt'`** — agrega metadatos de versión de
   Windows (CompanyName, FileDescription, ProductName, etc., visibles en
   Propiedades → Detalles del `.exe` en el Explorador). Un `.exe` sin esta
   información se ve "en blanco" (sin publisher, sin versión), otra señal
   que revisan tanto antivirus como SmartScreen.

Estos 2 cambios ayudan, pero **no reemplazan la firma digital
(Authenticode)** — la señal más fuerte de todas, y la que de verdad resuelve
el problema de raíz en vez de solo mitigarlo:

- Si Copa tiene una CA interna (la mayoría de las empresas con Active
  Directory la tienen) que ya está en la lista de confianza de los equipos
  del dominio, pedirle a Seguridad/Infraestructura un certificado de firma
  de código (*code signing*) de esa CA interna es lo más rápido — los
  equipos ya confían en esa CA sin necesitar que Windows/el antivirus
  "acumule reputación" del archivo con el tiempo. Firmar el `.exe` después
  de compilarlo:
  ```bat
  signtool sign /a /fd sha256 /tr http://timestamp.digicert.com /td sha256 dist\FS_APP_STN.exe
  ```
  (`signtool` viene con el Windows SDK; el parámetro `/tr` agrega un
  timestamp para que la firma siga siendo válida después de que venza el
  certificado).
- Si no hay CA interna disponible para esto, un certificado de firma de
  código de una CA pública (DigiCert, Sectigo, etc.) también funciona,
  aunque toma más tiempo/costo conseguirlo.
- **Mientras tanto** (sin firma todavía), otras 2 vías rápidas y sin costo,
  típicas para un despliegue interno como este:
  - **Excepción/lista blanca por hash o ruta vía política del antivirus
    empresarial** (Microsoft Defender ASR, o la consola del EDR/antivirus
    que use Copa) — al ser un despliegue controlado a equipos del dominio,
    esto suele ser más rápido que esperar que el antivirus "aprenda" que
    el archivo es confiable por su cuenta.
  - **Enviar el `.exe` a revisión de falso positivo**: a Microsoft
    (https://www.microsoft.com/en-us/wdsi/filesubmission, si el antivirus
    en cuestión es Defender) y/o subirlo a VirusTotal para ver qué
    motores lo marcan — varios antivirus tienen su propio formulario de
    "falso positivo" parecido al de Microsoft.

Nota aparte: cada vez que se recompila el `.exe` (cada `pyinstaller
build.spec` nuevo) el archivo resultante es un binario distinto con un hash
distinto — cualquier reputación o excepción que se haya ganado/agregado
para una versión anterior no se traslada automáticamente a la nueva, así
que conviene planear firmar (o volver a pedir la excepción) como parte del
proceso de cada release, no como un paso de una sola vez.

## Logs

Cada instalación queda registrada en `logs/install_YYYY-MM-DD.log` con
hora, comando ejecutado y código de salida. Se consideran éxito los
códigos 0, 3010 (éxito con reinicio pendiente) y 1638 (`ERROR_PRODUCT_VERSION`
del Windows Installer: "ya hay otra versión de este producto instalada" —
típico en paquetes vcredist cuando ya está presente una versión igual o
más nueva; no es un fallo real, no hay nada que instalar). Cuando un paso
falla, el log también registra stdout y stderr por separado (o aclara que
el instalador no escribió nada en ninguno de los dos, si así fue).

"Shares Configuracion" y "AppShell Configuracion" (`LtpCssWindow._run_shares_configuration()`
y `_run_appshell_configuration()`) no pasan por `InstallManager`/`InstallWorker`
como el resto de la cola, así que tienen su propia instancia de
`InstallLogger` (`LtpCssWindow.logger`, creada en `__init__`) y escriben ahí
mismo su resultado (`OK (...)` o `ERROR - ...`) al terminar. Antes de esto,
un fallo en cualquiera de las dos quedaba solo en la casilla y en
`status_label` — nunca en `logs/`, aunque el diálogo final ("Instalación
finalizada") siempre le indica al técnico que revise esa carpeta para el
detalle.

## Próximos pasos sugeridos

1. Confirmar los `silent_args` y rutas de instalador reales de cada
   aplicación contra los paquetes que usa Copa, tanto en `config/apps.json`
   como en `config/ltp_css_apps.json` (los valores de LTP / CSS son
   placeholders puestos como referencia mientras se arma el catálogo).
2. Seguir agregando, "por partes", las demás condiciones de la pantalla
   LTP / CSS que todavía faltan (por ahora están implementadas la
   selección única entre GEMALTO / 3M / DESKO y el panel completo de
   "Shares Configuracion", incluyendo sus secciones DEVICES y CRT's).
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
