"""Audio-Diagnose: zeigt, was Windows/PortAudio wirklich melden (Geraete, Standard, Tests)."""
import threading

from core import deps, logger
from tts import audio_player as ap
from voice import microphone as mic

log = logger.get("diag")


def audio_report(settings, listener=None, play_beep=True) -> str:
    L = ["=== AUDIO DIAGNOSE ==="]
    miss = deps.missing()
    if miss:
        L.append("FEHLENDE PAKETE: %s" % ", ".join(miss))
        L.append("-> Settings: INSTALL MISSING PACKAGES  oder im Terminal (.venv aktiv):  python install_deps.py")
        L.append("")
    try:
        sd = ap._sd()
        L.append("PortAudio: %s" % sd.get_portaudio_version()[1])
        apis = sd.query_hostapis()
        dapi = ap._default_api(sd)
        L.append("Standard-Host-API: %s" % (apis[dapi]["name"] if dapi is not None else "?"))
        try:
            d_in, d_out = sd.default.device
            L.append("Windows-Standard  Mikrofon: %s | Lautsprecher: %s" % (
                sd.query_devices(d_in)["name"] if d_in is not None and d_in >= 0 else "KEINS",
                sd.query_devices(d_out)["name"] if d_out is not None and d_out >= 0 else "KEINS"))
        except Exception as e:
            L.append("Standardgeraete: nicht lesbar (%s)" % type(e).__name__)
        L.append("")
        L.append("Gefundene Geraete:")
        for i, d in enumerate(sd.query_devices()):
            L.append("  [%d] %s | %s | in=%d out=%d | %d Hz" % (
                i, d["name"], apis[d["hostapi"]]["name"], d["max_input_channels"], d["max_output_channels"],
                d["default_samplerate"]))
    except Exception as e:
        L.append("FEHLER: %s" % e)
        L.append("-> 'pip install sounddevice' pruefen / Python-Umgebung (.venv) aktiv?")
        return "\n".join(L)

    L.append("")
    L.append("Gespeichert: Mikrofon=%r  Lautsprecher=%r" % (settings.get("input_device") or "System-Standard",
                                                           settings.get("output_device") or "System-Standard"))
    ok, short, detail = mic.diagnose(settings.get("input_device"))
    L.append("Mikrofon-Test: %s - %s" % ("OK" if ok else "FEHLER", detail))
    if listener is not None:
        L.append("Hoer-Schleife: %s %s" % ("laeuft" if listener.mic_ok else "KEIN MIKROFON", listener.mic_name))
    ok2, short2, detail2 = ap.probe_output(settings.get("output_device"))
    L.append("Lautsprecher-Test: %s - %s" % ("OK" if ok2 else "FEHLER", detail2))

    try:
        import soundfile as sf
        L.append("MP3-Decoder: soundfile %s (libsndfile %s)" % (sf.__version__, sf.__libsndfile_version__))
    except Exception as e:
        L.append("MP3-Decoder soundfile: FEHLT (%s)" % type(e).__name__)
    try:
        import miniaudio  # noqa: F401
        L.append("MP3-Decoder miniaudio: vorhanden")
    except Exception:
        L.append("MP3-Decoder miniaudio: nicht installiert (ok, wenn soundfile da ist)")

    if play_beep and ok2:
        try:
            ap.AudioPlayer().play(ap.beep_wav(), int(settings.get("volume")), settings.get("output_device"))
            L.append("Testton: abgespielt - hoerst du ihn? Wenn nicht: Windows-Lautstaerkemixer / richtiges Geraet pruefen.")
        except Exception as e:
            L.append("Testton: FEHLER - %s" % e)
    if not ok:
        L.append("")
        L.append("Tipp: " + mic.PRIVACY_HINT)
    text = "\n".join(L)
    log.info("\n%s", text)
    return text


def run_async(settings, listener, callback):
    threading.Thread(target=lambda: callback(audio_report(settings, listener)), daemon=True).start()
