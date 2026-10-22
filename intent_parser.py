"""Intent-Erkennung. Lokale Regeln zuerst (schnell, ohne API), sonst entscheidet Gemini.

Gemini liefert NUR Intents (JSON). Ausgefuehrt wird ausschliesslich, was die lokale
Command-Engine in ihrer Whitelist kennt - nie freier Shell-Code.
"""
import json
import re
from dataclasses import dataclass, field

VALID_INTENTS = {
    "chat", "open_application", "open_folder", "open_file", "open_website", "web_search",
    "system_action", "mail_unread", "mail_read", "mail_summarize", "mail_search", "mail_compose",
    "mail_delete", "mail_clean", "remember", "forget", "call_me", "send_sms", "delete_file", "stop",
}

SYSTEM_ACTIONS = {"volume_up", "volume_down", "mute", "play_pause", "next_track", "prev_track",
                  "lock", "screenshot", "time", "date"}

ORDINALS = {"erste": 1, "ersten": 1, "erster": 1, "zweite": 2, "zweiten": 2, "dritte": 3, "dritten": 3,
            "vierte": 4, "vierten": 4, "fuenfte": 5, "fünfte": 5, "fünften": 5, "letzte": -1, "letzten": -1,
            "first": 1, "second": 2, "third": 3, "last": -1, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5}

WAKE_PATTERN = re.compile(
    r"^\s*(?:(?:hey|hi|hallo|ok|okay|hej)[\s,]+)?(?:j\.?\s?a\.?\s?r\.?\s?v\.?\s?i\.?\s?s|jarvis|dscharvis|"
    r"dschar\s?vis|charvis|jarvi|jarwis|dscharwis)\b[\s,.:!?-]*", re.IGNORECASE)

FOLDERS = {
    "downloads": "downloads", "download": "downloads", "desktop": "desktop", "schreibtisch": "desktop",
    "dokumente": "documents", "documents": "documents", "eigene dateien": "documents",
    "bilder": "pictures", "pictures": "pictures", "fotos": "pictures",
    "musik": "music", "music": "music", "videos": "videos", "jarvis": "jarvis", "jarvis ordner": "jarvis",
}

KNOWN_SITES = {"youtube": "https://www.youtube.com", "google": "https://www.google.com",
               "github": "https://github.com", "gmail": "https://mail.google.com",
               "outlook": "https://outlook.live.com", "netflix": "https://www.netflix.com",
               "twitch": "https://www.twitch.tv", "reddit": "https://www.reddit.com",
               "amazon": "https://www.amazon.de", "wikipedia": "https://de.wikipedia.org"}


@dataclass
class Intent:
    name: str
    params: dict = field(default_factory=dict)
    reply: str = ""
    source: str = "rule"


def strip_wake_word(text: str):
    """-> (hatte_wake_word, rest)"""
    m = WAKE_PATTERN.match(text)
    if m:
        return True, text[m.end():].strip()
    return False, text.strip()


YES = re.compile(r"^\s*(ja|jawohl|jep|yes|yeah|klar|bestätigt|bestätige|bestaetigt|mach das|mach es|los|ok|okay|genau|senden|sende es|ausführen)\b", re.I)
NO = re.compile(r"^\s*(nein|nee|no|nicht|abbrechen|stopp|stop|lass es|lieber nicht|cancel)\b", re.I)


def is_yes(t):
    return bool(YES.match(t))


def is_no(t):
    return bool(NO.match(t))


def _ordinal(text):
    m = re.search(r"\b(\d)\b", text)
    if m:
        return int(m.group(1))
    for word, n in ORDINALS.items():
        if re.search(r"\b" + word + r"\b", text, re.I):
            return n
    return 1


