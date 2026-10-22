"""Schlanker Gemini-Client ueber die REST-API (kein SDK noetig)."""
import time

import requests

from core import logger

log = logger.get("gemini")

BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-2.5-flash"]


class GeminiError(Exception):
    pass


class GeminiClient:
    def __init__(self, settings):
        self.settings = settings
        self._good_model = None

    def available(self) -> bool:
        return bool(self.settings.secret("gemini_api_key"))

    def _models(self):
        configured = (self.settings.get("gemini_model") or "").strip()
        if configured in ("gemini-flash", "flash", "gemini"):
            configured = "gemini-flash-latest"
        order = [self._good_model, configured] + FALLBACK_MODELS
        seen, out = set(), []
        for m in order:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def generate(self, contents, system=None, json_mode=False, grounded=False,
                 temperature=0.6, timeout=40):
        """contents: str ODER Liste von (rolle, text) mit rolle 'user'|'model'."""
        key = self.settings.secret("gemini_api_key")
        if not key:
            raise GeminiError("Kein Gemini API Key hinterlegt.")
        if isinstance(contents, str):
            contents = [("user", contents)]
        body = {
            "contents": [{"role": r, "parts": [{"text": t}]} for r, t in contents],
            "generationConfig": {"temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode and not grounded:
            body["generationConfig"]["responseMimeType"] = "application/json"
        if grounded:
            body["tools"] = [{"google_search": {}}]

        last_err = None
        for model in self._models():
            for attempt in range(2):
                try:
                    r = requests.post(BASE.format(model=model), json=body, timeout=timeout,
                                      headers={"x-goog-api-key": key, "Content-Type": "application/json"})
                except requests.RequestException as e:
                    last_err = GeminiError("Netzwerkfehler: %s" % type(e).__name__)
                    log.warning("Gemini Netzwerk (%s): %s", model, type(e).__name__)
                    time.sleep(0.6)
                    continue
                if r.status_code == 200:
                    self._good_model = model
                    return self._extract(r.json())
                if r.status_code in (400, 401, 403):
                    msg = self._err_msg(r)
                    if r.status_code == 400 and "model" in msg.lower():
                        last_err = GeminiError(msg)
                        break
                    raise GeminiError("Gemini lehnt die Anfrage ab (%d): %s" % (r.status_code, msg))
                if r.status_code == 404:
                    last_err = GeminiError("Modell %s nicht gefunden" % model)
                    log.warning("Gemini Modell %s nicht gefunden - versuche naechstes", model)
                    break
                if r.status_code in (429, 500, 502, 503, 504):
                    last_err = GeminiError("Gemini ueberlastet/Limit (%d)" % r.status_code)
                    time.sleep(1.2 * (attempt + 1))
                    continue
                last_err = GeminiError("Gemini Fehler %d: %s" % (r.status_code, self._err_msg(r)))
                break
        raise last_err or GeminiError("Gemini nicht erreichbar.")

    @staticmethod
    def _err_msg(r):
        try:
            return r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            return r.text[:200]

    @staticmethod
    def _extract(data):
        cands = data.get("candidates") or []
        if not cands:
            fb = data.get("promptFeedback", {})
            raise GeminiError("Keine Antwort (%s)" % fb.get("blockReason", "leer"))
        parts = cands[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise GeminiError("Leere Antwort von Gemini")
        return text

    def test(self):
        try:
            self.generate("Antworte nur mit: ok", temperature=0, timeout=15)
            return True, "online"
        except GeminiError as e:
            return False, str(e)
