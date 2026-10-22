"""Kontrollierte Windows-Aktionen (keine freie Shell)."""
import ctypes
import datetime as _dt
import os
import sys

from core import logger
from core.paths import sub_dir

log = logger.get("winactions")

VK = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3,
      "next_track": 0xB0, "prev_track": 0xB1}
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "Maerz", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]


def _press(vk, times=1):
    u = ctypes.windll.user32
    for _ in range(times):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)


def run(action: str):
    """-> (ok, text)"""
    now = _dt.datetime.now()
    if action == "time":
        return True, "Es ist %s Uhr, Sir." % now.strftime("%H:%M")
    if action == "date":
        return True, "Heute ist %s, der %d. %s %d." % (WEEKDAYS[now.weekday()], now.day, MONTHS[now.month - 1], now.year)
    if os.name != "nt":
        return False, "Diese Aktion gibt es nur unter Windows."
    try:
        if action in VK:
            _press(VK[action], 5 if action in ("volume_up", "volume_down") else 1)
            return True, {"volume_up": "Lauter.", "volume_down": "Leiser.", "mute": "Ton umgeschaltet.",
                          "play_pause": "Wiedergabe umgeschaltet.", "next_track": "Naechster Titel.",
                          "prev_track": "Vorheriger Titel."}[action]
        if action == "lock":
            ctypes.windll.user32.LockWorkStation()
            return True, "Der Rechner ist gesperrt."
        if action == "screenshot":
            from PIL import ImageGrab
            path = sub_dir("screenshots") / now.strftime("screenshot_%Y%m%d_%H%M%S.png")
            ImageGrab.grab(all_screens=True).save(path)
            return True, "Screenshot gespeichert unter %s." % path.name
    except Exception as e:
        log.exception("Windows-Aktion %s", action)
        return False, "Die Aktion ist fehlgeschlagen: %s" % type(e).__name__
    return False, "Diese Aktion kenne ich nicht."


def set_autostart(enabled: bool):
    if os.name != "nt":
        return
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    try:
        if enabled:
            exe = sys.executable if getattr(sys, "frozen", False) else '"%s" "%s"' % (sys.executable, os.path.abspath(sys.argv[0]))
            winreg.SetValueEx(key, "JARVIS", 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(key, "JARVIS")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
