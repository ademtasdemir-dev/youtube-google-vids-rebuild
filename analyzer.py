import re
import math
from collections import Counter
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi

app = FastAPI(title="YouTube Video Rebuild Tool", version="1.0.0")

# Allow the HTML frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (the frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

YOUTUBE_URL_RE = re.compile(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})")

STOP_WORDS = {
    "the", "and", "to", "a", "of", "in", "is", "it", "that", "i", "you",
    "we", "for", "on", "this", "with", "as", "are", "was", "be", "or",
    "so", "but", "do", "if", "not", "just", "like", "have", "has", "had",
    "what", "when", "where", "how", "all", "can", "will", "there", "their",
    "they", "them", "then", "than", "been", "being", "its", "my", "your",
    "our", "an", "at", "by", "from", "about", "into", "up", "out", "no",
    "one", "would", "could", "should", "did", "does", "done", "going",
    "get", "got", "go", "know", "see", "want", "think", "make", "say",
    "said", "really", "very", "more", "some", "also", "here", "well",
    "now", "way", "may", "still", "even", "too", "any", "each", "much",
    "own", "other", "take", "come", "over", "only", "because", "don",
    "t", "s", "re", "ve", "ll", "d", "m", "um", "uh", "oh", "yeah",
    "okay", "right", "thing", "things", "lot", "actually", "kind",
    "da", "die", "der", "und", "ist", "ich", "das", "du", "wir", "es",
    "ein", "eine", "nicht", "auch", "auf", "den", "mit", "hat", "von",
    "sind", "aber", "ja", "was", "so", "man", "dann", "wie", "noch",
    "mal", "oder", "wenn", "nur", "schon", "als",
}


class AnalyzeRequest(BaseModel):
    url: str


class RebuildRequest(BaseModel):
    url: str
    keyword: str
    language: str = "de"


# ─── Helper functions ──────────────────────────────────────────────────────


def extract_video_id(url: str) -> str:
    match = YOUTUBE_URL_RE.search(url)
    if match:
        return match.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", url):
        return url
    raise ValueError("Ungültige YouTube-URL oder Video-ID")


def fetch_transcript(video_id: str) -> List[Dict[str, Any]]:
    api = YouTubeTranscriptApi()
    try:
        return api.fetch(video_id, languages=["de", "en"]).to_raw_data()
    except Exception:
        try:
            return api.fetch(video_id).to_raw_data()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Transkript nicht verfügbar: {e}")


def full_text(transcript: List[Dict[str, Any]]) -> str:
    return " ".join(entry["text"] for entry in transcript)


def total_duration(transcript: List[Dict[str, Any]]) -> float:
    if not transcript:
        return 0
    last = transcript[-1]
    return last["start"] + last.get("duration", 0)


# ─── Analysis layers ───────────────────────────────────────────────────────


