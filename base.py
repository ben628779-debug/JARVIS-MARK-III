"""Gemeinsame Mail-Schnittstelle."""


class MailError(Exception):
    pass


class MailBackend:
    name = "base"

    def configured(self) -> bool:
        raise NotImplementedError

    def unread(self, limit=10) -> list:
        """-> [{id, from, subject, preview, date}]"""
        raise NotImplementedError

    def recent(self, limit=30) -> list:
        raise NotImplementedError

    def search(self, query: str, limit=10) -> list:
        raise NotImplementedError

    def body(self, mail_id: str) -> str:
        raise NotImplementedError

    def mark_read(self, mail_id: str) -> None:
        raise NotImplementedError

    def send(self, to: str, subject: str, body: str) -> None:
        raise NotImplementedError

    def trash(self, mail_id: str) -> None:
        raise NotImplementedError
