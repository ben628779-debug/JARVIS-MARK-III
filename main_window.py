"""Hauptfenster: HOME / SETTINGS / BRAIN. Schliessen = im Hintergrund weiterlaufen (Tray)."""
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
                               QPlainTextEdit, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from core.state import S
from gui.brain_page import BrainPage
from gui.reactor import ReactorWidget
from gui.settings_page import SettingsPage
from gui.tray import make_icon


class HomePage(QWidget):
    def __init__(self, settings, orch):
        super().__init__()
        self.orch = orch
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.reactor = ReactorWidget(settings)
        self.reactor.clicked.connect(self._reactor_clicked)
        lay.addWidget(self.reactor, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(112)
        self.log.setMaximumBlockCount(300)
        self.log.setStyleSheet("QPlainTextEdit { border: none; border-top: 1px solid rgba(255,255,255,25); "
                               "background: rgba(0,0,0,120); font-family: Consolas, monospace; font-size: 12px; }")
        lay.addWidget(self.log)
        row = QHBoxLayout()
        row.setContentsMargins(14, 8, 14, 10)
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Befehl eintippen oder auf den Reaktor klicken und sprechen ...")
        self.inp.returnPressed.connect(self._send)
        b_send = QPushButton("SEND")
        b_send.clicked.connect(self._send)
        b_mic = QPushButton("MIC")
        b_mic.clicked.connect(self.orch.push_to_talk)
        row.addWidget(self.inp, 1)
        row.addWidget(b_mic)
        row.addWidget(b_send)
        lay.addLayout(row)

    def _reactor_clicked(self):
        if self.reactor.state == S.SPEAKING:
            self.orch.interrupt()
        else:
            self.orch.push_to_talk()

    def _send(self):
        txt = self.inp.text().strip()
        if txt:
            self.inp.clear()
            self.orch.submit_text(txt)

    def add(self, role, text):
        tag = {"user": "YOU       ", "jarvis": "J.A.R.V.I.S", "system": "SYSTEM    "}.get(role, role)
        self.log.appendPlainText("[%s] %s  %s" % (time.strftime("%H:%M:%S"), tag, text))


class MainWindow(QMainWindow):
    def __init__(self, settings, orch):
        super().__init__()
        self.settings, self.orch = settings, orch
        self.quitting = False
        self.tray = None
        self._hint_shown = False
        self.setWindowTitle("J.A.R.V.I.S")
        self.setWindowIcon(make_icon())
        self.resize(1280, 840)
        self.setMinimumSize(900, 660)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(16, 6, 16, 0)
        self.chips = [QLabel() for _ in range(4)]
        for c in self.chips:
            c.setObjectName("hint")
            top.addWidget(c)
            top.addSpacing(12)
        top.addStretch(1)
        group = QButtonGroup(self)
        self.nav = []
        for i, name in enumerate(("HOME", "SETTINGS", "BRAIN")):
            b = QPushButton(name)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=i: self.show_page(k))
            group.addButton(b)
            top.addWidget(b)
            self.nav.append(b)
        self.nav[0].setChecked(True)
        top.addStretch(1)
        self.estop = QPushButton("EMERGENCY STOP")
        self.estop.setObjectName("estop")
        self.estop.setCheckable(True)
        self.estop.toggled.connect(self.orch.emergency_stop)
        top.addWidget(self.estop)
        root.addLayout(top)

        self.stack = QStackedWidget()
        self.home = HomePage(settings, orch)
        self.settings_page = SettingsPage(settings, orch)
        self.brain = BrainPage(settings, orch.memory)
        for pg in (self.home, self.settings_page, self.brain):
            self.stack.addWidget(pg)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        orch.state_changed.connect(self.home.reactor.set_state)
        orch.level.connect(self.home.reactor.set_level)
        orch.message.connect(self.home.add)
        orch.memory_changed.connect(self.brain.refresh)
        orch.error.connect(lambda t: None)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_info)
        self.timer.start(1000)
        self._refresh_info()

    def show_page(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 2:
            self.brain.refresh()

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _refresh_info(self):
        o, s = self.orch, self.settings
        mic = o.listener.mic_ok
        ai = o.brain.available()
        ok, vtxt = o.tts.status()
        dot = lambda good: "\u25cf" if good else "\u25cb"
        self.chips[0].setText("%s SYSTEM %s" % (dot(not o.security.killed), "LOCKED" if o.security.killed else "ONLINE"))
        self.chips[1].setText("%s VOICE %s" % (dot(ok), vtxt.split(" ")[0]))
        self.chips[2].setText("%s AI CORE %s" % (dot(ai), "ONLINE" if ai else "NO KEY"))
        self.chips[3].setText("%s MIC %s" % (dot(mic), "LIVE" if mic else "OFFLINE"))
        r = self.home.reactor
        r.info_left = ["SYSTEM  %s" % ("EMERGENCY STOP" if o.security.killed else "ONLINE"),
                       "MIC     %s" % ("LIVE" if mic else "OFFLINE"),
                       "INPUT   %d%%" % int(r.engine.level_s * 100),
                       "VOLUME  %d%%" % int(s.get("volume"))]
        voice = s.get("edge_voice") if s.get("tts_provider") == "edge" else s.get("tts_provider")
        r.info_right = ["AI CORE  %s" % (s.get("gemini_model") if ai else "NO KEY"),
                        "VOICE    %s" % voice,
                        "MEMORY   %d FACTS" % len(o.memory.db.all_facts()),
                        time.strftime("%H:%M:%S")]

    def closeEvent(self, e):
        if self.quitting or not QSystemTrayIcon.isSystemTrayAvailable():
            e.accept()
            return
        e.ignore()
        self.hide()
        if self.tray and not self._hint_shown:
            self._hint_shown = True
            self.tray.showMessage("J.A.R.V.I.S", "Ich laufe im Hintergrund weiter. Klick auf den Kreis oeffnet mich wieder.",
                                  QSystemTrayIcon.MessageIcon.Information, 4000)
