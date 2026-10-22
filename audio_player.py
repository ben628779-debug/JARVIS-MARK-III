"""Audio-Ausgabe + Geraeteliste. Robust: probiert Geraete, Abtastraten und Kanalzahlen durch und
rechnet selbst um - so klappt es auch, wenn ein Geraet 24 kHz / Stereo nicht direkt kann."""
import io
import math
import threading
import wave

from core import logger

log = logger.get("audio")


class AudioError(Exception):
    pass


def _sd():
    try:
        import sounddevice as sd
        return sd
    except Exception as e:           # PortAudio fehlt o. ae.
        raise AudioError("Audio-System (sounddevice/PortAudio) nicht verfuegbar: %s" % type(e).__name__)


def _key(kind):
    return "max_input_channels" if kind == "input" else "max_output_channels"


def _default_api(sd):
    try:
        return int(sd.default.hostapi)
    except Exception:
        return None


def list_devices(kind: str):
    """Eindeutige Geraetenamen (bevorzugt die Standard-Host-API von Windows)."""
    try:
        sd = _sd()
        devs = sd.query_devices()
    except Exception:
        return []
    api, key = _default_api(sd), _key(kind)

    def collect(only_api):
        seen, out = set(), []
        for d in devs:
            if d[key] > 0 and (not only_api or d["hostapi"] == api) and d["name"] not in seen:
                seen.add(d["name"])
                out.append(d["name"])
        return out
    return (collect(True) if api is not None else []) or collect(False)


def device_indices(kind: str, name: str = ""):
    """Reihenfolge zum Ausprobieren: gewaehltes Geraet -> Systemstandard -> alle anderen."""
    sd = _sd()
    devs, api, key = sd.query_devices(), _default_api(sd), _key(kind)
    out = []
    if name:
        for pref_api in (True, False):
            for i, d in enumerate(devs):
                if d["name"] == name and d[key] > 0 and (not pref_api or d["hostapi"] == api) and i not in out:
                    out.append(i)
            if out:
                break
    out.append(None)
    for same_api in (True, False):
        for i, d in enumerate(devs):
            if d[key] > 0 and i not in out and ((d["hostapi"] == api) == same_api):
                out.append(i)
    return out[:10]


def resolve_device(name: str, kind: str):
    if not name:
        return None
    try:
        first = device_indices(kind, name)[0]
        return first
    except Exception:
        return None


def rate_candidates(sd, dev, kind, preferred):
    rates = [preferred]
    try:
        info = sd.query_devices(dev) if dev is not None else sd.query_devices(kind=kind)
        rates.append(int(info["default_samplerate"]))
    except Exception:
        pass
    rates += [48000, 44100, 32000, 22050, 16000]
    seen, out = set(), []
    for r in rates:
        if r and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def is_permission_error(e) -> bool:
    m = str(e).lower()
    return any(k in m for k in ("-9999", "access", "denied", "verweigert", "mme error 5"))


def resample(x, src, dst):
    import numpy as np
    if src == dst or len(x) == 0:
        return x
    n = max(1, int(round(len(x) * dst / float(src))))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x.astype(np.float32))


def decode_audio(data: bytes):
    """mp3/wav-Bytes -> (mono int16 numpy, samplerate). soundfile zuerst, miniaudio als Reserve."""
    import numpy as np
    errs = []
    if data[:4] == b"RIFF":                      # WAV geht immer - auch ohne Zusatzpakete
        try:
            with wave.open(io.BytesIO(data), "rb") as w:
                ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
                raw = w.readframes(w.getnframes())
            if width == 2:
                arr = np.frombuffer(raw, dtype=np.int16)
                if ch > 1:
                    arr = arr.reshape(-1, ch).astype(np.float32).mean(axis=1).astype(np.int16)
                return arr, rate
        except Exception as e:
            errs.append("wave: %s" % type(e).__name__)
    try:
        import soundfile as sf
        fmt = "MP3" if (data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)) else None
        arr, rate = sf.read(io.BytesIO(data), dtype="int16", always_2d=True, format=fmt)
        mono = arr[:, 0] if arr.shape[1] == 1 else arr.astype(np.float32).mean(axis=1).astype(np.int16)
        if len(mono):
            return mono, int(rate)
        errs.append("soundfile: leer")
    except ImportError:
        errs.append("soundfile fehlt")
    except Exception as e:
        errs.append("soundfile: %s" % type(e).__name__)
    try:
        import miniaudio
        dec = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=24000)
        return np.frombuffer(dec.samples, dtype=np.int16), 24000
    except ImportError:
        errs.append("miniaudio fehlt")
    except Exception as e:
        errs.append("miniaudio: %s" % type(e).__name__)
    raise AudioError("Audio konnte nicht dekodiert werden (%s). Bitte 'pip install soundfile' ausfuehren." % "; ".join(errs))


