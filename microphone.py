"""Mikrofon-Zugriff. Probiert Geraete / Abtastraten / Kanaele durch und rechnet auf 16 kHz mono um."""
import queue

from core import logger
from tts.audio_player import (AudioError, device_indices, is_permission_error, list_devices, rate_candidates,
                              resolve_device, _sd)

log = logger.get("mic")

RATE = 16000
BLOCK = 480            # 30 ms bei 16 kHz

PRIVACY_HINT = ("Windows: Einstellungen -> Datenschutz & Sicherheit -> Mikrofon -> "
                "'Zugriff auf Mikrofon' AN und 'Desktop-Apps den Zugriff erlauben' AN.")


class MicError(Exception):
    pass


def input_devices():
    return list_devices("input")


def _to_16k(x, rate):
    import numpy as np
    x = x.astype(np.float32)
    if rate != RATE:
        if rate % RATE == 0:
            k = rate // RATE
            n = (len(x) // k) * k
            x = x[:n].reshape(-1, k).mean(axis=1)
        else:
            n = max(1, int(round(len(x) * RATE / float(rate))))
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    if len(x) < BLOCK:
        x = np.pad(x, (0, BLOCK - len(x)))
    return x[:BLOCK].astype(np.int16)


def _friendly(e):
    if e is not None and is_permission_error(e):
        return "Ich kann momentan nicht auf das Mikrofon zugreifen. " + PRIVACY_HINT
    return "Ich kann momentan nicht auf das Mikrofon zugreifen (%s)." % (str(e)[:100] if e else "kein Geraet")


def diagnose(device_name=""):
    """-> (ok, kurztext, detail). Oeffnet das Mikrofon kurz wirklich."""
    mic = MicStream(device_name)
    try:
        mic.open()
        return True, "ONLINE", "Mikrofon: %s (%d Hz)" % (mic.opened_name, mic.rate)
    except MicError as e:
        short = "ZUGRIFF VERWEIGERT" if "Datenschutz" in str(e) else ("KEIN MIKROFON" if not input_devices() else "FEHLER")
        return False, short, str(e)
    finally:
        mic.close()


class MicStream:
    def __init__(self, device_name=""):
        self.device_name = device_name
        self.q = queue.Queue(maxsize=200)
        self._stream = None
        self.opened_name = ""
        self.rate = 0

    def _callback(self, rate, ch):
        def cb(indata, frames, t, status):
            x = indata[:, 0] if ch == 1 else indata.mean(axis=1)
            try:
                self.q.put_nowait(_to_16k(x, rate))
            except queue.Full:
                pass
        return cb

    def open(self):
        try:
            sd = _sd()
        except AudioError as e:
            raise MicError(str(e))
        if not list_devices("input"):
            raise MicError("Windows meldet kein Mikrofon. Mikrofon anschliessen/aktivieren. " + PRIVACY_HINT)
        last = None
        for dev in device_indices("input", self.device_name):
            for rate in rate_candidates(sd, dev, "input", RATE):
                for ch in (1, 2):
                    try:
                        s = sd.InputStream(samplerate=rate, channels=ch, dtype="int16",
                                           blocksize=int(rate * 0.03), device=dev, callback=self._callback(rate, ch))
                        s.start()
                        self._stream, self.rate = s, rate
                        try:
                            self.opened_name = sd.query_devices(dev if dev is not None else sd.default.device[0])["name"]
                        except Exception:
                            self.opened_name = str(dev)
                        log.info("Mikrofon: %s @ %d Hz, %d Kanal/Kanaele", self.opened_name, rate, ch)
                        return
                    except Exception as e:
                        last = e
                        if is_permission_error(e):
                            raise MicError(_friendly(e))
        raise MicError(_friendly(last))

    def read(self, timeout=1.0):
        return self.q.get(timeout=timeout)

    def drain(self):
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    def close(self):
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
