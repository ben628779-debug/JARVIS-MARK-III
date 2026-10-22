"""Der zentrale Reaktor: Partikelring + Kern (numpy) + HUD-Ringe + Frequenzlinien + Statusanzeige."""
import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from core.state import STATUS_TEXT, S
from gui.hud import build_rings, draw_hud
from gui.particles import ParticleEngine
from gui.styles import accent_rgb

HUD_SPEED = {S.IDLE: 0.6, S.LISTENING: 1.2, S.THINKING: 2.4, S.PROCESSING: 3.0, S.SPEAKING: 1.0, S.ERROR: 0.5}
HUD_INTENSITY = {S.IDLE: 0.55, S.LISTENING: 0.75, S.THINKING: 0.85, S.PROCESSING: 0.95, S.SPEAKING: 0.8, S.ERROR: 0.6}


class ReactorWidget(QWidget):
    clicked = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.state = S.IDLE
        self.level = 0.0
        self.hud_t = 0.0
        self.bars = 0.0                       # Ein-/Ausblenden der Frequenzlinien
        self.info_left, self.info_right = [], []
        self.rings = build_rings(11)
        self.engine = ParticleEngine(settings.get("particle_quality"))
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0.0
        self.setMinimumSize(420, 420)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    # --- Steuerung
    def set_state(self, state):
        self.state = state

    def set_level(self, v):
        self.level = max(0.0, min(1.0, v))

    def rebuild(self):
        self.engine = ParticleEngine(self.settings.get("particle_quality"))

    def showEvent(self, e):
        self._last = self._clock.elapsed() / 1000.0
        self.timer.start(16)
        super().showEvent(e)

    def hideEvent(self, e):                  # im Tray keine CPU verbrauchen
        self.timer.stop()
        super().hideEvent(e)

    def mousePressEvent(self, e):
        self.clicked.emit()

    # --- Zeichnen
    def paintEvent(self, ev):
        now = self._clock.elapsed() / 1000.0
        dt = max(0.0, min(0.1, now - self._last))
        self._last = now
        state = self.state
        rgb = accent_rgb(self.settings.get("accent"))
        # Mikrofonpegel ruhig halten, wenn nichts passiert
        sharp, glow = self.engine.step(dt, state, self.level, rgb)
        lv = self.engine.level_s
        self.hud_t += dt * HUD_SPEED.get(state, 1.0)
        want_bars = 1.0 if state in (S.LISTENING, S.SPEAKING) else 0.0
        self.bars += (want_bars - self.bars) * min(1.0, dt * 6)

        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor(4, 6, 10))

        side = min(w, h * 0.84)
        half = side / 2.0
        cx, cy = w / 2.0, half + h * 0.012

        # sanfte Vignette
        g = QRadialGradient(QPointF(cx, cy), side * 0.75)
        g.setColorAt(0.0, QColor(18, 24, 32, 150))
        g.setColorAt(1.0, QColor(4, 6, 10, 0))
        p.fillRect(self.rect(), QBrush(g))

        target = QRectF(cx - half, cy - half, side, side)
        gh = glow.shape[0]
        S_ = sharp.shape[0]
        gb = glow.tobytes()
        sb = sharp.tobytes()
        gimg = QImage(gb, gh, gh, gh * 4, QImage.Format.Format_RGBA8888_Premultiplied)
        simg = QImage(sb, S_, S_, S_ * 4, QImage.Format.Format_RGBA8888_Premultiplied)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawImage(target, gimg)
        p.drawImage(target, simg)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Kernleuchten
        core = QRadialGradient(QPointF(cx, cy), half * (0.16 + 0.10 * lv))
        core.setColorAt(0.0, QColor(rgb[0], rgb[1], rgb[2], int(70 + 110 * lv)))
        core.setColorAt(1.0, QColor(rgb[0], rgb[1], rgb[2], 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), half * 0.28, half * 0.28)

        # HUD-Ringe (Referenzbild 2): aussen und innen. Drehen nur bei Aktivitaet, ausser in den Einstellungen gewaehlt.
        rotate = bool(self.settings.get("rotate_rings")) or state in (S.THINKING, S.PROCESSING)
        inten = HUD_INTENSITY.get(state, 0.6)
        if state == S.ERROR:
            hud_rgb = (255, 90, 90)
        else:
            hud_rgb = rgb
        draw_hud(p, cx, cy, half, self.hud_t, self.rings, hud_rgb, inten, rotate, rmin=0.68, rmax=1.0)
        draw_hud(p, cx, cy, half, self.hud_t, self.rings, hud_rgb, inten * 0.45, rotate, rmin=0.10, rmax=0.40)

        # Frequenzlinien (LISTENING / SPEAKING)
        if self.bars > 0.02:
            n = 72
            t = self.hud_t
            pen = QPen(QColor(rgb[0], rgb[1], rgb[2], int(210 * self.bars)), max(1.2, half * 0.006))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            r0 = half * 0.285
            for i in range(n):
                a = i / n * 2 * math.pi
                amp = abs(math.sin(i * 0.71 + t * 5.0) * math.sin(i * 0.23 - t * 3.1)) * (0.25 + 0.75 * lv) + 0.04
                ln = half * (0.012 + 0.085 * amp * self.bars)
                ca, sa = math.cos(a), math.sin(a)
                p.drawLine(QPointF(cx + ca * r0, cy + sa * r0), QPointF(cx + ca * (r0 + ln), cy + sa * (r0 + ln)))

        # Texte
        ty = cy + half + h * 0.018
        title_px = max(18, int(side * 0.058))
        f = QFont("Segoe UI", 10)
        f.setPixelSize(title_px)
        f.setWeight(QFont.Weight.Light)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, title_px * 0.35)
        p.setFont(f)
        p.setPen(QColor(235, 244, 252))
        p.drawText(QRectF(0, ty, w, title_px * 1.5), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "J.A.R.V.I.S")

        st_px = max(11, int(side * 0.025))
        f2 = QFont("Segoe UI", 9)
        f2.setPixelSize(st_px)
        f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, st_px * 0.45)
        p.setFont(f2)
        stc = QColor(255, 120, 120) if state == S.ERROR else QColor(rgb[0], rgb[1], rgb[2])
        p.setPen(stc)
        p.drawText(QRectF(0, ty + title_px * 1.45, w, st_px * 1.8), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   STATUS_TEXT.get(state, "READY"))

        # Fortschrittsanimation (THINKING / PROCESSING)
        if state in (S.THINKING, S.PROCESSING):
            bw = side * 0.34
            by = ty + title_px * 1.45 + st_px * 2.2
            x0 = cx - bw / 2
            p.setPen(QPen(QColor(rgb[0], rgb[1], rgb[2], 70), 1.5))
            p.drawLine(QPointF(x0, by), QPointF(x0 + bw, by))
            pos = (self.hud_t * 0.55) % 1.0
            seg = bw * 0.22
            sx = x0 + (bw + seg) * pos - seg
            sx0, sx1 = max(x0, sx), min(x0 + bw, sx + seg)
            if sx1 > sx0:
                p.setPen(QPen(QColor(rgb[0], rgb[1], rgb[2], 230), 2.5))
                p.drawLine(QPointF(sx0, by), QPointF(sx1, by))

        # Echte Statusdaten links/rechts (nur bei genug Platz)
        if w > 980:
            mf = QFont("Consolas", 9)
            mf.setPixelSize(12)
            p.setFont(mf)
            p.setPen(QColor(rgb[0], rgb[1], rgb[2], 170))
            for k, line in enumerate(self.info_left):
                p.drawText(QPointF(w * 0.04, h * 0.30 + k * 20), line)
            for k, line in enumerate(self.info_right):
                p.drawText(QRectF(w * 0.60, h * 0.30 + k * 20 - 13, w * 0.36, 20),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, line)
        p.end()
