"""Carga y guardado de la configuración de la aplicación.

Las rutas se resuelven junto al ejecutable (o al script, si se corre con
`python main.py`) para que los técnicos puedan editar `config/apps.json` y
`config/settings.json` sin tener que reconstruir el .exe.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def get_app_root() -> Path:
    """Carpeta base de la app: junto al .exe cuando está empaquetada con
    PyInstaller (--onefile), o la raíz del proyecto cuando se corre desde
    código fuente."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_assets_dir() -> Path:
    """Carpeta de recursos estáticos (íconos, etc.).

    A diferencia de `config/`, estos archivos no los edita el técnico, así
    que sí se empaquetan dentro del .exe (PyInstaller los extrae en una
    carpeta temporal referenciada por `sys._MEIPASS`)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "assets"
        return get_app_root() / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def get_scripts_dir() -> Path:
    """Carpeta de scripts auxiliares (PowerShell, etc.) que la app invoca
    pero que el técnico no necesita editar — igual que `get_assets_dir()`,
    se empaquetan dentro del .exe y PyInstaller los extrae a una carpeta
    temporal (`sys._MEIPASS`) al arrancar."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "scripts"
        return get_app_root() / "scripts"
    return Path(__file__).resolve().parent.parent / "scripts"


def get_default_installers_base_path() -> str:
    """Carpeta de instaladores por defecto: `CM APPS\\APPS` dentro de la
    MISMA unidad (letra de disco) desde la que se está ejecutando la app en
    este momento. Así funciona igual sin tocar nada si el .exe corre desde
    el disco local (`C:`) o desde una memoria USB (`E:`, `F:`, etc.) — cada
    copia de la app usa su propia unidad como base, sin depender de que la
    letra de la USB sea siempre la misma."""
    root = get_app_root()
    drive = root.drive  # ej. "C:" en Windows; "" fuera de Windows (dev)
    if drive:
        return str(Path(drive + "\\") / "CM APPS" / "APPS")
    return str(root / "CM APPS" / "APPS")


APP_ROOT = get_app_root()
CONFIG_DIR = APP_ROOT / "config"
LOGS_DIR = APP_ROOT / "logs"
APPS_FILE = CONFIG_DIR / "apps.json"
LTP_CSS_APPS_FILE = CONFIG_DIR / "ltp_css_apps.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
ASSETS_DIR = get_assets_dir()
SCRIPTS_DIR = get_scripts_dir()


@dataclass
class AppItem:
    id: str
    label: str
    installer: str
    silent_args: str = ""
    installer_type: str = "exe"  # exe | msi | script
    default_checked: bool = False
    enabled: bool = True
    version: str = "N/D"
    # Si no está vacío, este ítem forma parte de un grupo de selección única
    # (como un radio button): todos los ítems con el mismo valor se dibujan
    # juntos en una fila y solo se puede marcar uno a la vez (ver
    # app/ui/catalog_widgets.py). Ejemplo: GEMALTO / 3M / DESKO.
    exclusive_group: str = ""

    def resolved_installer_path(self, installers_base_path: str) -> Path:
        base = Path(installers_base_path)
        return base / self.installer


@dataclass
class AppGroup:
    items: list[AppItem] = field(default_factory=list)


@dataclass
class AppColumn:
    groups: list[AppGroup] = field(default_factory=list)


@dataclass
class Settings:
    installers_base_path: str = field(default_factory=get_default_installers_base_path)
    logs_path: str = "logs"
    run_mode: str = "sequential"  # sequential | parallel

    def to_dict(self) -> dict[str, Any]:
        return {
            "installers_base_path": self.installers_base_path,
            "logs_path": self.logs_path,
            "run_mode": self.run_mode,
        }


def load_settings() -> Settings:
    if not SETTINGS_FILE.exists():
        return Settings()
    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return Settings(
        installers_base_path=data.get("installers_base_path") or get_default_installers_base_path(),
        logs_path=data.get("logs_path", Settings.logs_path),
        run_mode=data.get("run_mode", Settings.run_mode),
    )


