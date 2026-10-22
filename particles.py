"""Partikel-Reaktor (reines numpy, ohne Qt) - rendert den Partikelring wie im Referenzbild.

Aufbau: gewellter Ring aus mehreren Faeden + Funkel-Halo, Kern-Kugel aus Punkten, schwebender
Staub, nach innen fliessende Datenpartikel (THINKING). Ausgabe: scharfe Ebene + Glow-Ebene (RGBA).
"""
import math

import numpy as np

STATE_PARAMS = {
    #            speed  bright  wave   level_gain  flow  ring_open
    "IDLE":       (0.55, 0.85, 0.075, 0.04, 0.0, 0.0),
    "LISTENING":  (1.35, 1.05, 0.085, 0.18, 0.0, 0.0),
    "THINKING":   (2.30, 1.00, 0.095, 0.05, 1.0, 0.0),
    "PROCESSING": (1.90, 1.05, 0.090, 0.06, 0.55, 0.0),
    "SPEAKING":   (1.25, 1.05, 0.080, 0.22, 0.0, 0.0),
    "ERROR":      (0.80, 0.90, 0.070, 0.04, 0.0, 0.0),
}
QUALITY = {"low": (384, 600, 1800, 400), "medium": (448, 950, 2800, 500), "high": (512, 1500, 4200, 700)}


