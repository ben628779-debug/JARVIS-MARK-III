"""Prueft und installiert fehlende Python-Pakete (jedes einzeln - ein Fehler blockiert nicht die anderen)."""
import importlib.util
import subprocess
import sys

# import-Name -> (pip-Paket, noetig?)
PACKAGES = {
    "numpy": ("numpy", True),
    "requests": ("requests", True),
    "sounddevice": ("sounddevice", True),
    "soundfile": ("soundfile", True),
    "speech_recognition": ("SpeechRecognition", True),
    "edge_tts": ("edge-tts", True),
    "send2trash": ("send2trash", True),
    "msal": ("msal", True),
    "PIL": ("Pillow", True),
    "dotenv": ("python-dotenv", False),
    "pyttsx3": ("pyttsx3", False),
    "miniaudio": ("miniaudio", False),
}


def missing(required_only=False):
    out = []
    for mod, (pip_name, needed) in PACKAGES.items():
        if required_only and not needed:
            continue
        try:
            found = importlib.util.find_spec(mod) is not None
        except Exception:
            found = False
        if not found:
            out.append(pip_name)
    return out


def can_install() -> bool:
    return not getattr(sys, "frozen", False)


def install(pkgs, progress=None):
    """-> (installiert, fehlgeschlagen). progress(text) optional."""
    ok, failed = [], []
    for pkg in pkgs:
        if progress:
            progress("Installiere %s ..." % pkg)
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--prefer-binary", pkg],
                               capture_output=True, text=True, timeout=600)
            (ok if r.returncode == 0 else failed).append(pkg)
        except Exception:
            failed.append(pkg)
    importlib.invalidate_caches()
    return ok, failed
