"""Aktivierung: Wake-Word im erkannten Text + Doppel-Klatschen."""
import time

from ai.intent_parser import strip_wake_word


class WakeWord:
    """Text-basiert: 'Hey J.A.R.V.I.S, ...' -> (True, 'rest des Befehls')."""

    @staticmethod
    def check(text: str):
        return strip_wake_word(text)


class ClapDetector:
    """Erkennt zweimaliges Klatschen (scharfer Pegelsprung aus relativer Ruhe)."""

    def __init__(self, min_peak=0.30, ratio=7.0, min_gap=0.18, max_gap=1.1):
        self.min_peak, self.ratio = min_peak, ratio
        self.min_gap, self.max_gap = min_gap, max_gap
        self._hist = []
        self._claps = []
        self._last = 0.0

    def feed(self, peak: float, rms: float, now=None) -> bool:
        now = now if now is not None else time.monotonic()
        base = (sum(self._hist) / len(self._hist)) if self._hist else 0.0
        self._hist.append(rms)
        if len(self._hist) > 12:
            self._hist.pop(0)
        if peak >= self.min_peak and peak > (base + 0.01) * self.ratio and now - self._last > 0.12:
            self._last = now
            self._claps = [t for t in self._claps if now - t <= self.max_gap]
            if self._claps and now - self._claps[-1] >= self.min_gap:
                self._claps = []
                return True
            self._claps.append(now)
        return False

    def reset(self):
        self._claps.clear()
        self._hist.clear()
