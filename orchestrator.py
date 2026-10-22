"""Verbindet alles: Hoeren -> Verstehen -> Ausfuehren -> Sprechen. Meldet Zustaende an die GUI.

Alle Netzwerk-/Audio-Arbeit laeuft in eigenen Threads - die GUI friert nie ein.
"""
import queue
import threading
import time

from PySide6.QtCore import QObject, Signal

from ai import intent_parser as ip
from ai.ai_brain import AIBrain
from ai.gemini_client import GeminiError
from commands.command_router import CommandRouter, Result
from core import logger
from core.security import Security
from core.state import S
from mail.mail_manager import MailManager
from memory.memory_manager import MemoryManager
from telephony.twilio_client import Telephony
from tts.speech_queue import SpeechQueue
from tts.tts_manager import TTSManager
from voice import microphone
from voice.listener import Listener
from voice.speech_recognition import create_engine

log = logger.get("orchestrator")

CONFIRM_TIMEOUT = 45.0


class Orchestrator(QObject):
    state_changed = Signal(str)
    level = Signal(float)
    message = Signal(str, str)              # rolle (user|jarvis|system), text
    error = Signal(str)
    memory_changed = Signal()
    startup_line = Signal(str, str, bool)   # label, status, ok

    def __init__(self, settings, launch_state):
        super().__init__()
        self.settings, self.launch_state = settings, launch_state
        self.security = Security(settings)
        self.memory = MemoryManager(settings)
        self.brain = AIBrain(settings, self.memory)
        self.mail = MailManager(settings)
        self.telephony = Telephony(settings, self.security)
        self.router = CommandRouter(settings, self.security, self.memory, self.brain, self.mail, self.telephony)
        self.tts = TTSManager(settings)
        self.memory.on_new(lambda *a: self.memory_changed.emit())

        self._state = S.IDLE
        self._speaking = False
        self._stage = None                   # None | THINKING | PROCESSING
        self._listen_active = False
        self._error_until = 0.0
        self._pending = None                 # (Confirm, zeitstempel)
        self._want_command = False
        self._follow_up = False
        self._cmds = queue.Queue()

        self.speech = SpeechQueue(settings, self.tts, self._on_speaking, self._on_speech_level,
                                  self._on_audio_error, self._on_speech_idle)
        self.listener = Listener(settings, create_engine(settings), self._is_busy, self._on_mic_level,
                                 self._on_listener_text, self._on_listen_active, self._on_listener_error)
        self._worker = threading.Thread(target=self._work, daemon=True, name="worker")

    # ------------------------------------------------------------------ Lebenszyklus
    def start(self):
        self._worker.start()
        self.listener.start()

    def shutdown(self):
        self.listener.stop()
        self.speech.shutdown()
        self._cmds.put(None)

    def apply_settings(self):
        self.listener.stt = create_engine(self.settings)
        self.listener.reopen_mic()

    # ------------------------------------------------------------------ Zustand
    def _is_busy(self):
        return self._speaking or self._stage is not None

    def _recompute(self):
        if time.monotonic() < self._error_until:
            new = S.ERROR
        elif self._speaking:
            new = S.SPEAKING
        elif self._stage == S.PROCESSING:
            new = S.PROCESSING
        elif self._stage == S.THINKING:
            new = S.THINKING
        elif self._listen_active:
            new = S.LISTENING
        else:
            new = S.IDLE
        if new != self._state:
            self._state = new
            self.state_changed.emit(new)

    def _flash_error(self, text):
        log.warning("Fehler: %s", text)
        self._error_until = time.monotonic() + 4.0
        self.error.emit(text)
        self.message.emit("system", text)
        self._recompute()
        threading.Timer(4.2, self._recompute).start()

    # ------------------------------------------------------------------ Callbacks (aus Threads)
    def _on_speaking(self, on):
        self._speaking = on
        self._recompute()

    def _on_speech_level(self, v):
        self.level.emit(float(v))

    def _on_mic_level(self, v):
        if not self._speaking:
            self.level.emit(float(v))

    def _on_audio_error(self, text):
        self._flash_error(text)

    def _on_listen_active(self, on):
        self._listen_active = on
        self._recompute()

    def _on_listener_error(self, text):
        self._flash_error(text)

    def _on_speech_idle(self):
        now = time.monotonic()
        if self._pending and now - self._pending[1] > CONFIRM_TIMEOUT:
            self._pending = None
        if self._stage is not None:
            return
        if self._want_command or self._pending or self._follow_up:
            secs = 8.0 if (self._want_command or self._pending) else 6.0
            self._want_command = self._follow_up = False
            self.listener.request_listen(secs)

    def _on_listener_text(self, text, source):
        if source in ("clap", "wake") and not text:
            self._want_command = True
            self.say("Ja, Sir?", log_message=False)
            return
        self.submit_text(text, source)

    # ------------------------------------------------------------------ Eingaben
    def submit_text(self, text, source="text"):
        text = (text or "").strip()
        if text:
            self._cmds.put((text, source))

    def push_to_talk(self):
        if self.security.killed:
            self.message.emit("system", "Der Not-Aus ist aktiv.")
            return
        self.speech.clear()
        self.listener.request_listen(10.0)

    def interrupt(self):
        self.speech.clear()
        self._follow_up = self._want_command = False

    def emergency_stop(self, on=True):
        self.security.emergency_stop(on)
        if on:
            self.speech.clear()
            self._pending = None
            self.listener.cancel_listen()
        self.message.emit("system", "NOT-AUS AKTIV - alle Aktionen gesperrt." if on else "Not-Aus aufgehoben.")

    def say(self, text, log_message=True):
        if log_message:
            self.message.emit("jarvis", text)
        self.speech.say(text)

    def greet(self):
        first = self.launch_state.is_first_launch
        text = "Guten Tag Sir." if first else "Willkommen zurück Sir."
        self.launch_state.register_launch()
        self.say(text)
        if first and not self.settings.secret("gemini_api_key"):
            self.message.emit("system", "Tipp: Tragen Sie unter SETTINGS Ihren Gemini API Key ein, damit ich denken kann.")

    def test_voice(self):
        self.say("Dies ist ein Test meiner Stimme, Sir.")

    # ------------------------------------------------------------------ Verarbeitung
    def _work(self):
        while True:
            item = self._cmds.get()
            if item is None:
                return
            text, source = item
            try:
                self._process(text, source)
            except Exception:
                log.exception("Verarbeitung")
                self._flash_error("Unerwarteter Fehler - Details in der Logdatei.")
            finally:
                self._stage = None
                self._recompute()

    def _process(self, text, source):
        had, text = ip.strip_wake_word(text)
        if not text:
            self._want_command = True
            self.say("Ja, Sir?", log_message=False)
            return
        self.message.emit("user", text)
        self.speech.clear()
        self._stage = S.THINKING
        self._recompute()

        if self.security.killed and not ip.parse_local(text):
            pass

        # --- offene Rueckfrage?
        if self._pending:
            confirm, ts = self._pending
            self._pending = None
            if time.monotonic() - ts <= CONFIRM_TIMEOUT:
                if ip.is_yes(text):
                    self._stage = S.PROCESSING
                    self._recompute()
                    res = self._run_confirmed(confirm)
                    self._finish(text, res)
                    return
                if ip.is_no(text):
                    self._finish(text, Result("Abgebrochen, Sir."))
                    return
            # sonst: normaler neuer Befehl

        intent = ip.parse_local(text)
        if intent is None:
            if not self.brain.available():
                self._finish(text, Result("Bitte tragen Sie zuerst in den Einstellungen einen Gemini API Key ein, Sir.", ok=False))
                return
            try:
                intent = self.brain.classify(text)
            except GeminiError as e:
                log.warning("Gemini: %s", e)
                self._finish(text, Result("Gemini ist momentan nicht erreichbar.", ok=False))
                return

        if intent.name != "chat":
            self._stage = S.PROCESSING
            self._recompute()
        if intent.name == "web_search":
            self.message.emit("system", "WEB SEARCH: %s" % intent.params.get("query", ""))
        res = self.router.execute(intent)
        if res.stop_speaking:
            self.speech.clear()
            return
        if res.confirm:
            self._pending = (res.confirm, time.monotonic())
            res = Result(res.confirm.prompt)
        self._finish(text, res, intent.name)

    def _run_confirmed(self, confirm):
        try:
            return confirm.action()
        except Exception as e:
            log.exception("Bestaetigte Aktion")
            return Result("Das hat leider nicht geklappt: %s." % type(e).__name__, ok=False)

    def _finish(self, user_text, res: Result, intent_name="chat"):
        self._stage = None
        reply = res.text or "Erledigt, Sir."
        if not res.ok:
            self._error_until = time.monotonic() + 2.5
            threading.Timer(2.7, self._recompute).start()
        self._follow_up = bool(self.settings.get("follow_up_enabled")) and intent_name in ("chat", "web_search")
        self.say(reply)
        self.memory.log_exchange(user_text, reply)
        if res.ok and intent_name in ("chat", "web_search", "remember", "mail_compose"):
            threading.Thread(target=self.brain.learn, args=(user_text, reply), daemon=True).start()
        self._recompute()

    # ------------------------------------------------------------------ Startup-Pruefung
    def run_startup_checks(self):
        """Blockierend - in einem Hintergrund-Thread aufrufen. Haengt nie, wenn etwas fehlt."""
        def line(label, ok_text, ok, bad_text=None):
            self.startup_line.emit(label, ok_text if ok else (bad_text or "OFFLINE"), ok)

        from core import deps
        miss = deps.missing()
        if miss:
            self.message.emit("system", "FEHLENDE PAKETE: %s - SETTINGS -> INSTALL MISSING PACKAGES oder 'python install_deps.py'." % ", ".join(miss))
        from tts.audio_player import probe_output
        ok, short, detail = probe_output(self.settings.get("output_device"))
        line("VOICE SYSTEM", "ONLINE", ok, short)
        self.message.emit("system", detail if ok else "Lautsprecher: " + detail)
        ok, short, detail = microphone.diagnose(self.settings.get("input_device"))
        line("MICROPHONE", "ONLINE", ok, short)
        self.message.emit("system", detail)
        if self.brain.available():
            ok, txt = self.brain.gemini.test()
            line("GEMINI CORE", "ONLINE", ok, "OFFLINE")
            line("WEB SEARCH", "ONLINE", ok, "BROWSER-FALLBACK")
        else:
            line("GEMINI CORE", "ONLINE", False, "KEIN API KEY")
            line("WEB SEARCH", "ONLINE", False, "BROWSER-FALLBACK")
        ok, txt = self.tts.status()
        line("VOICE ENGINE", txt, ok, txt)
        line("MEMORY", "%d FACTS" % len(self.memory.db.all_facts()), True)
        line("MAIL", "CONNECTED" if self.mail.configured() else "NOT SET UP", self.mail.configured(), "NOT SET UP")
