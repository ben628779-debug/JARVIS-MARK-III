"""Einheitlicher Zugriff auf das Postfach (Outlook via Graph, Gmail/IMAP)."""
from core import logger
from mail.base import MailError
from mail.graph_mail import GraphMail
from mail.imap_mail import ImapMail

log = logger.get("mail")


class MailManager:
    def __init__(self, settings):
        self.settings = settings
        self._graph = GraphMail(settings)
        self._imap = ImapMail(settings)
        self.last_list = []           # zuletzt vorgelesene Liste, damit "die erste Mail" funktioniert

    @property
    def backend(self):
        return self._graph if self.settings.get("mail_provider") == "outlook" else self._imap

    def configured(self):
        return self.backend.configured()

    def connect_outlook(self):
        return self._graph.connect_interactive()

    def unread(self, limit=8):
        self.last_list = self.backend.unread(limit)
        return self.last_list

    def recent(self, limit=30):
        return self.backend.recent(limit)

    def search(self, q, limit=8):
        self.last_list = self.backend.search(q, limit)
        return self.last_list

    def by_index(self, index):
        if not self.last_list:
            self.last_list = self.backend.unread(8)
        if not self.last_list:
            raise MailError("Es gibt keine Mails in der Liste.")
        i = index - 1 if index > 0 else len(self.last_list) + index
        if i < 0 or i >= len(self.last_list):
            raise MailError("Diese Mail gibt es nicht - ich habe %d in der Liste." % len(self.last_list))
        return self.last_list[i]

    def body(self, mail):
        return self.backend.body(mail["id"])

    def mark_read(self, mail):
        self.backend.mark_read(mail["id"])

    def trash(self, mail):
        self.backend.trash(mail["id"])

    def send(self, to, subject, body):
        self.backend.send(to, subject, body)

    def find_address(self, name):
        """Name -> Adresse ueber bisherige Absender."""
        try:
            for m in self.backend.search(name, 5):
                if m.get("address") and name.lower() in (m["from"] + m["address"]).lower():
                    return m["address"]
        except MailError:
            pass
        return None
