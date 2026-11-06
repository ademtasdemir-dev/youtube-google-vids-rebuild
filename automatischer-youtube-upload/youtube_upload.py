"""Automatischer YouTube-Upload – Kern-Logik und Kommandozeile.

Beispiele:
  uv run youtube_upload.py --video vortrag.mp4 --titel "Netzwerk & Backup" --beschreibung-datei text.txt --tags "VLAN, RAID 6"
  uv run youtube_upload.py --paket paket.json
  uv run youtube_upload.py --warteschlange          (überwacht den Ordner "warteschlange")
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ORDNER = Path(__file__).resolve().parent
CLIENT_SECRET = ORDNER / "client_secret.json"
TOKEN = ORDNER / "token.json"
WARTESCHLANGE = ORDNER / "warteschlange"
ERLEDIGT = WARTESCHLANGE / "erledigt"
FEHLER = WARTESCHLANGE / "fehler"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SICHTBARKEIT = {"nicht gelistet": "unlisted", "unlisted": "unlisted", "privat": "private", "private": "private",
                "öffentlich": "public", "oeffentlich": "public", "public": "public"}


class UploadFehler(Exception):
    """Fehler mit verständlicher deutscher Meldung."""


@dataclass
class Paket:
    video: str
    titel: str
    beschreibung: str = ""
    tags: list[str] = field(default_factory=list)
    thumbnail: Optional[str] = None
    sichtbarkeit: str = "nicht gelistet"
    fuer_kinder: bool = False
    kategorie: str = "22"  # YouTube-Standard "Menschen & Blogs"; 27 = Bildung

    @staticmethod
    def aus_dict(d: dict, basis: Path) -> "Paket":
        def pfad(p):
            if not p:
                return None
            q = Path(p)
            return str(q if q.is_absolute() else (basis / q))
        tags = d.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        return Paket(video=pfad(d.get("video")) or "", titel=d.get("titel", ""), beschreibung=d.get("beschreibung", ""),
                     tags=[t for t in tags if t], thumbnail=pfad(d.get("thumbnail")),
                     sichtbarkeit=d.get("sichtbarkeit", "nicht gelistet"), fuer_kinder=bool(d.get("fuer_kinder", False)),
                     kategorie=str(d.get("kategorie", "22")))

    def pruefen(self) -> list[str]:
        """Prüft alles vor dem Upload, gibt Liste mit Problemen zurück (leer = ok)."""
        p = []
        if not self.video or not Path(self.video).is_file():
            p.append(f"Videodatei nicht gefunden: {self.video or '(leer)'}")
        if not self.titel.strip():
            p.append("Titel fehlt.")
        if len(self.titel) > 100:
            p.append(f"Titel ist {len(self.titel)} Zeichen lang, erlaubt sind 100.")
        if len(self.beschreibung.encode("utf-8")) > 5000:
            p.append("Beschreibung ist länger als 5000 Bytes.")
        for name, text in (("Titel", self.titel), ("Beschreibung", self.beschreibung)):
            if "<" in text or ">" in text:
                p.append(f"{name} enthält < oder > – das lehnt YouTube ab.")
        tag_laenge = sum(len(t) + (2 if " " in t else 0) for t in self.tags) + max(0, len(self.tags) - 1)
        if tag_laenge > 500:
            p.append(f"Tags sind zusammen {tag_laenge} Zeichen lang, erlaubt sind 500.")
        if self.thumbnail:
            t = Path(self.thumbnail)
            if not t.is_file():
                p.append(f"Thumbnail nicht gefunden: {self.thumbnail}")
            elif t.stat().st_size > 2 * 1024 * 1024:
                p.append("Thumbnail ist größer als 2 MB.")
            elif t.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                p.append("Thumbnail muss PNG oder JPG sein.")
        if self.sichtbarkeit.lower() not in SICHTBARKEIT:
            p.append(f"Unbekannte Sichtbarkeit: {self.sichtbarkeit}")
        return p

    def body(self) -> dict:
        return {
            "snippet": {"title": self.titel.strip(), "description": self.beschreibung, "tags": self.tags,
                        "categoryId": self.kategorie, "defaultLanguage": "de", "defaultAudioLanguage": "de"},
            "status": {"privacyStatus": SICHTBARKEIT[self.sichtbarkeit.lower()],
                       "selfDeclaredMadeForKids": self.fuer_kinder},
        }


def anmelden(interaktiv: bool = True):
    """Liefert einen YouTube-Dienst. Beim ersten Mal öffnet sich der Browser zur Anmeldung."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not CLIENT_SECRET.exists():
            raise UploadFehler("client_secret.json fehlt im Upload-Ordner. Siehe ANLEITUNG.md, Schritt 1.")
        if not interaktiv:
            raise UploadFehler("Noch nicht angemeldet. Starte einmal die App und klicke auf „Anmelden“.")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def hochladen(paket: Paket, dienst=None, fortschritt: Optional[Callable[[float], None]] = None,
              log: Callable[[str], None] = print, versuche: int = 5) -> str:
    """Lädt das Video hoch, setzt das Thumbnail und gibt den Video-Link zurück."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    probleme = paket.pruefen()
    if probleme:
        raise UploadFehler("Upload abgebrochen:\n- " + "\n- ".join(probleme))
    dienst = dienst or anmelden()
    log(f"Lade hoch: {Path(paket.video).name}")
    media = MediaFileUpload(paket.video, chunksize=8 * 1024 * 1024, resumable=True)
    anfrage = dienst.videos().insert(part="snippet,status", body=paket.body(), media_body=media)
    antwort, fehlversuche = None, 0
    while antwort is None:
        try:
            status, antwort = anfrage.next_chunk()
            fehlversuche = 0
            if status and fortschritt:
                fortschritt(status.progress())
        except HttpError as e:
            code = getattr(e.resp, "status", 0)
            if code in (500, 502, 503, 504) and fehlversuche < versuche:
                fehlversuche += 1
                warte = 2 ** fehlversuche
                log(f"Server-Fehler {code}, neuer Versuch in {warte} s …")
                time.sleep(warte)
                continue
            raise UploadFehler(_fehlertext(e)) from e
        except (ConnectionError, TimeoutError, OSError) as e:
            if fehlversuche < versuche:
                fehlversuche += 1
                warte = 2 ** fehlversuche
                log(f"Verbindung unterbrochen, neuer Versuch in {warte} s …")
                time.sleep(warte)
                continue
            raise UploadFehler(f"Verbindung dauerhaft unterbrochen: {e}") from e
    if fortschritt:
        fortschritt(1.0)
    video_id = antwort["id"]
    link = f"https://youtu.be/{video_id}"
    log(f"Video hochgeladen: {link}")
    if paket.thumbnail:
        try:
            dienst.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(paket.thumbnail)).execute()
            log("Thumbnail gesetzt.")
        except HttpError as e:
            log("Achtung: Thumbnail konnte nicht gesetzt werden – " + _fehlertext(e) + " Das Video ist trotzdem oben.")
    return link


def _fehlertext(e) -> str:
    try:
        info = json.loads(e.content.decode("utf-8"))["error"]
        grund = (info.get("errors") or [{}])[0].get("reason", "")
        msg = info.get("message", "")
    except Exception:
        grund, msg = "", str(e)
    hilfen = {
        "quotaExceeded": "Tageslimit der YouTube-Schnittstelle erreicht. Morgen erneut versuchen.",
        "uploadLimitExceeded": "Upload-Limit für heute erreicht. Morgen erneut versuchen.",
        "forbidden": "Keine Berechtigung. Prüfe, ob du mit dem richtigen Konto angemeldet bist.",
        "invalidTitle": "Der Titel ist ungültig (leer, zu lang oder mit < >).",
        "invalidDescription": "Die Beschreibung ist ungültig (zu lang oder mit < >).",
        "invalidTags": "Die Tags sind ungültig (zusammen zu lang?).",
        "mediaBodyRequired": "Videodatei fehlt.",
    }
    return hilfen.get(grund, f"YouTube meldet: {msg or grund or e}")


def paket_laden(pfad: Path) -> Paket:
    try:
        d = json.loads(Path(pfad).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise UploadFehler(f"Paket-Datei ist kein gültiges JSON: {e}") from e
    return Paket.aus_dict(d, Path(pfad).resolve().parent)


def warteschlange_einmal(dienst_fabrik=anmelden, log: Callable[[str], None] = print) -> int:
    """Bearbeitet alle *.json-Pakete im Ordner warteschlange. Gibt Anzahl bearbeiteter Pakete zurück."""
    WARTESCHLANGE.mkdir(exist_ok=True); ERLEDIGT.mkdir(exist_ok=True); FEHLER.mkdir(exist_ok=True)
    pakete = sorted(WARTESCHLANGE.glob("*.json"))
    dienst = None
    for p in pakete:
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        try:
            paket = paket_laden(p)
            dienst = dienst or dienst_fabrik(interaktiv=False)
            link = hochladen(paket, dienst=dienst, log=log)
            ziel = ERLEDIGT / f"{stamp}_{p.name}"
            shutil.move(str(p), ziel)
            ziel.with_suffix(".link.txt").write_text(link + "\n", encoding="utf-8")
        except Exception as e:
            ziel = FEHLER / f"{stamp}_{p.name}"
            shutil.move(str(p), ziel)
            ziel.with_suffix(".fehler.txt").write_text(str(e) + "\n", encoding="utf-8")
            log(f"Fehler bei {p.name}: {e}")
    return len(pakete)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Video im Hintergrund auf YouTube hochladen")
    ap.add_argument("--video"); ap.add_argument("--titel"); ap.add_argument("--beschreibung", default="")
    ap.add_argument("--beschreibung-datei"); ap.add_argument("--tags", default="")
    ap.add_argument("--thumbnail"); ap.add_argument("--sichtbarkeit", default="nicht gelistet")
    ap.add_argument("--fuer-kinder", action="store_true"); ap.add_argument("--kategorie", default="22")
    ap.add_argument("--paket", help="JSON-Datei mit allen Angaben")
    ap.add_argument("--warteschlange", action="store_true", help="Ordner 'warteschlange' dauerhaft überwachen")
    ap.add_argument("--anmelden", action="store_true", help="Nur anmelden (Browser öffnet sich einmal)")
    ap.add_argument("--pruefen", action="store_true", help="Nur prüfen, nichts hochladen")
    a = ap.parse_args(argv)
    try:
        if a.anmelden:
            anmelden(); print("Angemeldet. token.json gespeichert."); return 0
        if a.warteschlange:
            print(f"Überwache {WARTESCHLANGE} – zum Beenden Strg+C.")
            while True:
                warteschlange_einmal(); time.sleep(10)
        if a.paket:
            paket = paket_laden(Path(a.paket))
        else:
            beschreibung = Path(a.beschreibung_datei).read_text(encoding="utf-8") if a.beschreibung_datei else a.beschreibung
            paket = Paket(video=a.video or "", titel=a.titel or "", beschreibung=beschreibung,
                          tags=[t.strip() for t in a.tags.split(",") if t.strip()], thumbnail=a.thumbnail,
                          sichtbarkeit=a.sichtbarkeit, fuer_kinder=a.fuer_kinder, kategorie=a.kategorie)
        if a.pruefen:
            pr = paket.pruefen(); print("Alles in Ordnung." if not pr else "\n".join(pr)); return 0 if not pr else 1
        def balken(x): print(f"\r{int(x*100):3d} %", end="", flush=True)
        link = hochladen(paket, fortschritt=balken)
        print(f"\nFertig: {link}")
        return 0
    except KeyboardInterrupt:
        print("\nBeendet."); return 0
    except UploadFehler as e:
        print(f"\n{e}", file=sys.stderr); return 1


if __name__ == "__main__":
    sys.exit(main())
