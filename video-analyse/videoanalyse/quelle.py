"""Video holen: YouTube-Link (yt-dlp) oder eigene Datei auf dem PC."""
import json
import shutil
from pathlib import Path

from . import werkzeug, zeit

FELDER = ("id", "title", "uploader", "channel", "duration", "description", "tags", "categories",
          "chapters", "upload_date", "view_count", "like_count", "thumbnail", "webpage_url", "language")


def _info_kurz(info: dict) -> dict:
    k = {f: info.get(f) for f in FELDER}
    k["chapters"] = [{"start": c.get("start_time", 0), "ende": c.get("end_time"), "titel": c.get("title", "")}
                     for c in (info.get("chapters") or [])]
    k["tags"] = k.get("tags") or []
    return k


def fehler_erklaeren(text: str) -> str:
    t = text.lower()
    if "sign in to confirm" in t or "not a bot" in t:
        return ("YouTube verlangt eine Anmeldung (Bot-Schutz). Unter Einstellungen „Browser-Anmeldung nutzen“ auf Firefox oder Edge "
                "stellen, dort bei YouTube angemeldet sein, und erneut versuchen.")
    if "private video" in t:
        return "Das Video ist privat. Nur nicht gelistete oder öffentliche Videos lassen sich analysieren."
    if "video unavailable" in t or "removed" in t:
        return "Das Video ist nicht verfügbar (gelöscht, gesperrt oder Link falsch)."
    if "age" in t and "confirm" in t:
        return "Das Video ist altersbeschränkt. Browser-Anmeldung in den Einstellungen nutzen."
    if "http error 403" in t:
        return "YouTube hat den Download abgelehnt (403). Später erneut versuchen oder Browser-Anmeldung nutzen."
    return text


def von_youtube(url: str, ziel: Path, log=print, browser: str = "") -> dict:
    """Lädt das Video (max. 720p reicht für die Analyse), Metadaten und Vorschaubild."""
    import yt_dlp
    vid = zeit.video_id(url)
    if not vid:
        raise ValueError("Das ist kein gültiger YouTube-Link.")
    ziel.mkdir(parents=True, exist_ok=True)

    def fortschritt(d):
        if d.get("status") == "downloading" and d.get("total_bytes"):
            log(f"Download {d['downloaded_bytes'] * 100 // d['total_bytes']} %", prozent=d["downloaded_bytes"] / d["total_bytes"])

    opts = {
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(ziel / "video.%(ext)s"),
        "noplaylist": True,
        "writethumbnail": True,
        "quiet": True, "no_warnings": True, "noprogress": True,
        "ffmpeg_location": werkzeug.ffmpeg(),
        "progress_hooks": [fortschritt],
    }
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True)
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(fehler_erklaeren(str(e))) from None
    video = next((p for p in ziel.glob("video.*") if p.suffix.lower() in (".mp4", ".mkv", ".webm")), None)
    if not video:
        raise RuntimeError("Download fehlgeschlagen: keine Videodatei erhalten.")
    vorschau = next((p for p in ziel.glob("video.*") if p.suffix.lower() in (".jpg", ".webp", ".png")), None)
    k = _info_kurz(info)
    k.update({"video": str(video), "vorschaubild": str(vorschau) if vorschau else None, "quelle": "youtube"})
    (ziel / "info.json").write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
    return k


def von_datei(pfad: str, ziel: Path) -> dict:
    p = Path(pfad.strip().strip('"'))
    if not p.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {p}")
    ziel.mkdir(parents=True, exist_ok=True)
    kopie = ziel / ("video" + p.suffix.lower())
    shutil.copy2(p, kopie)
    k = {f: None for f in FELDER}
    k.update({"id": p.stem[:40], "title": p.stem, "duration": werkzeug.dauer(kopie), "tags": [], "chapters": [],
              "video": str(kopie), "vorschaubild": None, "quelle": "datei", "webpage_url": str(p)})
    (ziel / "info.json").write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
    return k
