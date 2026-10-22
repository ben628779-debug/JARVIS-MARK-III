"""Letzte Rueckfalloption: Windows-Offline-Stimme (SAPI) ueber pyttsx3."""
import os
import tempfile

from tts.edge_tts_engine import TTSError


def synthesize(text: str) -> bytes:
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        import pyttsx3
        engine = pyttsx3.init()
        for v in engine.getProperty("voices"):
            blob = (v.id + " " + v.name).lower()
            if "de-de" in blob or "german" in blob or "hedda" in blob or "katja" in blob:
                engine.setProperty("voice", v.id)
                break
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            engine.save_to_file(text, path)
            engine.runAndWait()
            with open(path, "rb") as f:
                data = f.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if not data:
            raise TTSError("Offline-Stimme lieferte kein Audio")
        return data
    except TTSError:
        raise
    except Exception as e:
        raise TTSError("Offline-Stimme nicht verfuegbar (%s)" % type(e).__name__)
