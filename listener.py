"""Hoer-Schleife: Mikrofonpegel, Klatschen, Wake-Word, Befehlsaufnahme (VAD) und STT."""
import threading
import time

import numpy as np

from ai.intent_parser import strip_wake_word
from core import logger
from voice.microphone import BLOCK, RATE, MicError, MicStream
from voice.speech_recognition import STTError
from voice.wake_word import ClapDetector

log = logger.get("listener")

BLOCK_S = BLOCK / RATE


class Listener(threading.Thread):
    def __init__(self, settings, stt, is_busy, on_level, on_text, on_active, on_error):
        super().__init__(daemon=True, name="listener")
        self.settings, self.stt, self.is_busy = settings, stt, is_busy
        self.on_level, self.on_text, self.on_active, self.on_error = on_level, on_text, on_active, on_error
        self._stop_evt = threading.Event()
        self._active_until = 0.0          # >now: Befehlsmodus (kein Wake-Word noetig)
        self._reopen = threading.Event()
        self.clap = ClapDetector()
        self._mic_error_shown = False
        self.mic_ok = False
        self.mic_name = ""

    # ---- Steuerung von aussen
    def request_listen(self, seconds=8.0):
        """Sofort auf einen Befehl hoeren (Klatschen, Klick, Rueckfrage, Folgefrage)."""
        self._active_until = time.monotonic() + seconds
        self.on_active(True)

    def cancel_listen(self):
        self._active_until = 0.0
        self.on_active(False)

    def reopen_mic(self):
        self._reopen.set()

    def stop(self):
        self._stop_evt.set()

    @property
    def listening_for_command(self):
        return time.monotonic() < self._active_until

    # ---- Hauptschleife
    def run(self):
        while not self._stop_evt.is_set():
            mic = MicStream(self.settings.get("input_device"))
            try:
                mic.open()
                self.mic_ok = True
                self.mic_name = mic.opened_name
                self._mic_error_shown = False
                log.info("Mikrofon geoeffnet: %s", mic.opened_name)
            except MicError as e:
                self.mic_ok = False
                if not self._mic_error_shown:
                    self._mic_error_shown = True
                    self.on_error(str(e))
                self._stop_evt.wait(5.0)
                continue
            try:
                self._loop(mic)
            except Exception:
                log.exception("Hoer-Schleife")
                self._stop_evt.wait(2.0)
            finally:
                mic.close()
                self.mic_ok = False

    def _loop(self, mic):
        self._reopen.clear()
        pre = []                          # Vorlauf (300 ms)
        rec, speech_blocks, silence, last_emit = [], 0, 0, 0.0
        recording = False
        was_active = False
        self.clap.reset()
        while not self._stop_evt.is_set() and not self._reopen.is_set():
            try:
                blk = mic.read(timeout=0.5)
            except Exception:
                if not mic._stream or not getattr(mic._stream, "active", True):
                    raise
                continue
            f = blk.astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(f * f)))
            peak = float(np.max(np.abs(f)))
            now = time.monotonic()
            if now - last_emit > 0.03:
                self.on_level(min(1.0, rms * 8.0))
                last_emit = now

            active = self.listening_for_command
            if was_active and not active and not recording:
                self.on_active(False)
            was_active = active

            if self.is_busy():                       # JARVIS spricht/arbeitet -> Echo ignorieren
                recording, rec, speech_blocks, silence, pre = False, [], 0, 0, []
                self.clap.reset()
                mic.drain()
                continue

            if not active and self.settings.get("clap_enabled") and self.clap.feed(peak, rms, now):
                log.info("Doppel-Klatschen erkannt")
                self.request_listen(8.0)
                self.on_text("", "clap")
                recording, rec, speech_blocks, silence, pre = False, [], 0, 0, []
                continue

            thr = float(self.settings.get("mic_threshold"))
            if not recording:
                pre.append(blk)
                if len(pre) > 10:
                    pre.pop(0)
                speech_blocks = speech_blocks + 1 if rms > thr else 0
                can_hear = active or self.settings.get("wake_word_enabled")
                if speech_blocks >= 3 and can_hear:
                    recording, rec, silence = True, list(pre), 0
                continue

            rec.append(blk)
            silence = silence + 1 if rms < thr * 0.7 else 0
            max_len = 14.0 if active else 8.0
            if silence * BLOCK_S > 0.85 or len(rec) * BLOCK_S > max_len:
                pcm = np.concatenate(rec).tobytes()
                dur = len(rec) * BLOCK_S
                recording, rec, speech_blocks, silence, pre = False, [], 0, 0, []
                if dur < 0.5:
                    continue
                self._handle_utterance(pcm, active)
                mic.drain()
                self.clap.reset()

    def _handle_utterance(self, pcm, was_active):
        try:
            text = self.stt.transcribe(pcm, RATE)
        except STTError as e:
            log.warning("STT: %s", e)
            self.on_error("Spracherkennung momentan nicht erreichbar.")
            return
        if not text:
            return
        log.info("Erkannt: %s", text)
        had, rest = strip_wake_word(text)
        if was_active or self.listening_for_command:
            self._active_until = 0.0
            self.on_active(False)
            self.on_text(rest if had else text, "voice")
        elif had:
            if rest:
                self.on_text(rest, "voice")
            else:
                self.request_listen(8.0)
                self.on_text("", "wake")
