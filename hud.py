"""HUD-Ringe im Stil von Referenzbild 2 (Segmentringe, Punktringe, Skalen) - echte, animierte Vektorgrafik."""
import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen

RADII = [0.115, 0.150, 0.190, 0.235, 0.285, 0.335, 0.385, 0.440, 0.500, 0.565,
         0.630, 0.700, 0.775, 0.850, 0.920, 0.990]


@dataclass
class Ring:
    r: float
    kind: str                 # arcs | thick | dots | ticks | solid
    segs: list                # [(start_deg, span_deg)]
    w: float                  # Strichstaerke in Pixeln bei Radius 450
    speed: float              # Grad pro Sekunde
    alpha: float
    gap: float = 8.0          # Punkt-/Tick-Abstand in Pixeln bei Radius 450
    phase: float = 0.0
    extra: dict = field(default_factory=dict)


def build_rings(seed=11):
    rnd = random.Random(seed)
    rings = []
    for i, r in enumerate(RADII):
        kind = "ticks" if i == 0 else rnd.choices(["arcs", "dots", "ticks", "solid", "thick"], weights=[4, 3, 2, 1.4, 2])[0]
        speed = rnd.choice([-1, 1]) * rnd.uniform(5, 38) * (1.5 if r < 0.3 else 1.0)
        start = rnd.uniform(0, 360)
        if kind == "arcs":
            n = rnd.randint(1, 3)
            segs, a = [], start
            for _ in range(n):
                span = rnd.uniform(28, 150)
                segs.append((a, span))
                a += span + rnd.uniform(25, 110)
            ring = Ring(r, kind, segs, rnd.uniform(1.0, 2.3), speed, rnd.uniform(0.65, 1.0))
        elif kind == "thick":
            n = rnd.randint(1, 2)
            segs = [(start + k * rnd.uniform(110, 200), rnd.uniform(18, 85)) for k in range(n)]
            ring = Ring(r, kind, segs, rnd.uniform(3.0, 5.5), speed, rnd.uniform(0.8, 1.0))
        elif kind == "dots":
            ring = Ring(r, kind, [(start, rnd.uniform(110, 360))], rnd.uniform(1.7, 2.7), speed,
                        rnd.uniform(0.6, 0.95), gap=rnd.uniform(7, 13))
        elif kind == "ticks":
            ring = Ring(r, kind, [(start, 360 if i == 0 else rnd.uniform(90, 360))], rnd.uniform(5, 10), speed,
                        rnd.uniform(0.55, 0.9), gap=rnd.uniform(4.5, 7.5))
        else:
            ring = Ring(r, "solid", [(0, 360)], 1.0, speed * 0.3, rnd.uniform(0.3, 0.5))
        ring.phase = rnd.uniform(0, 360)
        rings.append(ring)
    return rings


def draw_hud(p, cx, cy, R, t, rings, rgb, intensity=1.0, rotate=True, rmin=0.0, rmax=1.1, reveal=None):
    """Zeichnet die Ringe. R = Pixelradius fuer r=1.0. reveal(i)->0..1 optionaler Einblend-Faktor."""
    scale = max(0.55, R / 450.0)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for idx, ring in enumerate(rings):
        if ring.r < rmin or ring.r > rmax:
            continue
        rev = 1.0 if reveal is None else reveal(idx)
        if rev <= 0.0:
            continue
        rad = ring.r * R * (0.92 + 0.08 * rev)
        rect = QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad)
        off = ring.phase + (ring.speed * t if rotate else 0.0)
        pulse = 0.70 + 0.30 * math.sin(t * 1.5 + idx * 0.9)
        a = max(0.0, min(1.0, ring.alpha * pulse * intensity * rev))
        if a < 0.02:
            continue
        col = QColor(rgb[0], rgb[1], rgb[2])
        col.setAlphaF(a)
        if ring.kind in ("arcs", "thick", "solid"):
            pen = QPen(col, max(1.0, ring.w * scale))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        elif ring.kind == "dots":
            width = max(1.6, ring.w * scale)
            pen = QPen(col, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setDashPattern([0.01, max(1.5, ring.gap * scale / width)])
        else:  # ticks: dicker, sehr kurz gestrichelter Kreis = radiale Skalenstriche
            width = max(3.0, ring.w * scale)
            pen = QPen(col, width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen.setDashPattern([max(0.08, 1.3 * scale / width), max(1.0, ring.gap * scale / width * 1.8)])
        p.setPen(pen)
        for start, span in ring.segs:
            p.drawArc(rect, int((start + off) * 16), int(span * 16))
