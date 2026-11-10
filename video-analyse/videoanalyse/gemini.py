"""Optionale KI-Auswertung mit Google Gemini (kostenloser API-Schlüssel aus Google AI Studio).

Bekommt: Metadaten, Transkript mit Zeitstempeln und Sprechern, Szenenliste und Standbilder.
Liefert: ausführliche Zusammenfassung, Kapitel mit Inhalt und Bildbeschreibung, Beschreibung jedes Standbilds,
Analyse von Darstellung und Dramaturgie.
"""
import base64
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from .zeit import hms

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modell}:generateContent"
MAX_BILDER = 30
STANDARD_MODELL = "gemini-3-flash-preview"
ERSATZ_MODELLE = ["gemini-2.5-flash"]  # falls das gewählte Modell (noch/nicht mehr) nicht verfügbar ist

AUFGABE = """Du analysierst ein Video vollständig und sehr genau, auf Deutsch. Du bekommst Metadaten, das Transkript
mit Zeitstempeln und Sprechern, eine Szenenliste und Standbilder (je Bild steht Nummer und Zeit davor).
Beschreibe nur, was wirklich im Material steckt. Erfinde nichts. Wenn etwas unklar ist, sag das.
Antworte ausschließlich mit JSON in genau diesem Aufbau:
{
 "zusammenfassung": {"kurz": "2-3 Sätze", "ausfuehrlich": "mehrere Absätze, was im Video passiert und gesagt wird",
                      "kernaussagen": ["..."], "zielgruppe": "...", "thema": "..."},
 "kapitel": [{"start": Sekunden als Zahl, "titel": "kurzer Kapiteltitel", "phase": "Einstieg|Hauptteil|Abschluss|Hook|Übergang|Call-to-Action",
              "inhalt": "was in dem Abschnitt gesagt/gezeigt wird", "visuell": "welche Bilder/Folien/Einblendungen zu sehen sind"}],
 "bilder": [{"nr": Bildnummer, "bildtyp": "z.B. Folie, Diagramm, Person vor Kamera, Bildschirmaufnahme, B-Roll, Animation, Text-Einblendung",
             "beschreibung": "was genau zu sehen ist", "text_im_bild": "lesbarer Text im Bild, sonst leer"}],
 "darstellung": {"stil": "...", "grafiken_und_einblendungen": "...", "kamera_und_licht": "...", "sprecher_und_vortrag": "...",
                 "tempo_und_schnitt": "...", "ton_und_musik": "..."},
 "dramaturgie": {"einstieg": "...", "aufbau": "...", "spannung_und_wiederholung": "...", "abschluss": "..."},
 "sprecher_rollen": [{"sprecher": "Sprecher 1", "rolle": "z.B. Moderator, Gast, Erzähler", "merkmale": "..."}],
 "titel_vorschlaege": ["..."],
 "verbesserungen": ["konkrete Hinweise, was man am Video besser machen könnte"]
}
Kapitel: nutze die vorgeschlagenen Kapitelgrenzen als Hilfe, verbessere sie, wenn der Inhalt es nahelegt. Erstes Kapitel bei 0."""


def _bild_teil(pfad: Path) -> dict:
    im = Image.open(pfad).convert("RGB")
    im.thumbnail((640, 640))
    b = io.BytesIO(); im.save(b, "JPEG", quality=80)
    return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}


def anfrage_bauen(info: dict, zeilen: list[dict], szenen: list[dict], kapitel: list[dict], bilder_ordner: Path,
                  youtube_url: str | None = None) -> dict:
    """youtube_url: wenn gesetzt, schaut sich Gemini zusätzlich das ganze Video an (Bewegung, Schnitte, Einblendungen).
    Zählt beim kostenlosen Schlüssel zum Tageskontingent (8 Stunden YouTube-Video pro Tag)."""
    meta = {k: info.get(k) for k in ("title", "uploader", "duration", "description", "tags", "upload_date")}
    transkript = "\n".join(f"[{hms(z['start'])}] {z['sprecher']}: {z['text']}" for z in zeilen)
    szen = "\n".join(f"Bild {s['nr']} bei {hms(s['bild_zeit'])} (Szene {hms(s['start'])}–{hms(s['ende'])}), Schätzung: {s['bildart']}" for s in szenen)
    vorschlag = "\n".join(f"{hms(k['start'])} {k['titel']}" for k in kapitel)
    teile = [{"text": AUFGABE},
             {"text": "METADATEN:\n" + json.dumps(meta, ensure_ascii=False)},
             {"text": "TRANSKRIPT:\n" + (transkript or "(kein gesprochener Text erkannt)")},
             {"text": "SZENEN:\n" + szen},
             {"text": "VORGESCHLAGENE KAPITEL:\n" + vorschlag}]
    if youtube_url:
        teile.insert(1, {"file_data": {"file_uri": youtube_url}})
        teile.insert(1, {"text": "Das komplette Video ist beigefügt. Beschreibe Bilder, Einblendungen und Schnitte anhand des Videos."})
    max_b = 12 if youtube_url else MAX_BILDER
    schritt = max(1, -(-len(szenen) // max_b))
    for s in szenen[::schritt][:max_b]:
        teile.append({"text": f"Bild {s['nr']} ({hms(s['bild_zeit'])}):"})
        teile.append(_bild_teil(bilder_ordner / s["bild"]))
    return {"contents": [{"role": "user", "parts": teile}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}}


def auswerten(schluessel: str, anfrage: dict, modell: str = STANDARD_MODELL, timeout: int = 600, log=None) -> dict:
    """Probiert das gewählte Modell, bei „Modell nicht gefunden“ automatisch die Ersatzmodelle."""
    kandidaten = [modell or STANDARD_MODELL] + [m for m in ERSATZ_MODELLE if m != modell]
    for i, m in enumerate(kandidaten):
        try:
            return _auswerten_einmal(schluessel, anfrage, m, timeout)
        except ModellFehlt:
            if i + 1 == len(kandidaten):
                raise RuntimeError(f"Kein Gemini-Modell verfügbar ({', '.join(kandidaten)}).") from None
            if log:
                log(f"Modell {m} nicht verfügbar, nehme {kandidaten[i + 1]} …")


class ModellFehlt(Exception):
    pass


def _auswerten_einmal(schluessel: str, anfrage: dict, modell: str, timeout: int) -> dict:
    req = urllib.request.Request(URL.format(modell=modell), data=json.dumps(anfrage).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": schluessel})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            antwort = json.loads(r.read())
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(text)["error"]["message"]
        except Exception:
            msg = text[:300]
        if e.code in (400, 403) and "API key" in msg:
            raise RuntimeError("Gemini-Schlüssel ungültig. Bitte in den Einstellungen prüfen.") from e
        if e.code == 404 or (e.code == 400 and "model" in msg.lower() and "not" in msg.lower() and "found" in msg.lower()):
            raise ModellFehlt(msg) from e
        if e.code == 429:
            raise RuntimeError("Gemini-Tageslimit erreicht (kostenloser Schlüssel). Später erneut versuchen.") from e
        raise RuntimeError(f"Gemini-Fehler {e.code}: {msg}") from e
    return antwort_lesen(antwort)


def antwort_lesen(antwort: dict) -> dict:
    try:
        text = antwort["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError("Gemini hat keine Antwort geliefert: " + json.dumps(antwort)[:300]) from e
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)
