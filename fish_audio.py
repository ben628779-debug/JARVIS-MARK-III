"""Fish Audio TTS (optional)."""
import requests

from core import logger
from tts.edge_tts_engine import TTSError

log = logger.get("fishaudio")


def synthesize(text: str, api_key: str, voice_id: str, model="s1") -> bytes:
    if not api_key:
        raise TTSError("Kein Fish-Audio API Key hinterlegt.")
    body = {"text": text, "format": "mp3", "mp3_bitrate": 128, "latency": "normal"}
    if voice_id:
        body["reference_id"] = voice_id.strip()
    try:
        r = requests.post("https://api.fish.audio/v1/tts", json=body, timeout=40,
                          headers={"Authorization": "Bearer " + api_key, "model": model,
                                   "Content-Type": "application/json"})
    except requests.RequestException as e:
        raise TTSError("Fish Audio nicht erreichbar (%s)" % type(e).__name__)
    if r.status_code == 200 and r.content:
        return r.content
    raise TTSError("Fish Audio Fehler %d: %s" % (r.status_code, r.text[:100]))
