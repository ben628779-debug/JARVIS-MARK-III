"""Einstellungen - datengetriebenes Formular (Keys landen im Windows-Anmeldeinformationsspeicher)."""
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

from core import deps, diagnostics
from core.security import PERMISSIONS
from tts.audio_player import list_devices

SENTINEL = "\u2022" * 12      # zeigt "Key ist gespeichert", ohne ihn preiszugeben

PROVIDERS = [("edge", "Edge TTS (kostenlos) - de-DE-KillianNeural"), ("elevenlabs", "ElevenLabs"), ("fish", "Fish Audio")]
ACCENTS = [("ice", "Eis-Weiss (wie Referenzbild)"), ("blue", "Blau"), ("cyan", "Cyan"), ("green", "Gruen"),
           ("orange", "Orange"), ("red", "Rot")]
QUALITY = [("low", "Niedrig"), ("medium", "Mittel"), ("high", "Hoch")]
MAILP = [("outlook", "Outlook / Hotmail / Microsoft (OAuth)"), ("gmail", "Gmail (App-Passwort)"),
         ("imap", "Anderes IMAP-Postfach")]

FIELDS = [
    ("section", "KI"),
    ("secret", "gemini_api_key", "Gemini API Key"),
    ("text", "gemini_model", "Gemini Modell"),
    ("section", "STIMME"),
    ("combo", "tts_provider", "Sprachausgabe", PROVIDERS),
    ("text", "edge_voice", "Edge-Stimme"),
    ("text", "edge_rate", "Edge-Tempo (z. B. +10%)"),
    ("secret", "elevenlabs_api_key", "ElevenLabs API Key"),
    ("text", "elevenlabs_voice_id", "ElevenLabs Voice-ID"),
    ("text", "elevenlabs_model", "ElevenLabs Modell"),
    ("secret", "fish_api_key", "Fish Audio API Key"),
    ("text", "fish_voice_id", "Fish Audio Voice-ID"),
    ("slider", "volume", "Lautstaerke", 0, 100),
    ("section", "AUDIO & AKTIVIERUNG"),
    ("device_in", "input_device", "Mikrofon"),
    ("device_out", "output_device", "Lautsprecher"),
    ("slider1000", "mic_threshold", "Mikrofon-Schwelle (niedrig = empfindlicher)", 2, 100),
    ("check", "wake_word_enabled", "Wake-Word \"Hey J.A.R.V.I.S\" (sendet kurze Sprachschnipsel an Google-Spracherkennung)"),
    ("check", "clap_enabled", "Zweimal Klatschen aktiviert J.A.R.V.I.S"),
    ("check", "follow_up_enabled", "Folgefragen ohne erneutes Wake-Word"),
    ("section", "DESIGN"),
    ("combo", "accent", "HUD-Farbe", ACCENTS),
    ("combo", "particle_quality", "Animationsqualitaet", QUALITY),
    ("check", "rotate_rings", "HUD-Ringe immer drehen (sonst nur beim Denken/Verarbeiten)"),
    ("section", "E-MAIL"),
    ("combo", "mail_provider", "Postfach", MAILP),
    ("text", "mail_address", "E-Mail-Adresse"),
    ("text", "azure_client_id", "Azure Client-ID (nur Outlook, siehe README)"),
    ("secret", "mail_password", "App-Passwort (nur Gmail/IMAP)"),
    ("text", "imap_host", "IMAP-Server (optional)"),
    ("text", "smtp_host", "SMTP-Server (optional)"),
    ("buttons_mail",),
    ("section", "TELEFON & SMS (Twilio)"),
    ("secret", "twilio_sid", "Twilio Account SID"),
    ("secret", "twilio_token", "Twilio Auth Token"),
    ("text", "twilio_from", "Twilio-Nummer (+49...)"),
    ("text", "my_phone", "Meine Handynummer (+49...)"),
    ("text", "allowed_numbers", "Weitere freigegebene Nummern (Komma)"),
    ("spin", "call_limit_per_day", "Max. Anrufe pro Tag", 1, 50),
    ("section", "BERECHTIGUNGEN"),
    ("perms",),
    ("section", "SYSTEM"),
    ("check", "autostart", "Mit Windows starten"),
    ("check", "start_minimized", "Beim Start nur im Hintergrund (Tray)"),
    ("check", "learning_enabled", "Aus Gespraechen lernen"),
    ("check", "debug", "Debug-Modus (ausfuehrlichere Logs)"),
]


