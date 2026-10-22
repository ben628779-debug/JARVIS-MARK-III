"""Gmail / beliebiges IMAP-Postfach (IMAP + SMTP mit App-Passwort)."""
import email
import imaplib
import re
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

from core import logger
from mail.base import MailBackend, MailError

log = logger.get("imap")

PRESETS = {
    "gmail": ("imap.gmail.com", "smtp.gmail.com"),
    "outlook": ("outlook.office365.com", "smtp-mail.outlook.com"),
}


def _dh(value):
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def _text_of(msg) -> str:
    plain, html = "", ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            txt = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if ctype == "text/plain":
            plain += txt
        elif ctype == "text/html":
            html += txt
    if plain.strip():
        return re.sub(r"\s+", " ", plain).strip()
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


class ImapMail(MailBackend):
    name = "imap"

    def __init__(self, settings):
        self.settings = settings

    def _hosts(self):
        prov = self.settings.get("mail_provider")
        imap_h, smtp_h = PRESETS.get(prov, ("", ""))
        return (self.settings.get("imap_host") or imap_h, self.settings.get("smtp_host") or smtp_h)

    def configured(self):
        return bool(self.settings.get("mail_address") and self.settings.secret("mail_password") and self._hosts()[0])

    def _connect(self):
        host = self._hosts()[0]
        try:
            c = imaplib.IMAP4_SSL(host, 993, timeout=20)
            c.login(self.settings.get("mail_address"), self.settings.secret("mail_password"))
            return c
        except imaplib.IMAP4.error as e:
            raise MailError("Anmeldung am Postfach fehlgeschlagen - App-Passwort pruefen (%s)" % type(e).__name__)
        except OSError as e:
            raise MailError("Postfach nicht erreichbar (%s)" % type(e).__name__)

    def _fetch(self, c, uids, with_preview=True):
        out = []
        for uid in uids:
            typ, data = c.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK" or not data or not isinstance(data[0], tuple):
                continue
            msg = email.message_from_bytes(data[0][1])
            name, addr = parseaddr(_dh(msg.get("From")))
            out.append({"id": uid.decode() if isinstance(uid, bytes) else str(uid),
                        "from": name or addr, "address": addr,
                        "subject": _dh(msg.get("Subject")) or "(kein Betreff)",
                        "date": msg.get("Date", ""), "preview": ""})
        return out

    def _list(self, criteria, limit):
        c = self._connect()
        try:
            c.select("INBOX", readonly=True)
            typ, data = c.uid("SEARCH", None, *criteria)
            uids = data[0].split()[-limit:][::-1] if typ == "OK" and data and data[0] else []
            mails = self._fetch(c, uids)
            for m in mails[:limit]:
                m["preview"] = self._peek_preview(c, m["id"])
            return mails
        finally:
            try:
                c.logout()
            except Exception:
                pass

    def _peek_preview(self, c, uid):
        try:
            typ, data = c.uid("FETCH", uid, "(BODY.PEEK[TEXT]<0.1500>)")
            if typ == "OK" and data and isinstance(data[0], tuple):
                raw = data[0][1].decode("utf-8", errors="replace")
                return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()[:200]
        except Exception:
            pass
        return ""

    def unread(self, limit=10):
        return self._list(["UNSEEN"], limit)

    def recent(self, limit=30):
        return self._list(["ALL"], limit)

    def search(self, query, limit=10):
        q = query.replace('"', "")
        return self._list(["OR", "FROM", '"%s"' % q, "SUBJECT", '"%s"' % q], limit)

    def body(self, mail_id):
        c = self._connect()
        try:
            c.select("INBOX", readonly=False)
            typ, data = c.uid("FETCH", mail_id, "(BODY.PEEK[])")
            if typ != "OK" or not data or not isinstance(data[0], tuple):
                raise MailError("Mail nicht gefunden")
            return _text_of(email.message_from_bytes(data[0][1]))[:8000]
        finally:
            try:
                c.logout()
            except Exception:
                pass

    def mark_read(self, mail_id):
        c = self._connect()
        try:
            c.select("INBOX")
            c.uid("STORE", mail_id, "+FLAGS", "(\\Seen)")
        finally:
            c.logout()

    def trash(self, mail_id):
        c = self._connect()
        try:
            c.select("INBOX")
            trash = self._find_trash(c)
            typ, _ = c.uid("COPY", mail_id, '"%s"' % trash)
            if typ != "OK":
                raise MailError("Papierkorb nicht gefunden")
            c.uid("STORE", mail_id, "+FLAGS", "(\\Deleted)")
            c.expunge()
        finally:
            try:
                c.logout()
            except Exception:
                pass

    @staticmethod
    def _find_trash(c):
        typ, boxes = c.list()
        for b in boxes or []:
            line = b.decode("utf-8", errors="replace")
            if "\\Trash" in line:
                m = re.search(r'"([^"]+)"\s*$', line) or re.search(r"\s(\S+)\s*$", line)
                if m:
                    return m.group(1)
        return "Trash"

    def send(self, to, subject, body):
        host = self._hosts()[1]
        msg = EmailMessage()
        msg["From"] = self.settings.get("mail_address")
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(host, 587, timeout=25) as s:
                s.starttls()
                s.login(self.settings.get("mail_address"), self.settings.secret("mail_password"))
                s.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise MailError("Senden fehlgeschlagen (%s)" % type(e).__name__)