def detect_scenes(transcript: List[Dict[str, Any]], pause_threshold: float = 2.5) -> List[Dict[str, Any]]:
    """Split the transcript into scenes based on pauses between segments."""
    if not transcript:
        return []

    scenes: List[Dict[str, Any]] = []
    current_scene_entries: List[Dict[str, Any]] = [transcript[0]]

    for i in range(1, len(transcript)):
        prev_end = transcript[i - 1]["start"] + transcript[i - 1].get("duration", 0)
        gap = transcript[i]["start"] - prev_end
        if gap >= pause_threshold:
            scenes.append(_build_scene(current_scene_entries, len(scenes) + 1))
            current_scene_entries = []
        current_scene_entries.append(transcript[i])

    if current_scene_entries:
        scenes.append(_build_scene(current_scene_entries, len(scenes) + 1))

    # If we got too few scenes, split evenly by time
    if len(scenes) < 3:
        scenes = _split_scenes_evenly(transcript, target_count=max(4, len(transcript) // 15))

    return scenes


def _build_scene(entries: List[Dict[str, Any]], number: int) -> Dict[str, Any]:
    text = " ".join(e["text"] for e in entries)
    start = entries[0]["start"]
    end = entries[-1]["start"] + entries[-1].get("duration", 0)
    return {
        "scene_number": number,
        "start_sec": round(start, 1),
        "end_sec": round(end, 1),
        "duration_sec": round(end - start, 1),
        "text": text,
        "word_count": len(text.split()),
    }


def _split_scenes_evenly(transcript: List[Dict[str, Any]], target_count: int) -> List[Dict[str, Any]]:
    total = total_duration(transcript)
    interval = total / target_count
    scenes: List[Dict[str, Any]] = []
    current_entries: List[Dict[str, Any]] = []
    next_cut = interval

    for entry in transcript:
        current_entries.append(entry)
        if entry["start"] >= next_cut and current_entries:
            scenes.append(_build_scene(current_entries, len(scenes) + 1))
            current_entries = []
            next_cut += interval

    if current_entries:
        scenes.append(_build_scene(current_entries, len(scenes) + 1))
    return scenes


def extract_hook(transcript: List[Dict[str, Any]]) -> str:
    """Return the first ~15 seconds of text (the hook)."""
    hook_parts = []
    for entry in transcript:
        if entry["start"] > 15:
            break
        hook_parts.append(entry["text"])
    return " ".join(hook_parts)


def extract_keywords(transcript: List[Dict[str, Any]], top_n: int = 10) -> List[str]:
    words = re.findall(r"\b[a-zA-ZäöüÄÖÜß]{3,}\b", full_text(transcript).lower())
    freq = Counter(w for w in words if w not in STOP_WORDS)
    return [word for word, _ in freq.most_common(top_n)]


def detect_text_style(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyse average sentence length, pacing, etc."""
    text = full_text(transcript)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_words = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
    dur = total_duration(transcript)
    words_per_min = len(text.split()) / max(dur / 60, 0.1)
    return {
        "avg_sentence_words": round(avg_words, 1),
        "total_sentences": len(sentences),
        "words_per_minute": round(words_per_min, 1),
        "pacing": "schnell" if words_per_min > 170 else ("mittel" if words_per_min > 130 else "langsam"),
    }


def detect_cta(transcript: List[Dict[str, Any]]) -> Optional[str]:
    """Try to find a call-to-action in the last 20 seconds."""
    cta_parts = []
    dur = total_duration(transcript)
    for entry in transcript:
        if entry["start"] >= dur - 20:
            cta_parts.append(entry["text"])
    return " ".join(cta_parts) if cta_parts else None


# ─── Scene-script & prompt generation ──────────────────────────────────────


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def generate_scene_script(scenes: List[Dict[str, Any]], keyword: str, hook: str, style: Dict[str, Any], cta: Optional[str], lang: str) -> str:
    """Generate a scene-by-scene script adapted for the user's keyword."""
    lines = []
    lines.append(f"# 🎬 Video-Skript: {keyword}\n")
    lines.append(f"**Pacing:** {style['pacing']} ({style['words_per_minute']} Wörter/Min)")
    lines.append(f"**Szenen:** {len(scenes)}")
    lines.append(f"**Gesamtdauer:** {_format_time(scenes[-1]['end_sec'] if scenes else 0)}\n")
    lines.append("---\n")

    for sc in scenes:
        lines.append(f"## Szene {sc['scene_number']}  ({_format_time(sc['start_sec'])} – {_format_time(sc['end_sec'])}  |  {sc['duration_sec']}s)")

        if sc["scene_number"] == 1:
            lines.append(f"**Typ:** Hook / Einstieg")
            lines.append(f"**Vorlage-Text:** _{hook[:120]}…_")
            lines.append(f"**Dein Text:** [Schreibe hier einen packenden Einstieg zu **{keyword}**]")
        elif sc == scenes[-1] and cta:
            lines.append(f"**Typ:** Call-to-Action / Abschluss")
            lines.append(f"**Vorlage-Text:** _{cta[:120]}…_")
            lines.append(f"**Dein Text:** [CTA für **{keyword}** – z. B. Abonnieren, Link, Produkt]")
        else:
            lines.append(f"**Typ:** Hauptteil")
            lines.append(f"**Vorlage-Text:** _{sc['text'][:120]}…_")
            lines.append(f"**Dein Text:** [Inhalt zu **{keyword}** passend zu dieser Szene]")

        lines.append(f"**Bild-/Video-Empfehlung:** [Beschreibung passend zu {keyword}]")
        lines.append(f"**Text-Overlay:** [Kurzer Text für Einblendung]")
        lines.append("")

    return "\n".join(lines)


def generate_google_vids_prompt(scenes: List[Dict[str, Any]], keyword: str, hook: str, style: Dict[str, Any], keywords: List[str], cta: Optional[str], lang: str) -> str:
    """Generate a copy-paste prompt for Google Vids 'Erstellen' feature."""
    dur = total_duration_from_scenes(scenes)
    scene_count = len(scenes)

    prompt_lines = []
    prompt_lines.append(f"Erstelle ein professionelles Video zum Thema \"{keyword}\".\n")
    prompt_lines.append(f"Das Video soll {_format_time(dur)} lang sein und {scene_count} Szenen enthalten.")
    prompt_lines.append(f"Das Pacing ist {style['pacing']} (~{style['words_per_minute']} Wörter/Minute).\n")

    prompt_lines.append("Struktur:")
    for sc in scenes:
        if sc["scene_number"] == 1:
            prompt_lines.append(f"  Szene 1 (0:00–{_format_time(sc['end_sec'])}): Packender Hook-Einstieg. Sofort Aufmerksamkeit erzeugen. Stil: dramatisch, überraschend.")
        elif sc == scenes[-1]:
            prompt_lines.append(f"  Szene {sc['scene_number']} ({_format_time(sc['start_sec'])}–{_format_time(sc['end_sec'])}): Call-to-Action / Abschluss. Zuschauer zum Handeln auffordern.")
        else:
            prompt_lines.append(f"  Szene {sc['scene_number']} ({_format_time(sc['start_sec'])}–{_format_time(sc['end_sec'])}): Hauptinhalt ({sc['duration_sec']}s). Informativ und visuell ansprechend.")

    prompt_lines.append(f"\nSchlüsselwörter: {', '.join(keywords[:7])}")
    prompt_lines.append(f"Stil: Modern, professionell, mit Text-Overlays und dynamischen Übergängen.")
    prompt_lines.append(f"Musik: Passend zum Thema, motivierend, nicht zu laut.")
    prompt_lines.append(f"Voiceover: Klar und professionell, {style['pacing']}es Tempo.")

    if cta:
        prompt_lines.append(f"\nDer Abschluss soll einen klaren Call-to-Action enthalten.")

    return "\n".join(prompt_lines)


def total_duration_from_scenes(scenes: List[Dict[str, Any]]) -> float:
    if not scenes:
        return 0
    return scenes[-1]["end_sec"]


# ─── API endpoints ─────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    try:
        video_id = extract_video_id(request.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    transcript = fetch_transcript(video_id)
    scenes = detect_scenes(transcript)

    return {
        "video_id": video_id,
        "duration": round(total_duration(transcript), 1),
        "scenes": scenes,
        "hook": extract_hook(transcript),
        "keywords": extract_keywords(transcript),
        "text_style": detect_text_style(transcript),
        "cta": detect_cta(transcript),
        "transcript_preview": full_text(transcript)[:500],
    }


@app.post("/rebuild")
async def rebuild(request: RebuildRequest):
    try:
        video_id = extract_video_id(request.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    transcript = fetch_transcript(video_id)
    scenes = detect_scenes(transcript)
    hook = extract_hook(transcript)
    keywords = extract_keywords(transcript)
    style = detect_text_style(transcript)
    cta = detect_cta(transcript)

    scene_script = generate_scene_script(scenes, request.keyword, hook, style, cta, request.language)
    google_vids_prompt = generate_google_vids_prompt(scenes, request.keyword, hook, style, keywords, cta, request.language)

    return {
        "video_id": video_id,
        "keyword": request.keyword,
        "scene_script": scene_script,
        "google_vids_prompt": google_vids_prompt,
        "analysis": {
            "duration": round(total_duration(transcript), 1),
            "scene_count": len(scenes),
            "pacing": style["pacing"],
            "keywords": keywords,
        },
    }
