"""Tray-Symbol: orange-blauer Kreis. Klick oeffnet die GUI - J.A.R.V.I.S laeuft im Hintergrund weiter."""
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QRadialGradient, QPen, QBrush
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from core.paths import resource_path


def make_icon() -> QIcon:
    pm = QPixmap(resource_path("assets/jarvis_tray.png"))
    if not pm.isNull():
        return QIcon(pm)
    pm = QPixmap(64, 64)                       # Fallback: selbst zeichnen
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(255, 150, 30), 5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(32, 32), 26, 26)
    g = QRadialGradient(QPointF(32, 32), 14)
    g.setColorAt(0, QColor(200, 235, 255))
    g.setColorAt(1, QColor(30, 140, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(32, 32), 14, 14)
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, on_open, on_listen, on_quit, parent=None):
        super().__init__(make_icon(), parent)
        self.setToolTip("J.A.R.V.I.S - laeuft im Hintergrund (Klick zum Oeffnen)")
        menu = QMenu()
        a_open = QAction("J.A.R.V.I.S oeffnen", menu)
        a_open.triggered.connect(on_open)
        a_listen = QAction("Zuhoeren", menu)
        a_listen.triggered.connect(on_listen)
        a_quit = QAction("Beenden", menu)
        a_quit.triggered.connect(on_quit)
        menu.addAction(a_open)
        menu.addAction(a_listen)
        menu.addSeparator()
        menu.addAction(a_quit)
        self._menu = menu
        self.setContextMenu(menu)
        self.activated.connect(lambda reason: on_open() if reason in (
            QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
