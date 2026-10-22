"""BRAIN: animiertes Erinnerungs-Netz mit Suche. Neue Erinnerungen erscheinen als neue Nodes."""
import math
import time

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from gui.styles import accent_rgb
from memory.memory_database import CATEGORIES

CAT_LABELS = {"preferences": "USER PREFERENCES", "applications": "APPLICATIONS", "commands": "COMMANDS",
              "knowledge": "KNOWLEDGE", "mail": "MAIL RULES", "contacts": "CONTACTS", "conversations": "CONVERSATIONS"}
ALL_CATS = CATEGORIES + ["conversations"]


class BrainCanvas(QWidget):
    picked = Signal(int)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.facts = []
        self.convo_count = 0
        self.match = None            # None = alle, sonst Set von IDs
        self.selected = None
        self.born = {}
        self._hit = []               # (x, y, r, fact_id)
        self._clock = QElapsedTimer()
        self._clock.start()
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    def showEvent(self, e):
        self.timer.start(33)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def set_data(self, facts, convo_count, match):
        now = self._clock.elapsed() / 1000.0
        for f in facts:
            self.born.setdefault(f["id"], now)
        self.facts, self.convo_count, self.match = facts, convo_count, match

    def mousePressEvent(self, e):
        for x, y, r, fid in self._hit:
            if (e.position().x() - x) ** 2 + (e.position().y() - y) ** 2 <= (r + 4) ** 2:
                self.selected = fid
                self.picked.emit(fid)
                return

    def paintEvent(self, ev):
        t = self._clock.elapsed() / 1000.0
        w, h = self.width(), self.height()
        rgb = accent_rgb(self.settings.get("accent"))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(4, 6, 10))
        cx, cy = w / 2, h / 2
        Rc = min(w, h) * 0.30
        self._hit = []

        def col(a):
            return QColor(rgb[0], rgb[1], rgb[2], max(0, min(255, int(a))))

        # Zentrum
        g = QRadialGradient(QPointF(cx, cy), 60)
        g.setColorAt(0, col(140))
        g.setColorAt(1, col(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), 60 + 4 * math.sin(t * 1.5), 60 + 4 * math.sin(t * 1.5))
        p.setBrush(col(255))
        p.drawEllipse(QPointF(cx, cy), 9, 9)
        f = QFont("Segoe UI", 9)
        f.setPixelSize(11)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(f)
        p.setPen(col(230))
        p.drawText(QRectF(cx - 80, cy + 14, 160, 18), Qt.AlignmentFlag.AlignCenter, "MEMORY")

        by_cat = {c: [] for c in ALL_CATS}
        for fct in self.facts:
            by_cat.setdefault(fct["category"], []).append(fct)

        n = len(ALL_CATS)
        for ci, cat in enumerate(ALL_CATS):
            ang = -math.pi / 2 + ci * 2 * math.pi / n + 0.12 * math.sin(t * 0.3 + ci)
            kx = cx + math.cos(ang) * Rc
            ky = cy + math.sin(ang) * Rc * 0.82
            p.setPen(QPen(col(60), 1))
            p.drawLine(QPointF(cx, cy), QPointF(kx, ky))
            items = by_cat.get(cat, [])
            for i, fct in enumerate(items):
                age = t - self.born.get(fct["id"], 0)
                pop = min(1.0, age / 0.6)
                a = i * 2.39996 + ci
                rr = (34 + 11 * math.sqrt(i + 1)) * pop
                fx = kx + math.cos(a + t * 0.15) * rr + 3 * math.sin(t * 1.1 + i)
                fy = ky + math.sin(a + t * 0.15) * rr + 3 * math.cos(t * 0.9 + i)
                dim = self.match is not None and fct["id"] not in self.match
                alpha = 40 if dim else 210
                p.setPen(QPen(col(alpha * 0.35), 1))
                p.drawLine(QPointF(kx, ky), QPointF(fx, fy))
                radius = 4.5 + (3 if age < 1.5 else 0) * (1 - age / 1.5 if age < 1.5 else 0)
                is_sel = self.selected == fct["id"]
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col(255 if is_sel else alpha))
                p.drawEllipse(QPointF(fx, fy), radius + (2 if is_sel else 0), radius + (2 if is_sel else 0))
                if age < 2.0:                           # Einblend-Ring bei neuen Erinnerungen
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(col(200 * (1 - age / 2.0)), 1.5))
                    p.drawEllipse(QPointF(fx, fy), 6 + age * 18, 6 + age * 18)
                if not dim and (is_sel or (self.match is not None)):
                    p.setPen(col(230))
                    f2 = QFont("Segoe UI", 9)
                    f2.setPixelSize(11)
                    p.setFont(f2)
                    p.drawText(QPointF(fx + 9, fy + 4), fct["key"][:28])
                self._hit.append((fx, fy, radius, fct["id"]))
            cnt = self.convo_count if cat == "conversations" else len(items)
            p.setBrush(col(255))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(kx, ky), 7, 7)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(col(120), 1))
            p.drawEllipse(QPointF(kx, ky), 12 + 2 * math.sin(t * 2 + ci), 12 + 2 * math.sin(t * 2 + ci))
            p.setFont(f)
            p.setPen(col(220))
            p.drawText(QRectF(kx - 90, ky - 36, 180, 16), Qt.AlignmentFlag.AlignCenter, "%s (%d)" % (CAT_LABELS[cat], cnt))
        p.end()


class BrainPage(QWidget):
    def __init__(self, settings, memory):
        super().__init__()
        self.memory = memory
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Erinnerungen durchsuchen ...")
        self.search.textChanged.connect(self.refresh)
        self.canvas = BrainCanvas(settings)
        self.canvas.picked.connect(self._pick)
        left.addWidget(self.search)
        left.addWidget(self.canvas, 1)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(300)
        self.list.currentItemChanged.connect(self._item)
        self.detail = QLabel("Waehle einen Node oder Eintrag.")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("hint")
        self.btn = QPushButton("VERGESSEN")
        self.btn.clicked.connect(self._forget)
        right.addWidget(self.list, 1)
        right.addWidget(self.detail)
        right.addWidget(self.btn)
        lay.addLayout(right)
        self._current = None
        self.refresh()

    def refresh(self, *_):
        q = self.search.text().strip()
        facts = self.memory.db.all_facts()
        match = None
        if q:
            ids = {f["id"] for f in self.memory.db.all_facts(q)}
            match = ids
        self.canvas.set_data(facts, self.memory.db.history_count(), match)
        self.list.blockSignals(True)
        self.list.clear()
        for f in (self.memory.db.all_facts(q) if q else facts):
            it = QListWidgetItem("%s  \u00b7  %s" % (f["category"].upper(), f["key"]))
            it.setData(Qt.ItemDataRole.UserRole, f)
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _pick(self, fid):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole)["id"] == fid:
                self.list.setCurrentRow(i)
                return

    def _item(self, cur, _prev):
        if cur is None:
            self._current = None
            return
        f = cur.data(Qt.ItemDataRole.UserRole)
        self._current = f
        self.canvas.selected = f["id"]
        self.detail.setText("%s\n\n%s\n\nQuelle: %s" % (f["key"], f["value"], f.get("source", "")))

    def _forget(self):
        if self._current:
            self.memory.db.delete_fact(self._current["id"])
            self._current = None
            self.canvas.selected = None
            self.detail.setText("Vergessen.")
            self.refresh()