class SettingsPage(QWidget):
    saved = Signal()
    info = Signal(str)
    diag_text = Signal(str)
    deps_done = Signal(str)

    def __init__(self, settings, orch):
        super().__init__()
        self.settings, self.orch = settings, orch
        self._w = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        row = QHBoxLayout(host)
        row.addStretch(1)
        col = QWidget()
        col.setMaximumWidth(820)
        col.setMinimumWidth(520)
        self.form = QFormLayout(col)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form.setVerticalSpacing(9)
        self.form.setContentsMargins(20, 10, 20, 30)
        row.addWidget(col, 10)
        row.addStretch(1)
        scroll.setWidget(host)
        self.banner = QWidget()
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(20, 8, 20, 8)
        self.banner_text = QLabel("")
        self.banner_text.setWordWrap(True)
        self.banner_text.setStyleSheet("color: #ffb070;")
        self.banner_btn = QPushButton("INSTALL MISSING PACKAGES")
        self.banner_btn.clicked.connect(self._install_missing)
        bl.addWidget(self.banner_text, 1)
        bl.addWidget(self.banner_btn)
        outer.addWidget(self.banner)
        self.deps_done.connect(self._deps_finished)
        self._check_deps()
        outer.addWidget(scroll, 1)

        for spec in FIELDS:
            self._add(spec)

        self.diag = QPlainTextEdit()
        self.diag.setReadOnly(True)
        self.diag.setMaximumHeight(230)
        self.diag.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; font-size: 11px; }")
        self.diag.setVisible(False)
        outer.addWidget(self.diag)
        self.diag_text.connect(self._show_diag)

        bar = QHBoxLayout()
        bar.setContentsMargins(20, 8, 20, 12)
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        b_save = QPushButton("SAVE")
        b_save.clicked.connect(self.save)
        b_test = QPushButton("VOICE TEST")
        b_test.clicked.connect(self._voice_test)
        b_ref = QPushButton("REFRESH DEVICES")
        b_ref.clicked.connect(self.refresh_devices)
        b_diag = QPushButton("AUDIO DIAGNOSE")
        b_diag.clicked.connect(self._diagnose)
        bar.addWidget(self.msg, 1)
        b_apps = QPushButton("PROGRAMME PRUEFEN")
        b_apps.clicked.connect(self._check_apps)
        bar.addWidget(b_apps)
        bar.addWidget(b_diag)
        bar.addWidget(b_ref)
        bar.addWidget(b_test)
        bar.addWidget(b_save)
        outer.addLayout(bar)
        self.info.connect(self.msg.setText)
        self.load()

    # ------------------------------------------------------------------ Aufbau
    def _add(self, spec):
        kind = spec[0]
        if kind == "section":
            lab = QLabel(spec[1])
            lab.setObjectName("section")
            self.form.addRow(lab)
            return
        if kind == "perms":
            for name, (desc, _d) in PERMISSIONS.items():
                cb = QCheckBox(desc)
                self._w["perm_" + name] = ("check", cb)
                self.form.addRow(QLabel(name), cb)
            return
        if kind == "buttons_mail":
            h = QHBoxLayout()
            b1 = QPushButton("MIT OUTLOOK VERBINDEN")
            b1.clicked.connect(self._connect_outlook)
            b2 = QPushButton("POSTFACH TESTEN")
            b2.clicked.connect(self._test_mail)
            h.addWidget(b1)
            h.addWidget(b2)
            h.addStretch(1)
            self.form.addRow("", h)
            return
        key, label = spec[1], spec[2]
        if kind == "text":
            w = QLineEdit()
        elif kind == "secret":
            w = QLineEdit()
            w.setEchoMode(QLineEdit.EchoMode.Password)
        elif kind == "combo":
            w = QComboBox()
            for val, txt in spec[3]:
                w.addItem(txt, val)
        elif kind == "check":
            w = QCheckBox()
        elif kind in ("slider", "slider1000"):
            w = QSlider(Qt.Orientation.Horizontal)
            w.setRange(spec[3], spec[4])
        elif kind == "spin":
            w = QSpinBox()
            w.setRange(spec[3], spec[4])
        else:                                       # device_in / device_out
            w = QComboBox()
        self._w[key] = (kind, w)
        lab = QLabel(label)
        lab.setWordWrap(True)
        self.form.addRow(lab, w)

    # ------------------------------------------------------------------ Laden / Speichern
    def load(self):
        s = self.settings
        for key, (kind, w) in self._w.items():
            if kind == "text":
                w.setText(str(s.get(key, "") or ""))
            elif kind == "secret":
                w.setText(SENTINEL if s.secret(key) else "")
            elif kind == "combo":
                i = w.findData(s.get(key))
                w.setCurrentIndex(max(0, i))
            elif kind == "check":
                if key.startswith("perm_"):
                    name = key[5:]
                    w.setChecked(bool(s.get(key, PERMISSIONS[name][1])))
                else:
                    w.setChecked(bool(s.get(key)))
            elif kind == "slider":
                w.setValue(int(s.get(key)))
            elif kind == "slider1000":
                w.setValue(int(round(float(s.get(key)) * 1000)))
            elif kind == "spin":
                w.setValue(int(s.get(key)))
            elif kind in ("device_in", "device_out"):
                self._fill_devices(key, kind, s.get(key) or "")

    def _check_deps(self):
        miss = deps.missing()
        self.banner.setVisible(bool(miss))
        if miss:
            self.banner_text.setText("Fehlende Pakete: %s. Ohne sie funktionieren Mikrofon, Lautsprecher oder Stimme nicht." % ", ".join(miss))
            self.banner_btn.setEnabled(deps.can_install())
            if not deps.can_install():
                self.banner_text.setText(self.banner_text.text() + " (EXE-Version: bitte neu bauen.)")

    def _install_missing(self):
        miss = deps.missing()
        self.banner_btn.setEnabled(False)
        self.banner_text.setText("Installiere: %s ... (das kann 1-3 Minuten dauern)" % ", ".join(miss))

        def run():
            ok, failed = deps.install(miss)
            if failed:
                self.deps_done.emit("Nicht installiert: %s. Im Terminal (.venv aktiv) 'python install_deps.py' ausfuehren; "
                                    "empfohlen: Python 3.11 oder 3.12." % ", ".join(failed))
            else:
                self.deps_done.emit("Alles installiert. BITTE J.A.R.V.I.S JETZT NEU STARTEN (Tray -> Beenden, dann python main.py).")
        threading.Thread(target=run, daemon=True).start()

    def _deps_finished(self, text):
        self.banner.setVisible(True)
        self.banner_text.setText(text)
        self.banner_btn.setEnabled(bool(deps.missing()) and deps.can_install())

    def _fill_devices(self, key, kind, wanted):
        """Fuellt die Geraeteliste. Der gespeicherte Name bleibt IMMER erhalten (auch wenn das Geraet gerade fehlt)."""
        w = self._w[key][1]
        w.blockSignals(True)
        w.clear()
        w.addItem("System-Standard", "")
        names = list_devices("input" if kind == "device_in" else "output")
        for name in names:
            w.addItem(name, name)
        if wanted and wanted not in names:
            w.addItem("%s (gerade nicht gefunden)" % wanted, wanted)
        w.setCurrentIndex(max(0, w.findData(wanted)))
        w.blockSignals(False)

    def refresh_devices(self):
        for key, (kind, w) in self._w.items():
            if kind in ("device_in", "device_out"):
                self._fill_devices(key, kind, w.currentData() or "")
        self.info.emit("Geraeteliste aktualisiert.")

    def _diagnose(self):
        self.save()
        self.diag.setVisible(True)
        self.diag.setPlainText("Pruefe Mikrofon und Lautsprecher ... (du hoerst gleich einen kurzen Ton)")
        diagnostics.run_async(self.settings, self.orch.listener, self.diag_text.emit)

    def _check_apps(self):
        self.diag.setVisible(True)
        self.diag.setPlainText("Scanne installierte Programme ... (bis zu 30 Sekunden)")
        launcher = self.orch.router.launcher
        threading.Thread(target=lambda: self.diag_text.emit(launcher.report()), daemon=True).start()

    def _show_diag(self, text):
        self.diag.setPlainText(text)

    def save(self):
        s = self.settings
        failed = []
        for key, (kind, w) in self._w.items():
            if kind == "text":
                s.set(key, w.text().strip())
            elif kind == "secret":
                txt = w.text()
                if txt != SENTINEL:
                    if not s.secrets.set(key, txt):
                        failed.append(key)
                    elif txt:
                        w.setText(SENTINEL)
            elif kind == "combo":
                s.set(key, w.currentData())
            elif kind == "check":
                s.set(key, w.isChecked())
            elif kind == "slider":
                s.set(key, w.value())
            elif kind == "slider1000":
                s.set(key, w.value() / 1000.0)
            elif kind == "spin":
                s.set(key, w.value())
            elif kind in ("device_in", "device_out"):
                s.set(key, w.currentData() or "")
        ok = s.save()
        if ok and not failed:
            self.info.emit("Gespeichert in %s" % s.path)
        else:
            self.info.emit("FEHLER beim Speichern (%s) - siehe Log." % (", ".join(failed) or str(s.path)))
        self.saved.emit()

    # ------------------------------------------------------------------ Aktionen
    def _voice_test(self):
        self.save()
        self.orch.test_voice()
        self.info.emit("Sprachtest gestartet ...")

    def _connect_outlook(self):
        self.save()
        self.info.emit("Browser oeffnet sich zur Microsoft-Anmeldung ...")

        def run():
            try:
                self.orch.mail.connect_outlook()
                self.info.emit("Outlook ist verbunden.")
            except Exception as e:
                self.info.emit("Outlook: %s" % str(e)[:160])
        threading.Thread(target=run, daemon=True).start()

    def _test_mail(self):
        self.save()
        self.info.emit("Teste Postfach ...")

        def run():
            try:
                if not self.orch.mail.configured():
                    self.info.emit("Postfach ist noch nicht eingerichtet.")
                    return
                n = len(self.orch.mail.unread(20))
                self.info.emit("Postfach OK - %d ungelesene Mails." % n)
            except Exception as e:
                self.info.emit("Postfach-Fehler: %s" % str(e)[:160])
        threading.Thread(target=run, daemon=True).start()
