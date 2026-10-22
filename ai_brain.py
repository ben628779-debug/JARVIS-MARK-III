"""Das Gehirn: Gespraechsverlauf, Intent-Klassifikation, Antworten, Mail-Hilfen, Lernen."""
import datetime as _dt
import json
import re
import threading
import time

from ai import intent_parser as ip
from ai.gemini_client import GeminiClient, GeminiError
from core import logger

log = logger.get("brain")

INTENT_HELP = """Erlaubte intents und ihre params:
- chat: normale Unterhaltung/Frage/Rechnung (params leer, Antwort in reply)
- open_application: {"application": "name"}
- open_folder: {"folder": "downloads|desktop|documents|pictures|music|videos|jarvis"}
- open_file: {"name": "dateiname"}
- open_website: {"url": "..."}
- web_search: {"query": "..."}  (nutze das fuer ALLES Aktuelle: Wetter, News, Kurse, Sport, aktuelle Ereignisse)
- system_action: {"action": "volume_up|volume_down|mute|play_pause|next_track|prev_track|lock|screenshot|time|date"}
- mail_unread: {} | mail_summarize: {} | mail_clean: {}
- mail_read: {"index": 1}  | mail_delete: {"index": 1}
- mail_search: {"query": "..."}
- mail_compose: {"to": "name oder adresse", "subject": "...", "body": "fertiger Text oder leer", "instruction": "worum es geht"}
- remember: {"text": "was gemerkt werden soll"} | forget: {"query": "..."}
- call_me: {"delay_minutes": 0, "message": ""} | send_sms: {"message": "..."}
- delete_file: {"name": "dateiname"}
- stop: {}"""


