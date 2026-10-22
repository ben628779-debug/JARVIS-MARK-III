"""Microsoft Edge TTS (kostenlos, ohne Key) - Standardstimme de-DE-KillianNeural."""
import asyncio

from core import logger

log = logger.get("edge_tts")


class TTSError(Exception):
    pass


async def _run(text, voice, rate):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate)
    buf = bytearray()
    async for chunk in comm.stream():
        if chunk.get("type") == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def synthesize(text: str, voice="de-DE-KillianNeural", rate="+0%") -> bytes:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        raise TTSError("Paket 'edge-tts' fehlt (pip install edge-tts).")
    try:
        data = asyncio.run(asyncio.wait_for(_run(text, voice, rate), timeout=25))
    except asyncio.TimeoutError:
        raise TTSError("Edge-TTS Zeitueberschreitung (Internet?)")
    except Exception as e:
        raise TTSError("Edge-TTS Fehler: %s" % type(e).__name__)
    if not data:
        raise TTSError("Edge-TTS lieferte kein Audio (Stimme %s korrekt?)" % voice)
    return data