def parse_local(text: str):
    t = text.strip().rstrip(".!?").strip()
    low = t.lower()
    if not low:
        return None

    if re.match(r"^(stop|stopp|halt|sei still|ruhe|schweig|hör auf)\b", low):
        return Intent("stop")

    m = re.match(r"^(?:merk dir|merke dir|speicher|speichere)\s+(?:bitte\s+)?(?:dass\s+)?(.+)$", low)
    if m:
        return Intent("remember", {"text": t[m.start(1):]})
    m = re.match(r"^(?:vergiss|vergesse|lösche die erinnerung)\s+(?:bitte\s+)?(?:dass\s+|alles über\s+)?(.+)$", low)
    if m:
        return Intent("forget", {"query": m.group(1)})

    # --- Mail ---
    if re.search(r"(ungelesene|neue)\s+(e-?mails?|mails?|nachrichten)|wie viele\s+(e-?mails?|mails?)|habe ich (neue )?(e-?mails?|post)", low):
        return Intent("mail_unread")
    if re.search(r"(fass|fasse)\w*\s+(meine\s+|die\s+)?(e-?mails?|mails?|posteingang)\s*(zusammen)?|zusammenfassung.*(mails?|posteingang)", low):
        return Intent("mail_summarize")
    if re.search(r"(räum|raeum|sortier|bereinig)\w*\s+(mein\w*\s+)?(postfach|posteingang|mails?|e-?mails?)(\s+auf)?", low):
        return Intent("mail_clean")
    m = re.search(r"(?:les|lies|lese|zeig)\w*\s+(?:mir\s+)?(?:die\s+|meine\s+)?(\w+)\s+(?:e-?mail|mail|nachricht)", low)
    if m:
        return Intent("mail_read", {"index": _ordinal(m.group(1))})
    m = re.search(r"(?:lösche|loesche|entferne)\s+(?:die\s+)?(\w+)\s+(?:e-?mail|mail)", low)
    if m:
        return Intent("mail_delete", {"index": _ordinal(m.group(1))})
    m = re.search(r"(?:suche|such)\w*\s+(?:in\s+meinen\s+)?(?:e-?mails?|mails?|postfach)\s+(?:nach|von)\s+(.+)", low)
    if m:
        return Intent("mail_search", {"query": m.group(1)})

    # --- Telefon ---
    if re.search(r"\b(ruf|ruf\s+mich|rufe)\b.*\bmich\b.*\ban\b|^call me|ruf mich an", low):
        mm = re.search(r"in\s+(\d+)\s+(minuten?|min|stunden?)", low)
        delay = 0
        if mm:
            delay = int(mm.group(1)) * (60 if mm.group(2).startswith("stund") else 1)
        return Intent("call_me", {"delay_minutes": delay, "message": ""})

    # --- Systemaktionen ---
    sysmap = [
        (r"\b(lauter|volume up|mach.*lauter)\b", "volume_up"), (r"\b(leiser|volume down|mach.*leiser)\b", "volume_down"),
        (r"\b(stumm|mute|ton aus)\b", "mute"), (r"\b(nächster titel|naechster titel|nächstes lied|skip|next track)\b", "next_track"),
        (r"\b(vorheriger titel|letzter titel|previous track)\b", "prev_track"),
        (r"^(pause|musik pause|play|weiter ?spielen|musik an|musik aus|pausiere)\b", "play_pause"),
        (r"\b(sperre|sperr)\w*\s+(den\s+)?(pc|computer|bildschirm|rechner)|\block\b", "lock"),
        (r"\b(screenshot|bildschirmfoto|bildschirmaufnahme)\b", "screenshot"),
        (r"\b(wie spät|wieviel uhr|wie viel uhr|uhrzeit)\b", "time"), (r"\b(welcher tag|welches datum|datum heute|den wievielten)\b", "date"),
    ]
    for pat, act in sysmap:
        if re.search(pat, low):
            return Intent("system_action", {"action": act})

    # --- Websuche ---
    m = re.match(r"^(?:suche|such|google|recherchiere|finde)\s+(?:bitte\s+)?(?:im\s+(?:internet|web)\s+|online\s+|mal\s+)?(?:nach\s+|für\s+)?(.+)$", low)
    if m:
        return Intent("web_search", {"query": t[m.start(1):]})

    # --- Oeffnen ---
    m = re.match(r"^(?:bitte\s+)?(?:öffne|oeffne|starte|start|open|launch|mach)\s+(?:mir\s+)?(?:bitte\s+)?(?:die\s+|den\s+|das\s+|meinen\s+|meine\s+|mein\s+)?(?:app\s+|anwendung\s+|programm\s+)?(.+?)(?:\s+auf)?$", low)
    if m:
        target = m.group(1).strip()
        key = target.replace("-ordner", "").replace(" ordner", "").strip()
        if key in FOLDERS:
            return Intent("open_folder", {"folder": FOLDERS[key]})
        if key in KNOWN_SITES:
            return Intent("open_website", {"url": KNOWN_SITES[key]})
        if re.match(r"^(https?://|www\.)\S+$", target) or re.match(r"^[\w-]+\.(com|de|org|net|io|tv|eu)(/\S*)?$", target):
            return Intent("open_website", {"url": target})
        if re.search(r"\.(txt|pdf|docx?|xlsx?|pptx?|png|jpe?g|mp3|mp4|zip)$", target):
            return Intent("open_file", {"name": target})
        return Intent("open_application", {"application": target})
    return None


def from_gemini_json(raw: str) -> Intent:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return Intent("chat", reply=raw, source="gemini")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return Intent("chat", reply=raw, source="gemini")
    name = str(data.get("intent", "chat")).strip().lower()
    if name not in VALID_INTENTS:
        name = "chat"
    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    if name == "system_action" and params.get("action") not in SYSTEM_ACTIONS:
        name = "chat"
    return Intent(name, params, str(data.get("reply", "")).strip(), source="gemini")
