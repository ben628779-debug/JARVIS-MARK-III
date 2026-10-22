"""Websuche: Gemini mit Google-Grounding (aktuell, mit Quellen). Fallback: Standardbrowser."""
import urllib.parse
import webbrowser

from ai.gemini_client import GeminiError
from core import logger

log = logger.get("websearch")


def search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)


def open_in_browser(query: str):
    webbrowser.open(search_url(query))


def search(brain, query: str):
    """-> (antwort_text | None, fehler | None)"""
    if not brain.available():
        return None, "Kein Gemini API Key hinterlegt."
    try:
        return brain.grounded_answer(query), None
    except GeminiError as e:
        log.warning("Websuche fehlgeschlagen: %s", e)
        return None, str(e)
