"""Ordner/Dateien sicher oeffnen und (nur mit Rueckfrage) in den Papierkorb legen."""
import os
from pathlib import Path

from core import logger
from core.paths import home_dir

log = logger.get("files")

NAMES = {"downloads": "Downloads", "desktop": "Desktop", "documents": "Documents",
         "pictures": "Pictures", "music": "Music", "videos": "Videos"}


def folder_path(key: str):
    if key == "jarvis":
        return home_dir()
    base = Path.home()
    p = base / NAMES.get(key, key)
    if os.name == "nt" and not p.exists():
        od = Path(os.environ.get("OneDrive", "")) / NAMES.get(key, key)
        if od.exists():
            return od
    return p if p.exists() else None


def search_roots():
    return [p for p in (folder_path(k) for k in ("desktop", "documents", "downloads", "pictures", "music", "videos")) if p]


def find_file(name: str, max_depth=3):
    name = name.lower().strip()
    best = None
    for root in search_roots():
        base_depth = len(root.parts)
        for dirpath, dirs, files in os.walk(root):
            if len(Path(dirpath).parts) - base_depth >= max_depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                low = f.lower()
                if low == name:
                    return Path(dirpath) / f
                if name in low and best is None:
                    best = Path(dirpath) / f
    return best


def open_path(p: Path):
    if os.name == "nt":
        os.startfile(str(p))  # noqa: S606 - nur geprueftes, existierendes Ziel
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(p)])


def _inside_roots(p: Path):
    rp = p.resolve()
    return any(str(rp).startswith(str(r.resolve())) for r in search_roots())


def trash_file(p: Path):
    """In den Papierkorb (nicht endgueltig) - nur innerhalb von Desktop/Dokumente/Downloads/... ."""
    if not _inside_roots(p):
        raise PermissionError("Datei liegt ausserhalb der freigegebenen Ordner.")
    from send2trash import send2trash
    send2trash(str(p))
