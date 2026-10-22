"""Robuster Programmstart unter Windows.

Suchreihenfolge:
  1. eigene Programme (Einstellungen: custom_apps)
  2. gelernte Programme (Gedaechtnis)
  3. bekannte Programme (KNOWN)
  4. PROGRAMM-INDEX: Get-StartApps (Startmenue inkl. Store-Apps) + Startmenue-/Desktop-Verknuepfungen
     + Registry (installierte Programme), mit unscharfer Suche (Spracherkennungs-Fehler!)
  5. PATH / App-Paths-Registry
Es wird NIE ein Text aus der KI als Shell-Befehl ausgefuehrt - nur geprueftes Ziel oeffnen.
"""
import difflib
import os
import re
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

from core import logger

log = logger.get("launcher")

PF = os.environ.get("ProgramFiles", r"C:\Program Files")
PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
LOCAL = os.environ.get("LOCALAPPDATA", "")
APPDATA = os.environ.get("APPDATA", "")
CREATE_NO_WINDOW = 0x08000000

# Anzeigename -> Kandidaten: URI ("steam://"), Datei-Pfad oder exe-Name
KNOWN = {
    "steam": ["steam://open/main", PF86 + r"\Steam\steam.exe", PF + r"\Steam\steam.exe"],
    "discord": [LOCAL + r"\Discord\Update.exe --processStart Discord.exe", "discord://"],
    "spotify": ["spotify:", APPDATA + r"\Spotify\Spotify.exe"],
    "chrome": [PF + r"\Google\Chrome\Application\chrome.exe", PF86 + r"\Google\Chrome\Application\chrome.exe",
               LOCAL + r"\Google\Chrome\Application\chrome.exe"],
    "edge": ["msedge"], "firefox": [PF + r"\Mozilla Firefox\firefox.exe"],
    "visual studio code": [LOCAL + r"\Programs\Microsoft VS Code\Code.exe", PF + r"\Microsoft VS Code\Code.exe", "code"],
    "notepad": ["notepad.exe"], "editor": ["notepad.exe"], "rechner": ["calc.exe"], "taschenrechner": ["calc.exe"],
    "calculator": ["calc.exe"], "paint": ["mspaint.exe"], "explorer": ["explorer.exe"],
    "datei explorer": ["explorer.exe"], "task manager": ["taskmgr.exe"], "taskmanager": ["taskmgr.exe"],
    "einstellungen": ["ms-settings:"], "settings": ["ms-settings:"], "terminal": ["wt.exe", "cmd.exe"],
    "cmd": ["cmd.exe"], "eingabeaufforderung": ["cmd.exe"], "powershell": ["powershell.exe"],
    "word": ["winword.exe"], "excel": ["excel.exe"], "powerpoint": ["powerpnt.exe"],
    "telegram": [APPDATA + r"\Telegram Desktop\Telegram.exe"],
    "epic games": [PF86 + r"\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe"],
    "obs": [PF + r"\obs-studio\bin\64bit\obs64.exe"], "vlc": [PF + r"\VideoLAN\VLC\vlc.exe"],
}
# Spracherkennung verhoert sich gern -> haeufige Varianten
ALIASES = {
    "dc": "discord", "diskord": "discord", "diskort": "discord", "dis cord": "discord", "discort": "discord",
    "stim": "steam", "stiem": "steam", "steem": "steam", "stean": "steam", "schtiem": "steam",
    "spotifai": "spotify", "spotifei": "spotify", "spotty": "spotify", "spotti": "spotify",
    "krom": "chrome", "google chrome": "chrome", "browser": "chrome", "internet": "chrome",
    "microsoft edge": "edge", "vscode": "visual studio code", "vs code": "visual studio code",
    "code": "visual studio code", "visual studio kot": "visual studio code", "vs kot": "visual studio code",
    "exel": "excel", "microsoft word": "word", "microsoft excel": "excel", "microsoft powerpoint": "powerpoint",
    "oudlook": "outlook", "aotlook": "outlook", "whatsapp": "whatsapp", "wotsapp": "whatsapp",
    "whats app": "whatsapp", "tim speak": "teamspeak", "team speak": "teamspeak",
}
_LEAD = re.compile(r"^(?:(?:die|den|das|der|dem|meine|meinen|mein|app|anwendung|programm|applikation)\s+)+")
_TRAIL = re.compile(r"(?:\s+(?:bitte|mal|doch|jetzt|kurz|schnell|einmal|nochmal|fuer mich|für mich|auf|an|starten|oeffnen|öffnen))+$")


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9äöüß ]", " ", s.lower())).strip()