class ParticleEngine:
    R0 = 0.50          # Ringradius in Einheiten des halben Bildes
    CORE = 0.085

    def __init__(self, quality="high", seed=3):
        size, per_strand, halo_n, dust_n = QUALITY.get(quality, QUALITY["high"])
        self.size = size
        rng = np.random.default_rng(seed)
        self.rng = rng
        self.t = 0.0
        # --- Ringfaeden
        self.S = 9
        P = per_strand
        base = np.linspace(0, 2 * math.pi, P, endpoint=False, dtype=np.float32)
        self.th = np.tile(base, (self.S, 1)) + rng.normal(0, 0.0015, (self.S, P)).astype(np.float32)
        self.strand_idx = np.repeat(np.arange(self.S, dtype=np.float32)[:, None], P, axis=1)
        self.strand_bright = rng.uniform(0.35, 1.0, (self.S, P)).astype(np.float32)
        self.ks = np.array([2, 3, 5, 7, 11, 17], dtype=np.float32)
        self.amps = np.array([1.0, 0.75, 0.5, 0.34, 0.2, 0.1], dtype=np.float32)
        self.om = np.array([0.35, -0.5, 0.7, -0.9, 1.3, -1.7], dtype=np.float32)
        self.ph = rng.uniform(0, 2 * math.pi, 6).astype(np.float32)
        # --- Halo
        self.hth = rng.uniform(0, 2 * math.pi, halo_n).astype(np.float32)
        self.hoff = (rng.normal(0, 0.035, halo_n) * (1 + rng.exponential(0.6, halo_n))).astype(np.float32)
        self.hph = rng.uniform(0, 2 * math.pi, halo_n).astype(np.float32)
        self.hsp = rng.uniform(0.6, 2.4, halo_n).astype(np.float32)
        # --- Kern (70 % Oberflaeche, 30 % Volumen)
        n = 1300
        i = np.arange(n, dtype=np.float32) + 0.5
        phi = np.arccos(1 - 2 * i / n)
        gold = math.pi * (1 + 5 ** 0.5)
        th = gold * i
        rad = np.where(rng.random(n) < 0.7, 1.0, rng.random(n) ** (1 / 3)).astype(np.float32)
        self.cx = (np.cos(th) * np.sin(phi) * rad).astype(np.float32)
        self.cy = (np.sin(th) * np.sin(phi) * rad).astype(np.float32)
        self.cz = (np.cos(phi) * rad).astype(np.float32)
        self.cph = rng.uniform(0, 2 * math.pi, n).astype(np.float32)
        # --- Staub
        self.dx = rng.uniform(-1, 1, dust_n).astype(np.float32)
        self.dy = rng.uniform(-1, 1, dust_n).astype(np.float32)
        self.dvx = rng.normal(0, 0.012, dust_n).astype(np.float32)
        self.dvy = rng.normal(0, 0.012, dust_n).astype(np.float32)
        self.dw = rng.uniform(0.1, 0.5, dust_n).astype(np.float32)
        # --- Datenfluss
        fn = 520
        self.fa = rng.uniform(0, 2 * math.pi, fn).astype(np.float32)
        self.fu = rng.random(fn).astype(np.float32)
        self.fs = rng.uniform(0.25, 0.7, fn).astype(np.float32)
        # --- geglaettete Parameter
        self.p = np.array(STATE_PARAMS["IDLE"], dtype=np.float32)
        self.level_s = 0.0
        self.err = 0.0
        self.flow_amt = 0.0
        self._tone_gain = 1.0
        self.last_level_shape = np.zeros(72, dtype=np.float32)

    # ------------------------------------------------------------------ Hilfen
    def _wave(self, theta, t, shift=0.0):
        f = np.zeros_like(theta)
        for k, a, o, p in zip(self.ks, self.amps, self.om, self.ph):
            f += a * np.sin(k * theta + p + o * t + shift)
        return f / 2.2

    def _splat(self, acc, x, y, w):
        """Bilineares Einstreuen -> weiche, flimmerfreie Punkte."""
        S = self.size
        x0 = np.floor(x).astype(np.int32)
        y0 = np.floor(y).astype(np.int32)
        fx, fy = x - x0, y - y0
        xs = np.concatenate((x0, x0 + 1, x0, x0 + 1))
        ys = np.concatenate((y0, y0, y0 + 1, y0 + 1))
        ws = np.concatenate((w * (1 - fx) * (1 - fy), w * fx * (1 - fy), w * (1 - fx) * fy, w * fx * fy))
        ok = (xs >= 0) & (xs < S) & (ys >= 0) & (ys < S)
        acc += np.bincount(ys[ok] * S + xs[ok], weights=ws[ok], minlength=S * S).reshape(S, S).astype(np.float32)

    # ------------------------------------------------------------------ Frame
    def step(self, dt, state, level, accent_rgb):
        dt = max(0.0, min(dt, 0.1))
        target = np.array(STATE_PARAMS.get(state, STATE_PARAMS["IDLE"]), dtype=np.float32)
        self.p += (target - self.p) * min(1.0, dt * 3.5)
        speed, bright, wave, gain, flow, _ = [float(v) for v in self.p]
        self.t += dt * speed
        t = self.t
        self.level_s += (level - self.level_s) * min(1.0, dt * (14 if level > self.level_s else 6))
        lv = self.level_s
        self.err += ((1.0 if state == "ERROR" else 0.0) - self.err) * min(1.0, dt * 5)
        self.flow_amt = flow

        S = self.size
        half = S / 2.0
        acc = np.zeros((S, S), dtype=np.float32)

        # --- Ring
        amp = wave + lv * gain
        R = self.R0 * (1.0 + amp * self._wave(self.th, t, self.strand_idx * 0.33))
        spread = 0.5 + 0.5 * np.sin(2 * self.th + t * 0.45 + 1.3) * np.cos(3 * self.th - t * 0.3)
        R += (self.strand_idx - (self.S - 1) / 2.0) * (0.004 + 0.030 * spread * spread)
        R += lv * 0.02 * np.sin(23 * self.th - t * 9.0)
        xr = half + half * R * np.cos(self.th)
        yr = half + half * R * np.sin(self.th)
        twinkle = 0.75 + 0.25 * np.sin(self.th * 41 + t * 3.0 + self.strand_idx)
        self._splat(acc, xr.ravel(), yr.ravel(), (1.15 * bright * self.strand_bright * twinkle).ravel())

        # --- Halo
        Rh = self.R0 * (1.0 + amp * self._wave(self.hth, t, 0.8)) + self.hoff * (1.0 + 0.35 * np.sin(t * self.hsp + self.hph))
        xh = half + half * Rh * np.cos(self.hth)
        yh = half + half * Rh * np.sin(self.hth)
        wh = 0.75 * bright * (0.3 + 0.7 * np.maximum(0, np.sin(t * self.hsp * 1.7 + self.hph)) ** 2)
        self._splat(acc, xh, yh, wh)

        # --- Kern
        core_r = self.CORE * (1.0 + 0.04 * math.sin(t * 1.2)) * (1.0 + 0.6 * lv)
        jit = 0.012 * np.sin(t * 2.0 + self.cph)
        px = (self.cx + jit) * core_r
        py = (self.cy + 0.012 * np.cos(t * 1.7 + self.cph)) * core_r
        depth = 0.45 + 0.55 * (self.cz + 1) / 2
        limb = 0.6 + 0.4 * np.sqrt(np.maximum(0.0, 1 - self.cz ** 2))
        wc = 1.1 * bright * depth * limb * (0.75 + 0.25 * np.sin(t * 3.1 + self.cph * 2))
        self._splat(acc, half + half * px, half + half * py, wc)

        # --- Staub
        self.dx += self.dvx * dt * (1 + speed)
        self.dy += self.dvy * dt * (1 + speed)
        self.dx = np.where(np.abs(self.dx) > 1.0, -np.sign(self.dx) * 0.99, self.dx)
        self.dy = np.where(np.abs(self.dy) > 1.0, -np.sign(self.dy) * 0.99, self.dy)
        self._splat(acc, half + half * self.dx, half + half * self.dy,
                    self.dw * 0.9 * (0.6 + 0.4 * np.sin(t * 1.3 + self.dx * 9)))

        # --- Datenfluss nach innen
        if flow > 0.02:
            self.fu = (self.fu + dt * self.fs * (0.6 + speed * 0.5)) % 1.0
            u = self.fu
            rr = 0.95 * (1 - u) + 0.11 * u
            ang = self.fa + 2.6 * u
            wf = flow * 1.1 * np.sin(u * math.pi) * bright
            self._splat(acc, half + half * rr * np.cos(ang), half + half * rr * np.sin(ang), wf.astype(np.float32))

        # --- Tonemapping + Farbe
        img = 1.0 - np.exp(-acc * 1.15)
        gs = img.reshape(S // 4, 4, S // 4, 4).mean(axis=(1, 3))
        gs = np.minimum(1.0, gs * 4.5)
        ar, ag, ab = accent_rgb
        er, eg, eb = 255, 70, 70
        k = 0.30
        base = np.array([255 * (1 - k) + ar * k, 255 * (1 - k) + ag * k, 255 * (1 - k) + ab * k], dtype=np.float32)
        base = base * (1 - 0.55 * self.err) + np.array([er, eg, eb], dtype=np.float32) * 0.55 * self.err
        gl = np.array([ar, ag, ab], dtype=np.float32) * (1 - 0.6 * self.err) + np.array([er, eg, eb], dtype=np.float32) * 0.6 * self.err

        sharp = np.empty((S, S, 4), dtype=np.uint8)
        for c in range(3):
            sharp[..., c] = (img * (base[c] / 255.0) * 255.0).astype(np.uint8)
        sharp[..., 3] = (img * 255.0).astype(np.uint8)
        g = gs.shape[0]
        glow = np.empty((g, g, 4), dtype=np.uint8)
        for c in range(3):
            glow[..., c] = (gs * gl[c] * 0.55).astype(np.uint8)
        glow[..., 3] = (gs * 140.0).astype(np.uint8)
        return np.ascontiguousarray(sharp), np.ascontiguousarray(glow)
