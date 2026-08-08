"""Carga y guardado de la configuración de la aplicación.

Las rutas se resuelven junto al ejecutable (o al script, si se corre con
`python main.py`) para que los técnicos puedan editar `config/apps.json` y
`config/settings.json` sin tener que reconstruir el .exe.
"""
from __future__ import annotations

import json
import sys
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


APP_ROOT = get_app_root()
CONFIG_DIR = APP_ROOT / "config"
LOGS_DIR = APP_ROOT / "logs"
APPS_FILE = CONFIG_DIR / "apps.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
ASSETS_DIR = get_assets_dir()


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
    installers_base_path: str = r"C:\Instaladores"
    logs_path: str = "logs"
    run_mode: str = "sequential"  # sequential | parallel
    confirm_before_install: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "installers_base_path": self.installers_base_path,
            "logs_path": self.logs_path,
            "run_mode": self.run_mode,
            "confirm_before_install": self.confirm_before_install,
        }


def load_settings() -> Settings:
    if not SETTINGS_FILE.exists():
        return Settings()
    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return Settings(
        installers_base_path=data.get("installers_base_path", Settings.installers_base_path),
        logs_path=data.get("logs_path", Settings.logs_path),
        run_mode=data.get("run_mode", Settings.run_mode),
        confirm_before_install=data.get("confirm_before_install", Settings.confirm_before_install),
    )


def save_settings(settings: Settings) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_app_columns() -> list[AppColumn]:
    data = json.loads(APPS_FILE.read_text(encoding="utf-8"))
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
                )
                for it in grp.get("items", [])
            ]
            groups.append(AppGroup(items=items))
        columns.append(AppColumn(groups=groups))
    return columns