def clean_name(name: str) -> str:
    key = _norm(name)
    for _ in range(3):
        key = _LEAD.sub("", key)
        key = _TRAIL.sub("", key).strip()
    return ALIASES.get(key, key)


def _score(key, name):
    """Aehnlichkeit Suchbegriff <-> Programmname (0..100)."""
    if key == name:
        return 100
    kt, nt = key.split(), name.split()
    if not kt or not nt:
        return 0
    if set(kt) <= set(nt):
        return 92 - min(len(nt), 8)
    if len(name) >= 3 and set(nt) <= set(kt):
        return 85 - min(len(kt), 8)
    if len(key) >= 3 and name.startswith(key):
        return 78
    if len(key) >= 4 and key in name:
        return 70
    r = max([difflib.SequenceMatcher(None, key, name).ratio()] +
            [difflib.SequenceMatcher(None, key, t).ratio() for t in nt])
    return 50 + (r - 0.75) * 100 if r >= 0.75 else 0


def _run_ps(script, timeout=30):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script],
                       capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    return r.stdout.decode("utf-8", "replace")


def _registry_app_path(exe):
    if os.name != "nt":
        return None
    import winreg
    exe = exe if exe.lower().endswith(".exe") else exe + ".exe"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe) as k:
                v, _ = winreg.QueryValueEx(k, "")
                if v and os.path.exists(v.strip('"')):
                    return v.strip('"')
        except OSError:
            continue
    return None


