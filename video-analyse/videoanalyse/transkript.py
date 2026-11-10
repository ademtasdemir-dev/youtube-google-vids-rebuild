"""Gesprochenes -> Text mit Zeitstempeln (lokal mit faster-whisper, keine Cloud, keine Kosten)."""
import re

import numpy as np

SATZENDE = re.compile(r"[.!?…]$")


def transkribieren(audio16k: np.ndarray, modell: str = "small", sprache: str | None = "de", log=print) -> tuple[list[dict], str]:
    """Gibt (Wörter, erkannte Sprache) zurück. Wort = {w, s, e}."""
    from faster_whisper import WhisperModel
    log(f"Lade Spracherkennung ({modell}) …")
    m = WhisperModel(modell, device="cpu", compute_type="int8")
    segmente, info = m.transcribe(audio16k, language=sprache or None, word_timestamps=True, vad_filter=True,
                                  vad_parameters={"min_silence_duration_ms": 400})
    dauer = max(1e-6, len(audio16k) / 16000)
    woerter = []
    for s in segmente:
        for w in s.words or []:
            woerter.append({"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)})
        log(f"Transkript {int(min(1, s.end / dauer) * 100)} %", prozent=min(1, s.end / dauer))
    return woerter, info.language


def zeilen_bilden(woerter: list[dict], max_dauer: float = 12.0, pause: float = 0.7) -> list[dict]:
    """Fasst Wörter zu gut lesbaren Zeilen zusammen: Schnitt bei Satzende, langer Pause oder nach max_dauer."""
    zeilen, akt = [], []
    for i, w in enumerate(woerter):
        if akt:
            luecke = w["s"] - akt[-1]["e"]
            zu_lang = w["e"] - akt[0]["s"] > max_dauer
            if luecke > pause or zu_lang or (SATZENDE.search(akt[-1]["w"]) and w["s"] - akt[0]["s"] > 2.5):
                zeilen.append(akt); akt = []
        akt.append(w)
    if akt:
        zeilen.append(akt)
    return [{"start": z[0]["s"], "ende": z[-1]["e"], "text": verbinden(z),
             "woerter": len(z), "sprecher": "Sprecher 1", "_w": z} for z in zeilen]


def verbinden(woerter: list[dict]) -> str:
    """Wörter zu Text: kein Leerzeichen vor Satzzeichen oder vor Zahlenteilen wie '.168' / ',5'."""
    text = ""
    for w in woerter:
        t = w["w"]
        if text and not re.match(r"^[.,!?;:%)…]|^[.,]\d", t) and not text.endswith(("(", "„")):
            text += " "
        text += t
    return text


def aus_untertitel(vtt: str) -> list[dict]:
    """YouTube-Untertitel (.vtt) als Ersatz, falls keine eigene Erkennung läuft."""
    from .zeit import sekunden
    zeilen, gesehen = [], set()
    bloecke = re.split(r"\n\s*\n", vtt.replace("\r", ""))
    for b in bloecke:
        m = re.search(r"([\d:.]+)\s+-->\s+([\d:.]+)", b)
        if not m:
            continue
        text = " ".join(l for l in b.split("\n")[1:] if "-->" not in l)
        text = re.sub(r"<[^>]+>", "", text).strip()
        if not text or text in gesehen:
            continue
        gesehen.add(text)
        zeilen.append({"start": sekunden(m.group(1)), "ende": sekunden(m.group(2)), "text": text,
                       "woerter": len(text.split()), "sprecher": "Sprecher 1"})
    return zeilen
