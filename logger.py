"""Logging nach <home>/logs/jarvis.log. API-Keys werden maskiert."""
import logging
import logging.handlers

from core.paths import log_dir

_SECRETS: set = set()


def register_secret(value: str) -> None:
    if value and len(value) >= 6:
        _SECRETS.add(value)


class _MaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for s in _SECRETS:
                if s in msg:
                    msg = msg.replace(s, "***")
            record.msg, record.args = msg, ()
        except Exception:
            pass
        return True


def setup_logging(debug: bool = False) -> logging.Logger:
    root = logging.getLogger("jarvis")
    if root.handlers:
        root.setLevel(logging.DEBUG if debug else logging.INFO)
        return root
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        log_dir() / "jarvis.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(_MaskFilter())
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.addFilter(_MaskFilter())
    root.addHandler(sh)
    return root


def get(name: str) -> logging.Logger:
    return logging.getLogger("jarvis." + name)
