"""Sprechwarteschlange: nie zwei Antworten gleichzeitig, mit Vorab-Synthese des naechsten Satzes."""
import queue
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from core import logger
from tts.audio_player import AudioError, AudioPlayer
from tts.edge_tts_engine import TTSError

log = logger.get("speech")


def split_sentences(text: str, max_len=260):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out, cur = [], ""
    for p in parts:
        if len(cur) + len(p) + 1 <= max_len:
            cur = (cur + " " + p).strip()
        else:
            if cur:
                out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return [c for c in out if c.strip()]


class SpeechQueue:
    def __init__(self, settings, tts_manager, on_speaking, on_level, on_error, on_idle):
        self.settings, self.tts = settings, tts_manager
        self.on_speaking, self.on_level, self.on_error, self.on_idle = on_speaking, on_level, on_error, on_idle
        self.player = AudioPlayer()
        self._q = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._epoch = 0
        self._alive = True
        self._warned_audio = False
        threading.Thread(target=self._run, daemon=True, name="speech-queue").start()

    def say(self, text: str):
        if text and text.strip():
            self._q.put((self._epoch, text.strip()))

    def clear(self):
        """Aktuelle Ausgabe abbrechen und Warteschlange leeren."""
        self._epoch += 1
        self.player.stop()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def shutdown(self):
        self._alive = False
        self.clear()
        self._q.put((self._epoch, ""))

    def _run(self):
        while self._alive:
            epoch, text = self._q.get()
            if not text or epoch != self._epoch:
                continue
            self.on_speaking(True)
            try:
                chunks = split_sentences(text)
                fut = self._pool.submit(self._synth, chunks[0]) if chunks else None
                for n in range(len(chunks)):
                    audio = fut.result() if fut else None
                    fut = self._pool.submit(self._synth, chunks[n + 1]) if n + 1 < len(chunks) else None
                    if epoch != self._epoch:
                        break
                    if audio is None:
                        continue
                    try:
                        self.player.play(audio, int(self.settings.get("volume")),
                                         self.settings.get("output_device"), self.on_level)
                    except AudioError as e:
                        log.error("Wiedergabe: %s", e)
                        self.on_error("Ich kann momentan nicht ueber den Lautsprecher sprechen: %s" % e)
                        break
            except Exception:
                log.exception("Sprechwarteschlange")
            finally:
                self.on_level(0.0)
                self.on_speaking(False)
                if self._q.empty():
                    self.on_idle()

    def _synth(self, text):
        try:
            data, _ = self.tts.synthesize(text, on_warning=self._warn)
            return data
        except TTSError as e:
            self.on_error(str(e))
            return None

    def _warn(self, msg):
        self.on_error(msg)
