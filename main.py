"""J.A.R.V.I.S - Startpunkt."""
import os
import sys
import traceback


def main():
    from core.config import LaunchState, Settings, load_env
    from core import logger
    load_env()
    settings = Settings()
    log = logger.setup_logging(bool(settings.get("debug")))

    def hook(exc_type, exc, tb):
        log.error("Unbehandelte Ausnahme:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
    sys.excepthook = hook

    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("jarvis.assistant.1")
        except Exception:
            pass

    from PySide6.QtCore import Qt
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    app = QApplication(sys.argv)
    app.setApplicationName("J.A.R.V.I.S")
    app.setQuitOnLastWindowClosed(False)

    # nur eine Instanz: zweiter Start oeffnet das vorhandene Fenster
    NAME = "JARVIS_AI_SINGLE_INSTANCE"
    sock = QLocalSocket()
    sock.connectToServer(NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(NAME)
    server = QLocalServer()
    server.listen(NAME)

    from commands.windows_actions import set_autostart
    from core.orchestrator import Orchestrator
    from gui.main_window import MainWindow
    from gui.startup_screen import StartupScreen
    from gui.styles import accent_rgb, build_qss
    from gui.tray import Tray

    app.setStyleSheet(build_qss(accent_rgb(settings.get("accent"))))
    orch = Orchestrator(settings, LaunchState())
    orch.start()
    win = MainWindow(settings, orch)

    def quit_app():
        win.quitting = True
        orch.shutdown()
        if tray:
            tray.hide()
        app.quit()

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(win.bring_to_front, orch.push_to_talk, quit_app)
        tray.show()
        win.tray = tray
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.bring_to_front()))

    def apply_settings():
        app.setStyleSheet(build_qss(accent_rgb(settings.get("accent"))))
        win.home.reactor.rebuild()
        orch.apply_settings()
        logger.setup_logging(bool(settings.get("debug")))
        try:
            set_autostart(bool(settings.get("autostart")))
        except Exception as e:
            log.warning("Autostart: %s", e)
    win.settings_page.saved.connect(apply_settings)

    def ready():
        if not settings.get("start_minimized"):
            win.show()
            win.bring_to_front()
        orch.greet()                       # 1. Start: "Guten Tag Sir." - danach: "Willkommen zurück Sir."

    if settings.get("start_minimized") and tray:
        ready()
    else:
        splash = StartupScreen(orch)
        splash.finished.connect(ready)
        splash.begin()
        app._splash = splash               # Referenz halten
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
