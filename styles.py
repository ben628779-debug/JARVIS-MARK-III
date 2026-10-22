"""Farben & Stylesheet."""

ACCENTS = {
    "ice": (205, 230, 255),
    "blue": (70, 160, 255),
    "cyan": (0, 229, 255),
    "green": (70, 255, 150),
    "orange": (255, 150, 50),
    "red": (255, 80, 80),
}

BG = "#04060a"


def accent_rgb(name: str):
    return ACCENTS.get(name, ACCENTS["ice"])


def build_qss(accent=(205, 230, 255)):
    a = "rgb(%d,%d,%d)" % accent
    a_dim = "rgba(%d,%d,%d,70)" % accent
    a_faint = "rgba(%d,%d,%d,28)" % accent
    return """
    QWidget { background: %(bg)s; color: #d7e6f2; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }
    QLabel { background: transparent; }
    QLabel#section { color: %(a)s; font-size: 11px; letter-spacing: 4px; padding-top: 14px; }
    QLabel#hint { color: #7d8b97; font-size: 11px; }
    QPushButton { background: %(faint)s; border: 1px solid %(dim)s; border-radius: 3px; padding: 7px 16px;
                  color: #e8f4ff; letter-spacing: 2px; }
    QPushButton:hover { background: %(dim)s; border-color: %(a)s; }
    QPushButton:pressed { background: %(a)s; color: #02060a; }
    QPushButton#nav { border: none; border-bottom: 2px solid transparent; background: transparent; padding: 10px 22px;
                      font-size: 13px; letter-spacing: 5px; color: #8fa3b3; }
    QPushButton#nav:hover { color: #ffffff; }
    QPushButton#nav:checked { color: #ffffff; border-bottom: 2px solid %(a)s; }
    QPushButton#estop { background: rgba(255,60,60,40); border: 1px solid rgba(255,90,90,160); color: #ffb3b3; }
    QPushButton#estop:checked { background: rgb(210,40,40); color: white; }
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit { background: rgba(255,255,255,8); border: 1px solid %(dim)s;
                      border-radius: 3px; padding: 6px 8px; selection-background-color: %(a)s; selection-color: #000; }
    QLineEdit:focus, QComboBox:focus { border-color: %(a)s; }
    QComboBox QAbstractItemView { background: #0a1016; border: 1px solid %(dim)s; selection-background-color: %(dim)s; }
    QCheckBox { spacing: 8px; }
    QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid %(dim)s; background: transparent; border-radius: 2px; }
    QCheckBox::indicator:checked { background: %(a)s; }
    QSlider::groove:horizontal { height: 3px; background: %(dim)s; }
    QSlider::handle:horizontal { width: 14px; margin: -6px 0; background: %(a)s; border-radius: 7px; }
    QScrollArea { border: none; }
    QScrollBar:vertical { width: 8px; background: transparent; }
    QScrollBar::handle:vertical { background: %(dim)s; border-radius: 4px; min-height: 30px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QListWidget { background: transparent; border: 1px solid %(dim)s; }
    QListWidget::item:selected { background: %(dim)s; }
    QToolTip { background: #0a1016; color: #fff; border: 1px solid %(a)s; }
    """ % {"bg": BG, "a": a, "dim": a_dim, "faint": a_faint}