def save_settings(settings: Settings) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def save_app_versions(updates: dict[str, str], apps_file: Path = APPS_FILE) -> None:
    """Actualiza únicamente el campo `version` de los ítems indicados en
    `updates` ({item_id: nueva_version}) dentro de `apps_file` (por defecto
    `config/apps.json`; pásale `LTP_CSS_APPS_FILE` para el catálogo de
    LTP / CSS), dejando todo lo demás (instalador, argumentos, grupos, etc.)
    intacto."""
    if not updates:
        return
    data = json.loads(apps_file.read_text(encoding="utf-8"))
    for col in data.get("columns", []):
        for grp in col.get("groups", []):
            for it in grp.get("items", []):
                if it.get("id") in updates:
                    it["version"] = updates[it["id"]]
    apps_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def slugify_id(label: str, existing_ids: set[str]) -> str:
    """Genera un id único (estilo `snake_case`, sin acentos) a partir del
    nombre visible de una app nueva, evitando choques con ids que ya existen
    en el catálogo (les agrega un sufijo numérico si hace falta)."""
    normalized = unicodedata.normalize("NFKD", label)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "_", ascii_only.lower()).strip("_")
    if not base:
        base = "app"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def add_app_item(column_index: int, item: dict[str, Any], apps_file: Path = APPS_FILE) -> None:
    """Agrega un ítem nuevo a `apps_file` (por defecto `config/apps.json`;
    pásale `LTP_CSS_APPS_FILE` para el catálogo de LTP / CSS), dentro del
    primer grupo de la columna indicada (0, 1 o 2). Si la columna no tiene
    ningún grupo todavía, crea uno. No toca ningún otro ítem existente."""
    data = json.loads(apps_file.read_text(encoding="utf-8"))
    columns = data.setdefault("columns", [])
    while len(columns) <= column_index:
        columns.append({"groups": []})
    groups = columns[column_index].setdefault("groups", [])
    if not groups:
        groups.append({"items": []})
    groups[0].setdefault("items", []).append(item)
    apps_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def update_app_installer(
    item_id: str,
    installer: str | None = None,
    version: str | None = None,
    apps_file: Path = APPS_FILE,
) -> None:
    """Actualiza el campo `installer` y/o `version` de un ítem que YA existe
    en `apps_file` (por defecto `config/apps.json`; pásale
    `LTP_CSS_APPS_FILE` para el catálogo de LTP / CSS) — usado al reemplazar
    el instalador de una app del catálogo por una versión nueva. No toca
    ningún otro campo ni ítem."""
    data = json.loads(apps_file.read_text(encoding="utf-8"))
    for col in data.get("columns", []):
        for grp in col.get("groups", []):
            for it in grp.get("items", []):
                if it.get("id") == item_id:
                    if installer is not None:
                        it["installer"] = installer
                    if version is not None:
                        it["version"] = version
    apps_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def remove_app_item(item_id: str, apps_file: Path = APPS_FILE) -> None:
    """Elimina un ítem del catálogo (`apps_file`, por defecto
    `config/apps.json`; pásale `LTP_CSS_APPS_FILE` para el catálogo de
    LTP / CSS) por su id. Esta función solo toca el JSON — borrar la
    carpeta del instalador en disco (si corresponde) es responsabilidad de
    quien la llama."""
    data = json.loads(apps_file.read_text(encoding="utf-8"))
    for col in data.get("columns", []):
        for grp in col.get("groups", []):
            grp["items"] = [it for it in grp.get("items", []) if it.get("id") != item_id]
    apps_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_app_columns(source_file: Path = APPS_FILE) -> list[AppColumn]:
    """Carga un catálogo de aplicaciones desde un archivo JSON con el mismo
    formato que `config/apps.json`. Por defecto lee ese archivo (el
    catálogo de APPS); pásale `LTP_CSS_APPS_FILE` (u otro) para cargar un
    catálogo distinto, como el de la pantalla LTP / CSS."""
    data = json.loads(source_file.read_text(encoding="utf-8"))
    columns: list[AppColumn] = []
    for col in data.get("columns", []):
        groups: list[AppGroup] = []
        for grp in col.get("groups", []):
            items = [
                AppItem(
                    id=it["id"],
                    label=it["label"],
                    installer=it["installer"],
                    silent_args=it.get("silent_args", ""),
                    installer_type=it.get("installer_type", "exe"),
                    default_checked=it.get("default_checked", False),
                    enabled=it.get("enabled", True),
                    version=it.get("version", "N/D"),
                    exclusive_group=it.get("exclusive_group", ""),
                )
                for it in grp.get("items", [])
            ]
            groups.append(AppGroup(items=items))
        columns.append(AppColumn(groups=groups))
    return columns
