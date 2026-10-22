"""Outlook.com / Microsoft 365 ueber Microsoft Graph (OAuth).

Microsoft hat Passwort-/App-Passwort-Login (IMAP/SMTP) fuer Outlook abgeschaltet.
Darum: einmalig im Browser anmelden ("Mit Outlook verbinden" in den Einstellungen).
Benoetigt eine kostenlose Azure-App-Registrierung (Client-ID) - siehe README.
"""
import requests

from core import logger
from core.paths import data_dir
from mail.base import MailBackend, MailError

log = logger.get("graph")

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.ReadWrite", "Mail.Send"]
AUTHORITY = "https://login.microsoftonline.com/common"


class GraphMail(MailBackend):
    name = "graph"

    def __init__(self, settings):
        self.settings = settings
        self._app = None
        self._cache = None
        self._cache_path = data_dir() / "msal_cache.bin"

    def _msal(self):
        if self._app is not None:
            return self._app
        try:
            import msal
        except ImportError:
            raise MailError("Paket 'msal' fehlt (pip install msal).")
        cid = self.settings.get("azure_client_id")
        if not cid:
            raise MailError("Keine Azure Client-ID in den Einstellungen.")
        self._cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            try:
                self._cache.deserialize(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        self._app = msal.PublicClientApplication(cid, authority=AUTHORITY, token_cache=self._cache)
        return self._app

    def _save_cache(self):
        if self._cache is not None and self._cache.has_state_changed:
            try:
                self._cache_path.write_text(self._cache.serialize(), encoding="utf-8")
            except OSError:
                pass

    def configured(self):
        return bool(self.settings.get("azure_client_id"))

    def connect_interactive(self):
        """Oeffnet den Browser zur Microsoft-Anmeldung. Blockiert bis fertig (in Worker-Thread aufrufen)."""
        app = self._msal()
        res = app.acquire_token_interactive(scopes=SCOPES, prompt="select_account")
        self._save_cache()
        if "access_token" not in res:
            raise MailError("Anmeldung fehlgeschlagen: %s" % res.get("error_description", "unbekannt")[:150])
        return True

    def _token(self):
        app = self._msal()
        accounts = app.get_accounts()
        if not accounts:
            raise MailError("Outlook ist noch nicht verbunden (Einstellungen -> Mit Outlook verbinden).")
        res = app.acquire_token_silent(SCOPES, account=accounts[0])
        self._save_cache()
        if not res or "access_token" not in res:
            raise MailError("Outlook-Anmeldung abgelaufen - bitte erneut verbinden.")
        return res["access_token"]

    def _req(self, method, path, **kw):
        headers = {"Authorization": "Bearer " + self._token()}
        headers.update(kw.pop("headers", {}))
        try:
            r = requests.request(method, GRAPH + path, headers=headers, timeout=25, **kw)
        except requests.RequestException as e:
            raise MailError("Outlook nicht erreichbar (%s)" % type(e).__name__)
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except Exception:
                msg = r.text[:120]
            raise MailError("Outlook-Fehler %d: %s" % (r.status_code, msg[:120]))
        return r.json() if r.content else {}

    @staticmethod
    def _norm(m):
        sender = (m.get("from") or {}).get("emailAddress", {})
        return {"id": m["id"], "from": sender.get("name") or sender.get("address", "?"),
                "address": sender.get("address", ""), "subject": m.get("subject") or "(kein Betreff)",
                "date": m.get("receivedDateTime", ""), "preview": (m.get("bodyPreview") or "")[:200]}

    SEL = "id,subject,from,receivedDateTime,bodyPreview,isRead"

    def unread(self, limit=10):
        d = self._req("GET", "/me/mailFolders/inbox/messages", params={
            "$filter": "isRead eq false", "$top": limit, "$select": self.SEL})
        return [self._norm(m) for m in d.get("value", [])]

    def recent(self, limit=30):
        d = self._req("GET", "/me/mailFolders/inbox/messages", params={
            "$top": limit, "$select": self.SEL, "$orderby": "receivedDateTime desc"})
        return [self._norm(m) for m in d.get("value", [])]

    def search(self, query, limit=10):
        d = self._req("GET", "/me/messages", params={
            "$search": '"%s"' % query.replace('"', ""), "$top": limit, "$select": self.SEL},
            headers={"ConsistencyLevel": "eventual"})
        return [self._norm(m) for m in d.get("value", [])]

    def body(self, mail_id):
        d = self._req("GET", "/me/messages/" + mail_id, params={"$select": "body"},
                      headers={"Prefer": 'outlook.body-content-type="text"'})
        return (d.get("body", {}).get("content") or "")[:8000]

    def mark_read(self, mail_id):
        self._req("PATCH", "/me/messages/" + mail_id, json={"isRead": True})

    def trash(self, mail_id):
        self._req("POST", "/me/messages/%s/move" % mail_id, json={"destinationId": "deleteditems"})

    def send(self, to, subject, body):
        self._req("POST", "/me/sendMail", json={"message": {
            "subject": subject, "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}]}, "saveToSentItems": True})