class AppLauncher:
    def __init__(self, settings, memory):
        self.settings = settings
        self.memory = memory
        self.index = {}          # normierter Name -> (Anzeigename, Ziel)
        self.stats = {}
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._building = False

    # ------------------------------------------------------------------ Index
    def warmup(self, force=False):
        """Baut den Programm-Index im Hintergrund."""
        with self._lock:
            if self._building:
                return
            if self._ready.is_set() and not force:
                return
            self._building = True
            self._ready.clear()
        threading.Thread(target=self._build, daemon=True, name="app-index").start()

    def _build(self):
        idx, stats = {}, {"startapps": 0, "links": 0, "registry": 0, "fehler": ""}
        try:
            if os.name == "nt":
                self._scan_startapps(idx, stats)
                self._scan_links(idx, stats)
                self._scan_registry(idx, stats)
        except Exception as e:
            stats["fehler"] += " %s" % e
            log.warning("Programm-Index Fehler: %s", e)
        finally:
            self.index, self.stats = idx, stats
            with self._lock:
                self._building = False
            self._ready.set()
            log.info("Programm-Index fertig: %d Programme (StartApps %d, Verknuepfungen %d, Registry %d)",
                     len(idx), stats["startapps"], stats["links"], stats["registry"])

    @staticmethod
    def _bad(name):
        n = name.lower()
        return any(w in n for w in ("uninstall", "deinstall", "readme", "license", "lizenz", "hilfe", "help "))

    def _add(self, idx, stats, bucket, name, target):
        key = _norm(name)
        if not key or self._bad(name) or key in idx:
            return
        idx[key] = (name, target)
        stats[bucket] += 1

    def _scan_startapps(self, idx, stats):
        try:
            out = _run_ps("Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }")
            for line in out.splitlines():
                if "|" in line:
                    name, appid = line.rsplit("|", 1)
                    if name.strip() and appid.strip():
                        self._add(idx, stats, "startapps", name.strip(), "shell:AppsFolder\\" + appid.strip())
        except Exception as e:
            stats["fehler"] += " Get-StartApps: %s" % e
            log.warning("Get-StartApps fehlgeschlagen: %s", e)

    def _scan_links(self, idx, stats):
        home = Path.home()
        roots = [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
                 Path(APPDATA) / r"Microsoft\Windows\Start Menu\Programs",
                 home / "Desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"]
        one = os.environ.get("OneDrive")
        if one:
            roots.append(Path(one) / "Desktop")
        for r in roots:
            try:
                if not r.exists():
                    continue
                for ext in ("*.lnk", "*.url"):
                    for p in r.rglob(ext):
                        self._add(idx, stats, "links", p.stem, str(p))
            except Exception:
                continue

    def _scan_registry(self, idx, stats):
        import winreg
        keys = [(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")]
        for hive, path in keys:
            try:
                with winreg.OpenKey(hive, path) as root:
                    for i in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                                name = winreg.QueryValueEx(k, "DisplayName")[0]
                                icon = winreg.QueryValueEx(k, "DisplayIcon")[0]
                        except OSError:
                            continue
                        exe = str(icon).split(",")[0].strip().strip('"')
                        if exe.lower().endswith(".exe") and os.path.exists(exe) and "unins" not in exe.lower():
                            self._add(idx, stats, "registry", name, exe)
            except OSError:
                continue

    def _wait_index(self, timeout=25):
        if not self._ready.is_set() and not self._building:
            self.warmup()
        self._ready.wait(timeout)

    def search(self, key, n=1):
        scored = sorted(((_score(key, k), -len(k), k) for k in self.index), reverse=True)
        return [(s, self.index[k]) for s, _, k in scored[:n] if s >= 50]

    def report(self, test=""):
        self._wait_index(40)
        L = ["=== PROGRAMM-SUCHE ===",
             "Index: %d Programme  (StartApps %s, Verknuepfungen %s, Registry %s)" % (
                 len(self.index), self.stats.get("startapps", 0), self.stats.get("links", 0),
                 self.stats.get("registry", 0))]
        if os.name != "nt":
            L.append("(nur unter Windows verfuegbar)")
        if self.stats.get("fehler"):
            L.append("Fehler: " + self.stats["fehler"].strip())
        if not self.index:
            L.append("-> Kein Programm gefunden: PowerShell blockiert? Als Notloesung in Settings 'custom_apps' nutzen.")
        names = sorted(v[0] for v in self.index.values())
        L.append("")
        L.append(", ".join(names[:150]) + (" ..." if len(names) > 150 else ""))
        return "\n".join(L)

    # ------------------------------------------------------------------ Starten
    def _start(self, target: str) -> bool:
        """Startet ein bereits geprueftes Ziel. Gibt True bei Erfolg."""
        try:
            if re.match(r"^[a-z][a-z0-9+.-]+:(//)?", target, re.I) and not re.match(r"^[a-zA-Z]:[\\/]", target):
                os.startfile(target) if os.name == "nt" else webbrowser.open(target)  # URI / shell:AppsFolder
                return True
            if " --" in target:                       # z. B. Discord Update.exe --processStart Discord.exe
                exe, args = target.split(" --", 1)
                if os.path.exists(exe):
                    subprocess.Popen([exe, "--" + args.split()[0]] + args.split()[1:], close_fds=True)
                    return True
                return False
            if os.path.isabs(target):
                if os.path.exists(target):
                    os.startfile(target) if os.name == "nt" else subprocess.Popen([target])
                    return True
                return False
            found = shutil.which(target) or _registry_app_path(target)
            if found:
                os.startfile(found) if os.name == "nt" else subprocess.Popen([found])
                return True
        except Exception as e:
            log.warning("Start von %r fehlgeschlagen: %s", target, e)
        return False

    def open(self, name: str):
        """-> (ok, anzeigename, vorschlag)"""
        key = clean_name(name)
        log.info("Programm oeffnen: gehoert %r -> suche %r", name, key)
        custom = {clean_name(k): v for k, v in (self.settings.get("custom_apps") or {}).items()}
        if key in custom and self._start(custom[key]):
            return True, name, ""
        learned = self.memory.db.get_exact("applications", key)
        if learned and self._start(learned):
            self.memory.db.touch("applications", key)
            log.info("  -> gelernter Pfad: %s", learned)
            return True, name, ""
        for cand in KNOWN.get(key, []):
            if self._start(cand):
                log.info("  -> bekanntes Programm: %s", cand)
                return True, name, ""
        for attempt in (1, 2):
            self._wait_index()
            hits = self.search(key, 3)
            for score, (shown, target) in hits[:1]:
                log.info("  -> Index-Treffer %r (%.0f) -> %s", shown, score, target)
                if self._start(target):
                    self.memory.learn_app(key, target)       # beim naechsten Mal sofort
                    return True, shown, ""
            if attempt == 1 and not hits and self.index:
                self.warmup(force=True)                      # evtl. gerade erst installiert -> neu scannen
                self._ready.wait(25)
            else:
                break
        if self._start(key):
            return True, name, ""
        suggestion = ""
        if self.index:
            near = sorted(self.index.values(), key=lambda v: -difflib.SequenceMatcher(None, key, _norm(v[0])).ratio())
            if near and difflib.SequenceMatcher(None, key, _norm(near[0][0])).ratio() >= 0.5:
                suggestion = near[0][0]
        log.warning("Programm %r nicht gefunden (Index: %d Programme)", key, len(self.index))
        return False, key, suggestion
