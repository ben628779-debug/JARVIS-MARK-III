"""Lernen & Erinnern. Haelt Fakten ueber den Nutzer und meldet neue Erinnerungen an die GUI."""
import threading

from core import logger
from memory.memory_database import MemoryDatabase

log = logger.get("memory")


class MemoryManager:
    def __init__(self, settings, db=None):
        self.settings = settings
        self.db = db or MemoryDatabase()
        self._listeners = []          # callbacks(fact_id, category, key, value, is_new)
        self._lock = threading.Lock()

    def on_new(self, cb):
        self._listeners.append(cb)

    def remember(self, category, key, value, source="chat"):
        fid, is_new = self.db.upsert_fact(category, key, value, source)
        if fid is None:
            return False
        log.info("Erinnerung %s: [%s] %s", "neu" if is_new else "aktualisiert", category, key)
        for cb in list(self._listeners):
            try:
                cb(fid, category, key, value, is_new)
            except Exception:
                log.exception("memory listener")
        return True

    def forget(self, query):
        n = self.db.forget_matching(query)
        for cb in list(self._listeners):
            try:
                cb(None, "", "", "", False)
            except Exception:
                pass
        return n

    def context_block(self):
        facts = self.db.top_facts(40)
        if not facts:
            return "(noch keine gespeicherten Erinnerungen)"
        return "\n".join("- [%s] %s: %s" % (f["category"], f["key"], f["value"]) for f in facts)

    def log_exchange(self, user_text, reply):
        self.db.add_history("user", user_text)
        self.db.add_history("jarvis", reply)

    def learn_app(self, name, path):
        self.remember("applications", name, path, source="launcher")