def beep_wav(freq=880, secs=0.4, rate=24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * secs)
        frames = bytearray()
        for i in range(n):
            env = min(1.0, i / 800.0, (n - i) / 800.0)
            v = int(9000 * env * math.sin(2 * math.pi * freq * i / rate))
            frames += v.to_bytes(2, "little", signed=True)
        w.writeframes(bytes(frames))
    return buf.getvalue()


class AudioPlayer:
    def __init__(self):
        self._stop = threading.Event()
        self._cfg = None            # zuletzt funktionierende (Geraet, Rate, Kanaele)
        self.last_device = ""

    def stop(self):
        self._stop.set()

    def play(self, data: bytes, volume=90, device_name="", on_level=None):
        """Spielt mp3/wav-Bytes ab. Blockiert bis fertig oder stop()."""
        import numpy as np
        sd = _sd()
        self._stop.clear()
        mono, src_rate = decode_audio(data)
        gain = max(0, min(100, volume)) / 100.0
        cache = {}
        state = {"pos": 0, "data": None}
        done = threading.Event()

        def make(rate, ch):
            if rate not in cache:
                cache[rate] = np.clip(resample(mono, src_rate, rate) * gain, -32768, 32767).astype(np.int16)
            return np.repeat(cache[rate][:, None], ch, axis=1)

        def cb(outdata, frames, time_info, status):
            if self._stop.is_set():
                outdata[:] = 0
                raise sd.CallbackStop
            arr, pos = state["data"], state["pos"]
            chunk = arr[pos:pos + frames]
            n = len(chunk)
            outdata[:n] = chunk
            if n < frames:
                outdata[n:] = 0
            if on_level is not None and n:
                rms = float(np.sqrt(np.mean((chunk[:, 0].astype(np.float32) / 32768.0) ** 2)))
                on_level(min(1.0, rms * 5.0))
            state["pos"] = pos + frames
            if state["pos"] >= len(arr):
                raise sd.CallbackStop

        configs = []
        if self._cfg:
            configs.append(self._cfg)
        last_err = None
        for dev in device_indices("output", device_name):
            for rate in rate_candidates(sd, dev, "output", 24000):
                for ch in (2, 1):
                    if (dev, rate, ch) not in configs:
                        configs.append((dev, rate, ch))
        stream = None
        for dev, rate, ch in configs[:60]:
            try:
                state["data"], state["pos"] = make(rate, ch), 0
                done.clear()
                s = sd.OutputStream(samplerate=rate, channels=ch, dtype="int16", device=dev,
                                    callback=cb, finished_callback=done.set)
                s.start()
                stream, self._cfg = s, (dev, rate, ch)
                try:
                    self.last_device = sd.query_devices(dev if dev is not None else sd.default.device[1])["name"]
                except Exception:
                    self.last_device = str(dev)
                log.info("Ausgabe: %s @ %d Hz, %d Kanal/Kanaele", self.last_device, rate, ch)
                break
            except Exception as e:
                last_err = e
                if is_permission_error(e) and dev is None:
                    break
        if stream is None:
            raise AudioError("Kein Lautsprecher verfuegbar (%s)" % (str(last_err)[:120] if last_err else "keine Geraete"))
        try:
            done.wait(timeout=len(state["data"]) / float(self._cfg[1]) + 5)
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            if on_level:
                on_level(0.0)


def probe_output(device_name=""):
    """-> (ok, kurztext, detail). Prueft, ob irgendein Lautsprecher geoeffnet werden kann."""
    try:
        sd = _sd()
    except AudioError as e:
        return False, "AUDIO-SYSTEM FEHLT", str(e)
    if not list_devices("output"):
        return False, "KEIN LAUTSPRECHER", "Windows meldet keinen Wiedergabe-Eintrag."
    last = None
    for dev in device_indices("output", device_name):
        for rate in rate_candidates(sd, dev, "output", 24000):
            for ch in (2, 1):
                try:
                    sd.check_output_settings(device=dev, samplerate=rate, channels=ch, dtype="int16")
                    name = sd.query_devices(dev if dev is not None else sd.default.device[1])["name"]
                    return True, "ONLINE", "Lautsprecher: %s (%d Hz, %d Kanal)" % (name, rate, ch)
                except Exception as e:
                    last = e
    return False, "FEHLER", "Kein Lautsprecher oeffnet sich: %s" % str(last)[:150]
