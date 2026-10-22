"""Fuehrt Intents aus - ausschliesslich Whitelist-Aktionen, jede mit Berechtigungspruefung."""
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from ai import intent_parser as ip
from ai.gemini_client import GeminiError
from commands import file_manager, windows_actions
from commands.app_launcher import AppLauncher
from core import logger
from mail.base import MailError
from telephony.twilio_client import TelephonyError
from web import web_search

log = logger.get("router")


@dataclass
class Confirm:
    prompt: str
    action: Callable[[], "Result"]


@dataclass
class Result:
    text: str
    ok: bool = True
    confirm: Optional[Confirm] = None
    stop_speaking: bool = False


class CommandRouter:
    def __init__(self, settings, security, memory, brain, mail, telephony):
        self.settings, self.security, self.memory = settings, security, memory
        self.brain, self.mail, self.tel = brain, mail, telephony
        self.launcher = AppLauncher(settings, memory)
        self.launcher.warmup()                       # Programmliste im Hintergrund aufbauen

    # --------------------------------------------------------------- Hilfen
    def _deny(self, perm):
        if self.security.killed:
            return Result("Der Not-Aus ist aktiv, Sir. Ich fuehre nichts aus.", ok=False)
        return Result("Dafuer fehlt mir die Berechtigung. Sie koennen sie in den Einstellungen freigeben.", ok=False)

    def execute(self, intent: ip.Intent) -> Result:
        fn = getattr(self, "_do_" + intent.name, None)
        if fn is None:
            return Result(intent.reply or "Das habe ich nicht verstanden, Sir.", ok=bool(intent.reply))
        try:
            return fn(intent)
        except (MailError, TelephonyError, GeminiError) as e:
            log.warning("%s: %s", intent.name, e)
            self.security.audit(intent.name.upper(), str(e), ok=False)
            return Result(self._friendly(e), ok=False)
        except Exception as e:
            log.exception("Intent %s", intent.name)
            return Result("Das hat leider nicht geklappt: %s." % type(e).__name__, ok=False)

    @staticmethod
    def _friendly(e):
        if isinstance(e, GeminiError):
            return "Gemini ist momentan nicht erreichbar."
        return str(e) + ("" if str(e).endswith(".") else ".")

    # --------------------------------------------------------------- Unterhaltung
    def _do_chat(self, i):
        return Result(i.reply or "Ich habe dazu leider keine Antwort, Sir.")

    def _do_stop(self, i):
        return Result("", stop_speaking=True)

    # --------------------------------------------------------------- Programme / Dateien
    def _do_open_application(self, i):
        if not self.security.allowed("OPEN_APPS"):
            return self._deny("OPEN_APPS")
        name = (i.params.get("application") or "").strip()
        ok, shown, hint = self.launcher.open(name)
        self.security.audit("OPEN_APP", name, ok)
        if ok:
            return Result("%s wird geoeffnet." % shown)
        msg = "Ich habe %s nicht gefunden, Sir." % shown.title()
        if hint:
            msg += " Meinten Sie %s?" % hint
        return Result(msg, ok=False)

    def _do_open_website(self, i):
        if not self.security.allowed("OPEN_APPS"):
            return self._deny("OPEN_APPS")
        import webbrowser
        url = i.params.get("url", "")
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        self.security.audit("OPEN_URL", url)
        return Result("Die Webseite wird geoeffnet.")

    def _do_open_folder(self, i):
        if not self.security.allowed("FILES_OPEN"):
            return self._deny("FILES_OPEN")
        p = file_manager.folder_path(i.params.get("folder", ""))
        if not p:
            return Result("Diesen Ordner habe ich nicht gefunden.", ok=False)
        file_manager.open_path(p)
        self.security.audit("OPEN_FOLDER", str(p))
        return Result("Ordner %s wird geoeffnet." % p.name)

    def _do_open_file(self, i):
        if not self.security.allowed("FILES_OPEN"):
            return self._deny("FILES_OPEN")
        p = file_manager.find_file(i.params.get("name", ""))
        if not p:
            return Result("Diese Datei habe ich nicht gefunden.", ok=False)
        file_manager.open_path(p)
        self.security.audit("OPEN_FILE", str(p))
        return Result("%s wird geoeffnet." % p.name)

    def _do_delete_file(self, i):
        if not self.security.allowed("FILES_DELETE"):
            return self._deny("FILES_DELETE")
        p = file_manager.find_file(i.params.get("name", ""))
        if not p:
            return Result("Diese Datei habe ich nicht gefunden.", ok=False)

        def go():
            file_manager.trash_file(p)
            self.security.audit("DELETE_FILE", str(p))
            return Result("%s liegt jetzt im Papierkorb." % p.name)
        return Result("", confirm=Confirm("Soll ich %s in den Papierkorb legen?" % p.name, go))

    # --------------------------------------------------------------- Web
    def _do_web_search(self, i):
        if not self.security.allowed("WEB_SEARCH"):
            return self._deny("WEB_SEARCH")
        q = i.params.get("query", "")
        answer, err = web_search.search(self.brain, q)
        self.security.audit("WEB_SEARCH", q, answer is not None)
        if answer:
            return Result(answer)
        web_search.open_in_browser(q)
        return Result("Die Websuche konnte nicht durchgefuehrt werden. Ich habe die Suche im Browser geoeffnet.", ok=False)

    def _do_system_action(self, i):
        if not self.security.allowed("SYSTEM_ACTIONS"):
            return self._deny("SYSTEM_ACTIONS")
        ok, text = windows_actions.run(i.params.get("action", ""))
        self.security.audit("SYSTEM", i.params.get("action", ""), ok)
        return Result(text, ok=ok)

    # --------------------------------------------------------------- Lernen
    def _do_remember(self, i):
        if not self.security.allowed("LEARNING"):
            return self._deny("LEARNING")
        text = i.params.get("text", "").strip()
        if not text:
            return Result("Was soll ich mir merken, Sir?", ok=False)
        self.memory.remember("knowledge", text[:60], text, source="befehl")
        return Result("Gemerkt, Sir.")

    def _do_forget(self, i):
        n = self.memory.forget(i.params.get("query", ""))
        return Result("Ich habe %d Erinnerung%s vergessen." % (n, "" if n == 1 else "en") if n
                      else "Dazu habe ich nichts gespeichert.")

    # --------------------------------------------------------------- Mail
    def _mail_ready(self, perm="READ_EMAIL"):
        if not self.security.allowed(perm):
            return self._deny(perm)
        if not self.mail.configured():
            return Result("Ihr Postfach ist noch nicht verbunden. Das geht in den Einstellungen unter E-Mail.", ok=False)
        return None

    def _do_mail_unread(self, i):
        bad = self._mail_ready()
        if bad:
            return bad
        mails = self.mail.unread(8)
        self.security.audit("MAIL_LIST", "%d ungelesen" % len(mails))
        if not mails:
            return Result("Sie haben keine ungelesenen Mails, Sir.")
        parts = ["%d. %s: %s" % (n, m["from"], m["subject"]) for n, m in enumerate(mails[:5], 1)]
        more = " Und %d weitere." % (len(mails) - 5) if len(mails) > 5 else ""
        return Result("Sie haben %d ungelesene Mails. %s.%s" % (len(mails), ". ".join(parts), more))

    def _do_mail_search(self, i):
        bad = self._mail_ready()
        if bad:
            return bad
        mails = self.mail.search(i.params.get("query", ""))
        if not mails:
            return Result("Dazu habe ich keine Mails gefunden.")
        parts = ["%d. %s: %s" % (n, m["from"], m["subject"]) for n, m in enumerate(mails[:4], 1)]
        return Result("Ich habe %d Treffer. %s." % (len(mails), ". ".join(parts)))

    def _do_mail_read(self, i):
        bad = self._mail_ready()
        if bad:
            return bad
        m = self.mail.by_index(int(i.params.get("index", 1)))
        body = self.mail.body(m)
        try:
            summary = self.brain.summarize("Von: %s\nBetreff: %s\n\n%s" % (m["from"], m["subject"], body),
                                           "Fasse diese E-Mail in hoechstens 3 kurzen Saetzen zusammen.")
        except GeminiError:
            summary = body[:350]
        try:
            self.mail.mark_read(m)
        except MailError:
            pass
        self.security.audit("MAIL_READ", m["subject"])
        return Result("Mail von %s. %s" % (m["from"], summary))

    def _do_mail_summarize(self, i):
        bad = self._mail_ready()
        if bad:
            return bad
        mails = self.mail.unread(10)
        if not mails:
            return Result("Es gibt nichts Neues im Posteingang, Sir.")
        blob = "\n".join("%d) %s | %s | %s" % (n, m["from"], m["subject"], m["preview"]) for n, m in enumerate(mails, 1))
        text = self.brain.summarize(blob, "Fasse die ungelesenen Mails in 3 kurzen Saetzen zusammen und nenne zuerst, was wichtig ist.")
        return Result(text)

    def _do_mail_delete(self, i):
        bad = self._mail_ready("DELETE_EMAIL")
        if bad:
            return bad
        m = self.mail.by_index(int(i.params.get("index", 1)))

        def go():
            self.mail.trash(m)
            self.security.audit("MAIL_DELETE", m["subject"])
            self.mail.last_list = [x for x in self.mail.last_list if x["id"] != m["id"]]
            return Result("Die Mail ist im Papierkorb.")
        return Result("", confirm=Confirm("Soll ich die Mail von %s mit dem Betreff %s loeschen?" % (m["from"], m["subject"]), go))

    def _do_mail_clean(self, i):
        bad = self._mail_ready("DELETE_EMAIL")
        if bad:
            return bad
        mails = self.mail.recent(30)
        cats = self.brain.classify_mails(mails)
        junk = [m for m in mails if cats.get(str(m["id"])) in ("werbung", "newsletter")]
        important = sum(1 for m in mails if cats.get(str(m["id"])) in ("wichtig", "persoenlich"))
        if not junk:
            return Result("Ihr Posteingang ist ordentlich. %d wichtige Mails, nichts zum Aufraeumen." % important)

        def go():
            done = 0
            for m in junk:
                try:
                    self.mail.trash(m)
                    done += 1
                except MailError:
                    break
            self.security.audit("MAIL_CLEAN", "%d verschoben" % done)
            return Result("%d Mails sind im Papierkorb." % done)
        return Result("", confirm=Confirm(
            "Ich habe %d wichtige Mails und %d Werbung oder Newsletter gefunden. Soll ich die %d in den Papierkorb legen?"
            % (important, len(junk), len(junk)), go))

    def _do_mail_compose(self, i):
        bad = self._mail_ready("SEND_EMAIL")
        if bad:
            return bad
        p = i.params
        to = (p.get("to") or "").strip()
        if "@" not in to:
            addr = self.memory.db.find_value("contacts", to) if to else None
            if addr and "@" in addr:
                to = addr
            elif to:
                to = self.mail.find_address(to) or ""
        if "@" not in to:
            return Result("Die Adresse des Empfaengers kenne ich nicht. Bitte nennen Sie mir die Mail-Adresse.", ok=False)
        subject, body = (p.get("subject") or "").strip(), (p.get("body") or "").strip()
        if not body:
            d = self.brain.draft_mail(p.get("instruction") or subject or "kurze Nachricht", to)
            subject, body = subject or d["subject"], d["body"]

        def go():
            self.mail.send(to, subject, body)
            self.security.audit("MAIL_SEND", "an %s: %s" % (to, subject))
            return Result("Die Mail ist unterwegs, Sir.")
        return Result("", confirm=Confirm("Ich habe eine Mail an %s vorbereitet. Betreff: %s. Text: %s. Soll ich sie senden?"
                                          % (to, subject, body[:300]), go))

    # --------------------------------------------------------------- Telefon
    def _do_call_me(self, i):
        delay = int(i.params.get("delay_minutes", 0) or 0)
        msg = i.params.get("message") or ""
        if not self.security.allowed("PHONE_CALL"):
            return self._deny("PHONE_CALL")
        if delay > 0:
            threading.Timer(delay * 60, self._call_now, args=(msg,)).start()
            return Result("In %d Minuten rufe ich Sie an." % delay)
        self.tel.call_me(msg)
        return Result("Ich rufe Sie jetzt an, Sir.")

    def _call_now(self, msg):
        try:
            self.tel.call_me(msg)
        except TelephonyError as e:
            log.warning("Geplanter Anruf fehlgeschlagen: %s", e)

    def _do_send_sms(self, i):
        if not self.security.allowed("SMS"):
            return self._deny("SMS")
        self.tel.sms_me(i.params.get("message") or i.reply or "Nachricht von J.A.R.V.I.S")
        return Result("Die SMS ist raus, Sir.")
