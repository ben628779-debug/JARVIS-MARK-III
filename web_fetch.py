"""Seitentext abrufen (ohne zusaetzliche Abhaengigkeiten)."""
import re
from html.parser import HTMLParser

import requests

from core import logger

log = logger.get("webfetch")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def fetch_text(url: str, max_chars=6000) -> str:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 JARVIS"})
    r.raise_for_status()
    p = _Text()
    p.feed(r.text)
    return " ".join(p.parts)[:max_chars]
