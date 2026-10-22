"""ElevenLabs TTS (API-Key + Voice-ID in den Einstellungen)."""
import requests

from core import logger
from tts.edge_tts_engine import TTSError

log = logger.get("elevenlabs")


def synthesize(text: str, api_key: str, voice_id: str, model="eleven_multilingual_v2") -> bytes:
    if not api_key:
        raise TTSError("Kein ElevenLabs API Key hinterlegt.")
    if not voice_id:
        raise TTSError("Keine ElevenLabs Voice-ID hinterlegt.")
    try:
        r = requests.post(
            "https://api.elevenlabs.io/v1/text-to-speech/%s" % voice_id.strip(),
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"},
            json={"text": text, "model_id": model,
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
            timeout=30)
    except requests.RequestException as e:
        raise TTSError("ElevenLabs nicht erreichbar (%s)" % type(e).__name__)
    if r.status_code == 200 and r.content:
        return r.content
    detail = ""
    try:
        j = r.json().get("detail", {})
        detail = j.get("message", "") if isinstance(j, dict) else str(j)
    except Exception:
        detail = r.text[:120]
    hints = {401: "API Key ungueltig", 402: "Stimme/Funktion benoetigt einen bezahlten Plan",
             403: "Zugriff verweigert", 404: "Voice-ID nicht gefunden", 422: "Ungueltige Anfrage (Voice-ID/Modell)",
             429: "Zu viele Anfragen oder Kontingent aufgebraucht"}
    raise TTSError("ElevenLabs %d: %s %s" % (r.status_code, hints.get(r.status_code, "Fehler"), detail[:100]))
