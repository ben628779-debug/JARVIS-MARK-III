"""Einstellungen (settings.json) + sicherer Speicher fuer API-Keys.

Geheimnisse (API-Keys, Passwoerter) liegen im Windows-Anmeldeinformationsspeicher
(keyring). Alternativ koennen sie ueber Umgebungsvariablen / .env gesetzt werden.
Sie stehen NIE im Quellcode und NIE im Klartext in Logs.
"""
import base64
import json
import os
import threading

from core import logger
from core.paths import data_dir, home_dir

log = logger.get("config")

SERVICE = "JARVIS"

# key -> Umgebungsvariable
SECRET_KEYS = {
    "gemini_api_key": "GEMINI_API_KEY",
    "elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "fish_api_key": "FISH_AUDIO_API_KEY",
    "mail_password": "JARVIS_MAIL_PASSWORD",
    "twilio_sid": "TWILIO_ACCOUNT_SID",
    "twilio_token": "TWILIO_AUTH_TOKEN",
}

DEFAULTS = {
    "language": "de-DE",
    "gemini_model": "gemini-flash-latest",
    # Stimme
    "tts_provider": "edge",                   # edge | elevenlabs | fish
    "edge_voice": "de-DE-KillianNeural",
    "edge_rate": "+0%",
    "elevenlabs_voice_id": "cCwaxHZZF7rVaQK2aOys",
    "elevenlabs_model": "eleven_multilingual_v2",
    "fish_voice_id": "",
    "fish_model": "s1",
    "volume": 90,
    # Audio
    "input_device": "",
    "output_device": "",
    # Aktivierung
    "wake_word_enabled": True,
    "clap_enabled": True,
    "follow_up_enabled": True,
    "mic_threshold": 0.015,
    # Look
    "accent": "ice",                          # ice | blue | cyan | green | orange | red
    "particle_quality": "high",               # low | medium | high
    "rotate_rings": False,
    # System
    "autostart": False,
    "start_minimized": False,
    "debug": False,
    "learning_enabled": True,
    # Mail
    "mail_provider": "outlook",               # outlook | gmail | imap
    "mail_address": "",
    "imap_host": "",
    "smtp_host": "",
    "azure_client_id": "",
    # Telefon
    "twilio_from": "",
    "my_phone": "",
    "allowed_numbers": "",
    "call_limit_per_day": 5,
    # eigene Programme  {"name": "C:\\Pfad\\programm.exe"}
    "custom_apps": {},
}


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows-DPAPI: nur dein Windows-Benutzer kann die Datei entschluesseln. Ausserhalb von Windows: unveraendert."""
    if os.name != "nt":
        return data
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    inb = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    outb = BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(outb)):
        raise OSError("DPAPI fehlgeschlagen")
    try:
        return ctypes.string_at(outb.pbData, outb.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outb.pbData)


class SecretStore:
    """API-Keys & Passwoerter: <home>/data/secrets.dat (Windows-DPAPI verschluesselt).
    Aeltere Keys aus dem Windows-Anmeldeinformationsspeicher werden automatisch uebernommen."""

    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
        self._path = data_dir() / "secrets.dat"
        self._file = self._read_file()

    def _read_file(self):
        try:
            if self._path.exists():
                return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            log.error("secrets.dat unlesbar: %s", type(e).__name__)
        return {}

    def _write_file(self) -> bool:
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._file), encoding="utf-8")
            os.replace(tmp, self._path)
            return True
        except Exception as e:
            log.error("secrets.dat schreiben fehlgeschlagen: %s", e)
            return False

    def _from_file(self, key):
        raw = self._file.get(key)
        if not raw:
            return ""
        try:
            return _dpapi(base64.b64decode(raw), False).decode("utf-8")
        except Exception as e:
            log.error("Key %s nicht entschluesselbar: %s", key, type(e).__name__)
            return ""

    def get(self, key: str) -> str:
        with self._lock:
            if key in self._cache and self._cache[key]:
                return self._cache[key]
            val = self._from_file(key)
            if not val:
                try:                                    # Altbestand uebernehmen
                    import keyring
                    val = keyring.get_password(SERVICE, key) or ""
                    if val:
                        self._file[key] = base64.b64encode(_dpapi(val.encode("utf-8"), True)).decode("ascii")
                        self._write_file()
                except Exception:
                    val = ""
            if not val:
                val = os.environ.get(SECRET_KEYS.get(key, ""), "") or ""
            self._cache[key] = val
        logger.register_secret(val)
        return val

    def set(self, key: str, value: str) -> bool:
        value = (value or "").strip()
        with self._lock:
            self._cache[key] = value
            if value:
                self._file[key] = base64.b64encode(_dpapi(value.encode("utf-8"), True)).decode("ascii")
            else:
                self._file.pop(key, None)
            ok = self._write_file()
            if ok and value:
                ok = self._from_file(key) == value          # Gegenprobe: wirklich gespeichert?
        logger.register_secret(value)
        if not ok:
            log.error("Key %s konnte nicht dauerhaft gespeichert werden", key)
        return ok


class Settings:
    def __init__(self):
        self.path = data_dir() / "settings.json"
        self._data = dict(DEFAULTS)
        self._listeners = []
        self.secrets = SecretStore()
        self.load()

    def load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update({k: v for k, v in saved.items() if k in DEFAULTS or k.startswith("perm_")})
        except Exception as e:
            log.error("settings.json defekt: %s", e)

    def save(self) -> bool:
        ok = True
        try:
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            with open(self.path, "r", encoding="utf-8") as f:       # Gegenprobe
                ok = json.load(f) == json.loads(json.dumps(self._data))
        except Exception as e:
            ok = False
            log.error("settings.json speichern fehlgeschlagen: %s", e)
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                log.exception("settings listener")
        return ok

    def on_change(self, cb):
        self._listeners.append(cb)

    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value

    def secret(self, key) -> str:
        return self.secrets.get(key)


class LaunchState:
    """Merkt sich, wie oft J.A.R.V.I.S schon gestartet wurde (fuer die Begruessung)."""

    def __init__(self):
        self.path = data_dir() / "state.json"
        self.data = {"launch_count": 0}
        try:
            if self.path.exists():
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            pass

    @property
    def is_first_launch(self) -> bool:
        return int(self.data.get("launch_count", 0)) == 0

    def register_launch(self):
        self.data["launch_count"] = int(self.data.get("launch_count", 0)) + 1
        try:
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
        except Exception as e:
            log.error("state.json: %s", e)


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(home_dir() / ".env")
        load_dotenv()
    except Exception:
        pass