class AIBrain:
    def __init__(self, settings, memory):
        self.settings = settings
        self.memory = memory
        self.gemini = GeminiClient(settings)
        self.history = []              # (rolle, text)
        self._lock = threading.Lock()
        self._last_learn = 0.0

    # ----------------------------------------------------------------- Prompt
    def _system(self):
        now = _dt.datetime.now().strftime("%A, %d.%m.%Y %H:%M")
        return (
            "Du bist J.A.R.V.I.S, der persoenliche KI-Assistent des Nutzers - hoeflich, praezise, "
            "trocken-britischer Humor. Sprich den Nutzer mit 'Sir' an. Deine Antworten werden VORGELESEN: "
            "maximal 2-3 kurze Saetze, keine Listen, kein Markdown, keine Emojis. Antworte auf Deutsch, "
            "ausser der Nutzer spricht eine andere Sprache. Behaupte NIE, eine Aktion sei erledigt - die "
            "lokale Engine fuehrt Aktionen aus und meldet das Ergebnis.\n"
            "Aktuelle Zeit: %s\n\nWas du ueber den Nutzer gelernt hast:\n%s\n\n"
            "Gib AUSSCHLIESSLICH ein JSON-Objekt zurueck: {\"intent\": ..., \"params\": {...}, \"reply\": \"...\"}\n"
            "'reply' ist bei chat die Antwort, sonst ein kurzer Satz, was du tust.\n%s"
        ) % (now, self.memory.context_block(), INTENT_HELP)

    def available(self):
        return self.gemini.available()

    # ----------------------------------------------------------------- Klassifikation
    def classify(self, text: str) -> ip.Intent:
        with self._lock:
            turns = self.history[-10:] + [("user", text)]
        raw = self.gemini.generate(turns, system=self._system(), json_mode=True, temperature=0.4)
        intent = ip.from_gemini_json(raw)
        reply = intent.reply or ("" if intent.name != "chat" else raw)
        with self._lock:
            self.history.append(("user", text))
            self.history.append(("model", reply or intent.name))
            self.history = self.history[-20:]
        return intent

    # ----------------------------------------------------------------- Hilfsfunktionen
    def grounded_answer(self, query: str) -> str:
        prompt = ("Beantworte kurz und praezise auf Deutsch (maximal 3 Saetze, fuer Sprachausgabe, kein Markdown) "
                  "mit AKTUELLEN Informationen aus dem Web:\n" + query)
        return _clean(self.gemini.generate(prompt, grounded=True, temperature=0.3, timeout=50))

    def summarize(self, text: str, instruction="Fasse in 2 kurzen Saetzen zusammen.") -> str:
        prompt = "%s Deutsch, fuer Sprachausgabe, kein Markdown.\n\n%s" % (instruction, text[:6000])
        return _clean(self.gemini.generate(prompt, temperature=0.3))

    def draft_mail(self, instruction: str, recipient: str = "") -> dict:
        facts = self.memory.context_block()
        prompt = ("Schreibe eine E-Mail im Namen des Nutzers. Auftrag: %s\nEmpfaenger: %s\n"
                  "Bekannte Infos ueber den Nutzer:\n%s\n"
                  "Gib NUR JSON zurueck: {\"subject\": \"...\", \"body\": \"...\"}. Hoeflich, knapp, "
                  "mit Gruss. Erfinde keine Fakten." % (instruction, recipient, facts))
        raw = self.gemini.generate(prompt, json_mode=True, temperature=0.5)
        try:
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
            return {"subject": str(data.get("subject", "")), "body": str(data.get("body", ""))}
        except json.JSONDecodeError:
            return {"subject": "", "body": raw}

    def classify_mails(self, mails: list) -> dict:
        """mails: [{id, from, subject, preview}] -> {id: kategorie}"""
        lines = "\n".join("%s | %s | %s | %s" % (m["id"], m["from"], m["subject"], m.get("preview", "")[:120])
                          for m in mails)
        rules = self.memory.db.all_facts("mail")
        rule_txt = "\n".join("- %s: %s" % (r["key"], r["value"]) for r in rules) or "(keine)"
        prompt = ("Ordne jede Mail genau einer Kategorie zu: wichtig, persoenlich, newsletter, werbung, "
                  "benachrichtigung, sonstiges. Beachte die gelernten Nutzerregeln:\n%s\n\nMails (id | von | betreff | vorschau):\n%s\n\n"
                  "Gib NUR JSON zurueck: {\"<id>\": \"<kategorie>\", ...}" % (rule_txt, lines))
        raw = self.gemini.generate(prompt, json_mode=True, temperature=0.1, timeout=50)
        try:
            return {str(k): str(v).lower() for k, v in json.loads(raw).items()}
        except Exception:
            return {}

    # ----------------------------------------------------------------- Lernen
    def learn(self, user_text: str, reply: str):
        """Extrahiert dauerhafte Fakten/Vorlieben. Laeuft im Hintergrund, max. 1 Aufruf / 8 s."""
        if not self.settings.get("learning_enabled") or not self.gemini.available():
            return
        if len(user_text) < 12 or time.time() - self._last_learn < 8:
            return
        self._last_learn = time.time()
        prompt = (
            "Entscheide, ob der Nutzer in diesem Satz etwas Dauerhaftes ueber sich preisgegeben hat "
            "(Name, Vorlieben, Gewohnheiten, Personen, Termine-Routinen, Programme, E-Mail-Regeln, Korrekturen "
            "an deinem Verhalten). Keine einmaligen Befehle, keine Passwoerter/Zahlungsdaten.\n"
            "Nutzer: %s\nJ.A.R.V.I.S: %s\n\nGib NUR JSON zurueck: {\"facts\": [{\"category\": "
            "\"preferences|applications|commands|knowledge|mail|contacts\", \"key\": \"kurzer Name\", "
            "\"value\": \"Inhalt\"}]} - leere Liste wenn nichts Dauerhaftes." % (user_text, reply))
        try:
            raw = self.gemini.generate(prompt, json_mode=True, temperature=0.1, timeout=25)
            data = json.loads(raw)
            for f in (data.get("facts") or [])[:4]:
                cat = str(f.get("category", "knowledge")).lower()
                if cat not in ("preferences", "applications", "commands", "knowledge", "mail", "contacts"):
                    cat = "knowledge"
                self.memory.remember(cat, str(f.get("key", "")), str(f.get("value", "")), source="gelernt")
        except (GeminiError, json.JSONDecodeError, AttributeError, TypeError) as e:
            log.info("Lernen uebersprungen: %s", e)


def _clean(text: str) -> str:
    text = re.sub(r"[*_#`>]+", "", text)
    text = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()
