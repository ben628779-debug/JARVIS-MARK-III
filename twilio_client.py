"""Anruf / SMS an die eigene Nummer ueber Twilio (REST).

Sicherheit: nur Nummern aus 'my_phone' und der Freigabeliste, Tageslimit, Audit-Log.
Zwei-Wege-Telefongespraeche (Sprache rein/raus) brauchen einen oeffentlichen Webhook-Server und
sind hier NICHT enthalten - JARVIS ruft an, spricht die Nachricht und legt auf.
"""
import datetime as _dt
import json
import re
import xml.sax.saxutils as _x

import requests

from core import logger
from core.paths import data_dir

log = logger.get("twilio")


class TelephonyError(Exception):
    pass


class Telephony:
    def __init__(self, settings, security):
        self.settings = settings
        self.security = security
        self._hist = data_dir() / "call_history.json"

    def configured(self):
        s = self.settings
        return bool(s.secret("twilio_sid") and s.secret("twilio_token") and s.get("twilio_from") and s.get("my_phone"))

    def _allowed_numbers(self):
        nums = {self._norm(self.settings.get("my_phone"))}
        for n in re.split(r"[,;\s]+", self.settings.get("allowed_numbers") or ""):
            if n:
                nums.add(self._norm(n))
        return {n for n in nums if n}

    @staticmethod
    def _norm(n):
        return re.sub(r"[^\d+]", "", n or "")

    def _history(self):
        try:
            return json.loads(self._hist.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _log(self, kind, to, ok, info=""):
        h = self._history()[-200:]
        h.append({"ts": _dt.datetime.now().isoformat(timespec="seconds"), "kind": kind, "to": to[-4:].rjust(len(to), "*"),
                  "ok": ok, "info": info[:120]})
        try:
            self._hist.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
        self.security.audit(kind.upper(), "%s ok=%s %s" % (h[-1]["to"], ok, info), ok)

    def _check(self, kind, to):
        perm = "PHONE_CALL" if kind == "call" else "SMS"
        if not self.security.allowed(perm):
            raise TelephonyError("%s ist in den Berechtigungen ausgeschaltet." % ("Anrufe" if kind == "call" else "SMS"))
        if not self.configured():
            raise TelephonyError("Telefon-Anbieter (Twilio) ist noch nicht eingerichtet.")
        if self._norm(to) not in self._allowed_numbers():
            raise TelephonyError("Diese Nummer ist nicht freigegeben.")
        today = _dt.date.today().isoformat()
        used = sum(1 for e in self._history() if e["ts"].startswith(today) and e["kind"] == "call" and e["ok"])
        if kind == "call" and used >= int(self.settings.get("call_limit_per_day") or 5):
            raise TelephonyError("Das Tageslimit fuer Anrufe ist erreicht.")

    def _post(self, path, data):
        sid, tok = self.settings.secret("twilio_sid"), self.settings.secret("twilio_token")
        try:
            r = requests.post("https://api.twilio.com/2010-04-01/Accounts/%s/%s.json" % (sid, path),
                              data=data, auth=(sid, tok), timeout=20)
        except requests.RequestException as e:
            raise TelephonyError("Telefon-Anbieter nicht erreichbar (%s)" % type(e).__name__)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", "")
            except Exception:
                msg = r.text[:100]
            raise TelephonyError("Twilio-Fehler %d: %s" % (r.status_code, msg[:120]))
        return r.json()

    def call_me(self, message: str):
        to = self.settings.get("my_phone")
        self._check("call", to)
        text = _x.escape(message or "Hier ist J.A.R.V.I.S. Sie wollten angerufen werden, Sir.")
        twiml = '<Response><Say language="de-DE" voice="Polly.Daniel">%s</Say></Response>' % text
        try:
            self._post("Calls", {"To": to, "From": self.settings.get("twilio_from"), "Twiml": twiml})
            self._log("call", to, True)
        except TelephonyError as e:
            self._log("call", to, False, str(e))
            raise

    def sms_me(self, message: str):
        to = self.settings.get("my_phone")
        self._check("sms", to)
        try:
            self._post("Messages", {"To": to, "From": self.settings.get("twilio_from"), "Body": message[:1500]})
            self._log("sms", to, True)
        except TelephonyError as e:
            self._log("sms", to, False, str(e))
            raise
