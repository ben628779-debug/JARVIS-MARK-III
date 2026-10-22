"""Waehlt den TTS-Anbieter und faellt automatisch zurueck: Auswahl -> Edge -> Windows-Stimme."""
from core import logger
from tts import edge_tts_engine, elevenlabs, fish_audio, sapi_fallback
from tts.edge_tts_engine import TTSError

log = logger.get("tts")


class TTSManager:
    def __init__(self, settings):
        self.settings = settings
        self.last_provider = ""
        self.last_error = ""

    def _call(self, provider, text):
        s = self.settings
        if provider == "elevenlabs":
            return elevenlabs.synthesize(text, s.secret("elevenlabs_api_key"), s.get("elevenlabs_voice_id"),
                                         s.get("elevenlabs_model"))
        if provider == "fish":
            return fish_audio.synthesize(text, s.secret("fish_api_key"), s.get("fish_voice_id"), s.get("fish_model"))
        if provider == "edge":
            return edge_tts_engine.synthesize(text, s.get("edge_voice"), s.get("edge_rate"))
        return sapi_fallback.synthesize(text)

    def synthesize(self, text: str, on_warning=None):
        """-> (bytes, provider). Wirft TTSError nur, wenn ALLE Anbieter ausfallen."""
        chosen = self.settings.get("tts_provider") or "edge"
        chain = [chosen] + [p for p in ("edge", "sapi") if p != chosen]
        errors = []
        for prov in chain:
            try:
                data = self._call(prov, text)
                if errors and on_warning:
                    on_warning("%s nicht verfuegbar (%s) - nutze %s" % (errors[0][0], errors[0][1], prov))
                self.last_provider, self.last_error = prov, ""
                return data, prov
            except TTSError as e:
                log.warning("TTS %s fehlgeschlagen: %s", prov, e)
                errors.append((prov, str(e)))
        self.last_error = "; ".join("%s: %s" % e for e in errors)
        raise TTSError("Meine Sprachausgabe ist momentan nicht verfuegbar.")

    def status(self):
        s = self.settings
        prov = s.get("tts_provider")
        import importlib.util
        if importlib.util.find_spec("edge_tts") is None and prov in ("edge",):
            return False, "EDGE-TTS PAKET FEHLT"
        if prov == "elevenlabs" and not s.secret("elevenlabs_api_key"):
            return False, "ELEVENLABS KEY FEHLT (Edge aktiv)"
        if prov == "fish" and not s.secret("fish_api_key"):
            return False, "FISH KEY FEHLT (Edge aktiv)"
        return True, prov.upper()
