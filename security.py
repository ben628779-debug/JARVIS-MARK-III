"""Berechtigungen, Not-Aus und Audit-Log.

Jede Faehigkeit hat einen eigenen Schalter (Einstellungen -> Permissions).
Der Not-Aus (EMERGENCY STOP) sperrt alle externen Aktionen sofort.
"""
import datetime as _dt
import threading

from core import logger
from core.paths import log_dir

log = logger.get("security")

# name -> (Beschreibung, Standard)
PERMISSIONS = {
    "OPEN_APPS": ("Programme / Webseiten oeffnen", True),
    "FILES_OPEN": ("Dateien & Ordner oeffnen", True),
    "FILES_DELETE": ("Dateien loeschen (immer mit Rueckfrage)", True),
    "WEB_SEARCH": ("Websuche / Internet-Abfragen", True),
    "SYSTEM_ACTIONS": ("Lautstaerke, Medien, Screenshot, Sperren", True),
    "READ_EMAIL": ("E-Mails lesen / zusammenfassen / sortieren", True),
    "SEND_EMAIL": ("E-Mails senden (immer mit Rueckfrage)", True),
    "DELETE_EMAIL": ("E-Mails loeschen/verschieben (immer mit Rueckfrage)", True),
    "PHONE_CALL": ("Mich per Telefon anrufen (nur eigene Nummer)", False),
    "SMS": ("SMS an meine Nummer senden", False),
    "LEARNING": ("Aus Gespraechen lernen / Erinnerungen speichern", True),
}


class Security:
    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.killed = False
        self._audit_path = log_dir() / "audit.log"

    def allowed(self, name: str) -> bool:
        if self.killed:
            return False
        default = PERMISSIONS.get(name, ("", False))[1]
        return bool(self.settings.get("perm_" + name, default))

    def set_permission(self, name: str, value: bool):
        self.settings.set("perm_" + name, bool(value))

    def emergency_stop(self, on: bool = True):
        self.killed = on
        self.audit("EMERGENCY_STOP", "aktiviert" if on else "aufgehoben")

    def audit(self, action: str, detail: str = "", ok: bool = True):
        line = "%s | %-16s | %s | %s\n" % (
            _dt.datetime.now().isoformat(timespec="seconds"), action, "OK" if ok else "FAIL", detail[:300])
        with self._lock:
            try:
                with open(self._audit_path, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError:
                pass
