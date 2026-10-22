"""Pfad-Helfer. Funktioniert im Quellcode UND in der PyInstaller-EXE."""
import os
import sys
from pathlib import Path


def resource_path(rel: str) -> str:
    """Pfad zu einer mitgelieferten Datei (assets/...) - auch nach dem EXE-Build."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parent.parent
    return str(Path(base) / rel)


def _pick_home() -> Path:
    env = os.environ.get("JARVIS_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        return Path("C:/jarvis")
    return Path.home() / "jarvis"


def home_dir() -> Path:
    """Zentraler Datenordner (Windows: C:\\jarvis). Wird NIE automatisch geloescht."""
    p = _pick_home()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = Path.home() / "jarvis"
        p.mkdir(parents=True, exist_ok=True)
    return p


def sub_dir(name: str) -> Path:
    p = home_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    return sub_dir("data")


def log_dir() -> Path:
    return sub_dir("logs")
