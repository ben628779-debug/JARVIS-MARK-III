"""Startbildschirm: Referenzbild 2 als bewegte HUD-Ringe + echte Systempruefung."""
import math
import threading

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from gui.hud import build_rings, draw_hud

MIN_SHOW = 3.6          # Sekunden Mindestdauer (Animation soll sichtbar sein)
MAX_SHOW = 14.0         # nie haengen bleiben
LINE_STEP = 0.38


class StartupScreen(QWidget):
    finished = Signal()

    def __init__(self, orchestrator):
        super().__init__()
        self.orch = orchestrator
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("J.A.R.V.I.S")
        self.resize(1000, 720)
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - self.width() // 2, scr.center().y() - self.height() // 2)
        self.rings = build_rings(5)
        self.dust = [(math.sin(i * 12.9898) * 0.5 + 0.5, math.sin(i * 78.233) * 0.5 + 0.5,
                      0.3 + (i % 5) * 0.12) for i in range(90)]
        self._clock = QElapsedTimer()
        self._clock.start()
        self._pending, self._shown = [], []
        self._last_reveal = 0.0
        self._checks_done = False
        self._ready_at = None
        self._closing = False
        self.orch.startup_line.connect(self._on_line)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def begin(self):
        self.show()
        self._clock.restart()

        def run():
            try:
                self.orch.run_startup_checks()
            except Exception:
                pass
            self._checks_done = True
        threading.Thread(target=run, daemon=True, name="startup-checks").start()

    def _on_line(self, label, status, ok):
        self._pending.append((label, status, ok))

    def _tick(self):
        t = self._clock.elapsed() / 1000.0
        if self._pending and t - self._last_reveal > LINE_STEP:
            self._shown.append(self._pending.pop(0))
            self._last_reveal = t
        if self._ready_at is None and self._checks_done and not self._pending and t >= MIN_SHOW:
            self._ready_at = t
        if self._ready_at is None and t > MAX_SHOW:
            self._pending.clear()
            self._ready_at = t
        if self._ready_at is not None and t - self._ready_at > 1.0 and not self._closing:
            self._closing = True
            self.timer.stop()
            self.hide()
            self.finished.emit()
            return
        self.update()

    def paintEvent(self, ev):
        t = self._clock.elapsed() / 1000.0
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        white = (236, 243, 250)

        # schwebender Staub
        for i, (x, y, s) in enumerate(self.dust):
            px = (x * w + 14 * math.sin(t * 0.3 + i)) % w
            py = (y * h - t * 6 * s) % h
            c = QColor(white[0], white[1], white[2], int(30 + 60 * s))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(px, py), s * 1.6, s * 1.6)

        # Kamerabewegung: Ringe driften, atmen und bauen sich nacheinander auf
        cx = w / 2 + 16 * math.sin(t * 0.55)
        cy = h * 0.40 + 10 * math.cos(t * 0.41)
        R = min(w * 0.46, h * 0.37) * (1.0 + 0.035 * math.sin(t * 0.8) + min(0.12, t * 0.02))
        draw_hud(p, cx, cy, R, t, self.rings, white, 1.0, True,
                 reveal=lambda i: max(0.0, min(1.0, (t - i * 0.11) / 0.7)))

        # Texte
        f = QFont("Segoe UI", 10)
        f.setPixelSize(30)
        f.setWeight(QFont.Weight.Light)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 12)
        p.setFont(f)
        p.setPen(QColor(240, 246, 252))
        p.drawText(QRectF(0, h * 0.745, w, 40), Qt.AlignmentFlag.AlignHCenter, "J.A.R.V.I.S")
        f2 = QFont("Consolas", 9)
        f2.setPixelSize(12)
        f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(f2)
        ready = self._ready_at is not None
        p.setPen(QColor(white[0], white[1], white[2], 190))
        p.drawText(QRectF(0, h * 0.745 + 38, w, 20), Qt.AlignmentFlag.AlignHCenter,
                   "SYSTEM READY" if ready else "INITIALIZING SYSTEM" + "." * (1 + int(t * 2) % 3))
        f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        p.setFont(f2)
        for k, (label, status, ok) in enumerate(self._shown):
            col, row = k // 4, k % 4
            x = w * (0.17 if col == 0 else 0.53)
            y = h * 0.745 + 78 + row * 19
            dots = "." * max(2, 22 - len(label) - len(status))
            p.setPen(QColor(white[0], white[1], white[2], 200) if ok else QColor(255, 150, 90, 230))
            p.drawText(QPointF(x, y), "%s %s %s" % (label, dots, status))

        # Fortschrittslinie
        prog = 1.0 if ready else min(0.96, t / MIN_SHOW * 0.9)
        p.setPen(QPen(QColor(white[0], white[1], white[2], 60), 1))
        p.drawLine(QPointF(w * 0.2, h - 22), QPointF(w * 0.8, h - 22))
        p.setPen(QPen(QColor(white[0], white[1], white[2], 230), 2))
        p.drawLine(QPointF(w * 0.2, h - 22), QPointF(w * (0.2 + 0.6 * prog), h - 22))
        p.end()
