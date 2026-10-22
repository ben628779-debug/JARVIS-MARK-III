"""Speech-to-Text. Austauschbar: neue Engine = Klasse mit transcribe(pcm_bytes, rate) -> str."""
from core import logger

log = logger.get("stt")


class STTError(Exception):
    pass


class GoogleSTT:
    """Nutzt die kostenlose Google-Web-Spracherkennung (Internet noetig, kein Key)."""
    name = "google"

    def __init__(self, language="de-DE"):
        self.language = language

    def transcribe(self, pcm: bytes, rate: int = 16000) -> str:
        try:
            import speech_recognition as sr
        except ImportError:
            raise STTError("Paket 'SpeechRecognition' fehlt.")
        rec = sr.Recognizer()
        try:
            return rec.recognize_google(sr.AudioData(pcm, rate, 2), language=self.language).strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            raise STTError("Spracherkennung nicht erreichbar (%s)" % str(e)[:60])
        except Exception as e:
            raise STTError("Spracherkennung fehlgeschlagen (%s)" % type(e).__name__)


def create_engine(settings):
    return GoogleSTT(settings.get("language") or "de-DE")
