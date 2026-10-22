"""SQLite-Speicher fuer Erinnerungen (<home>/data/memory.db)."""
import sqlite3
import threading
import time

from core.paths import data_dir

CATEGORIES = ["preferences", "applications", "commands", "knowledge", "mail", "contacts"]


class MemoryDatabase:
    def __init__(self, path=None):
        self.path = str(path or (data_dir() / "memory.db"))
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript("""
            CREATE TABLE IF NOT EXISTS facts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                source TEXT DEFAULT 'chat', created REAL, updated REAL, uses INTEGER DEFAULT 0,
                UNIQUE(category, key));
            CREATE TABLE IF NOT EXISTS history(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, role TEXT, text TEXT);
            """)
            self._db.commit()

    def upsert_fact(self, category, key, value, source="chat"):
        category, key, value = category.strip().lower(), key.strip()[:80], value.strip()[:500]
        if not key or not value:
            return None, False
        now = time.time()
        with self._lock:
            row = self._db.execute("SELECT id, value FROM facts WHERE category=? AND key=?",
                                   (category, key)).fetchone()
            if row:
                if row["value"] != value:
                    self._db.execute("UPDATE facts SET value=?, updated=? WHERE id=?", (value, now, row["id"]))
                    self._db.commit()
                return row["id"], False
            cur = self._db.execute(
                "INSERT INTO facts(category,key,value,source,created,updated) VALUES(?,?,?,?,?,?)",
                (category, key, value, source, now, now))
            self._db.commit()
            return cur.lastrowid, True

    def delete_fact(self, fact_id):
        with self._lock:
            self._db.execute("DELETE FROM facts WHERE id=?", (fact_id,))
            self._db.commit()

    def forget_matching(self, query):
        q = "%" + query.strip().lower() + "%"
        with self._lock:
            cur = self._db.execute(
                "DELETE FROM facts WHERE lower(key) LIKE ? OR lower(value) LIKE ?", (q, q))
            self._db.commit()
            return cur.rowcount

    def all_facts(self, search=""):
        with self._lock:
            if search:
                q = "%" + search.lower() + "%"
                rows = self._db.execute(
                    "SELECT * FROM facts WHERE lower(key) LIKE ? OR lower(value) LIKE ? OR lower(category) LIKE ? "
                    "ORDER BY updated DESC", (q, q, q)).fetchall()
            else:
                rows = self._db.execute("SELECT * FROM facts ORDER BY updated DESC").fetchall()
        return [dict(r) for r in rows]

    def get_exact(self, category, key):
        with self._lock:
            row = self._db.execute("SELECT value FROM facts WHERE category=? AND lower(key)=? LIMIT 1",
                                   (category, key.lower())).fetchone()
        return row["value"] if row else None

    def find_value(self, category, key_like):
        with self._lock:
            row = self._db.execute(
                "SELECT value FROM facts WHERE category=? AND lower(key) LIKE ? LIMIT 1",
                (category, "%" + key_like.lower() + "%")).fetchone()
        return row["value"] if row else None

    def top_facts(self, n=40):
        with self._lock:
            rows = self._db.execute(
                "SELECT category,key,value FROM facts ORDER BY uses DESC, updated DESC LIMIT ?", (n,)).fetchall()
        return [dict(r) for r in rows]

    def touch(self, category, key):
        with self._lock:
            self._db.execute("UPDATE facts SET uses=uses+1 WHERE category=? AND key=?", (category, key))
            self._db.commit()

    def add_history(self, role, text):
        with self._lock:
            self._db.execute("INSERT INTO history(ts,role,text) VALUES(?,?,?)", (time.time(), role, text[:2000]))
            self._db.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 500)")
            self._db.commit()

    def history_count(self):
        with self._lock:
            return self._db.execute("SELECT COUNT(*) c FROM history").fetchone()["c"]
