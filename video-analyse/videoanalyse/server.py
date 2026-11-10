"""Lokaler Server für die Oberfläche. Läuft nur auf diesem PC (127.0.0.1), nichts ist von außen erreichbar."""
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import analyse, bericht, cartesia, werkzeug

BASIS = Path(__file__).resolve().parent.parent
UI = BASIS / "ui"
DATEN = Path(os.environ.get("VA_DATEN", BASIS / "daten"))
ARBEIT, CACHE, EINST = DATEN / "arbeit", DATEN / "modelle", DATEN / "einstellungen.json"

JOB = {"fs": None, "thread": None, "ordner": None}


def einstellungen() -> dict:
    try:
        return json.loads(EINST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def einstellungen_speichern(neu: dict):
    alt = einstellungen()
    alt.update({k: v for k, v in neu.items() if v is not None})
    DATEN.mkdir(parents=True, exist_ok=True)
    EINST.write_text(json.dumps(alt, ensure_ascii=False, indent=1), encoding="utf-8")


def _dialog(art: str, titel: str) -> str | None:
    """Öffnet einen Windows-Dialog (Ordner wählen / Datei wählen). Für Tests: VA_DIALOG_TEST setzt die Antwort."""
    test = os.environ.get("VA_DIALOG_TEST")
    if test is not None:
        return test or None
    code = ("import tkinter as tk; from tkinter import filedialog as f; r=tk.Tk(); r.withdraw(); r.attributes('-topmost',1); "
            + ("p=f.askdirectory(title=%r, mustexist=True)" % titel if art == "ordner" else
               "p=f.askopenfilename(title=%r, filetypes=[('Videos','*.mp4 *.mkv *.mov *.webm *.avi *.m4v'),('Alle','*.*')])" % titel)
            + "; print(p or '', end='')")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, creationflags=flags)
    return r.stdout.strip() or None


def _sicher(ordner: str, rel: str = "") -> Path:
    basis = (ARBEIT / ordner).resolve()
    p = (basis / rel).resolve()
    if ARBEIT.resolve() not in basis.parents or (p != basis and basis not in p.parents):
        raise PermissionError("Ungültiger Pfad")
    return p


def _frei(ziel: Path) -> Path:
    if not ziel.exists():
        return ziel
    for i in range(2, 1000):
        k = ziel.with_name(f"{ziel.stem} ({i}){ziel.suffix}")
        if not k.exists():
            return k
    return ziel


def ergebnis_laden(ordner: str) -> dict:
    return json.loads(_sicher(ordner, "ergebnis.json").read_text(encoding="utf-8"))


def verlauf() -> list[dict]:
    out = []
    for p in sorted(ARBEIT.glob("*/ergebnis.json"), key=lambda x: -x.stat().st_mtime) if ARBEIT.exists() else []:
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
            groesse = sum(f.stat().st_size for f in p.parent.rglob("*") if f.is_file())
            out.append({"ordner": p.parent.name, "titel": e["info"].get("title"), "dauer": e["kennzahlen"]["dauer"],
                        "art": e.get("analyse_art"), "mb": round(groesse / 1e6, 1)})
        except Exception:
            continue
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, daten, code=200):
        b = json.dumps(daten, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _fehler(self, text, code=400):
        self._json({"fehler": text}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _datei(self, p: Path):
        if not p.is_file():
            return self._fehler("Datei nicht gefunden", 404)
        groesse = p.stat().st_size
        typ = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        bereich = self.headers.get("Range")
        start, ende = 0, groesse - 1
        if bereich and bereich.startswith("bytes="):
            a, _, b = bereich[6:].partition("-")
            start = int(a) if a else 0
            ende = int(b) if b else groesse - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{ende}/{groesse}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", typ + ("; charset=utf-8" if typ.startswith("text") else ""))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(ende - start + 1))
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            rest = ende - start + 1
            while rest > 0:
                stueck = f.read(min(1 << 20, rest))
                if not stueck:
                    break
                try:
                    self.wfile.write(stueck)
                except (ConnectionResetError, BrokenPipeError):
                    return
                rest -= len(stueck)

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if not self._eigene_seite():
            return self._fehler("Anfrage abgelehnt.", 403)
        try:
            if u.path in ("/", "/index.html"):
                return self._datei(UI / "index.html")
            if u.path == "/api/status":
                fs = JOB["fs"]
                return self._json({"laeuft": bool(JOB["thread"] and JOB["thread"].is_alive()), "ordner": JOB["ordner"],
                                   "fortschritt": fs.als_dict() if fs else None, "schritte": analyse.SCHRITTE})
            if u.path == "/api/ergebnis":
                return self._json(ergebnis_laden(q["ordner"]))
            if u.path == "/api/verlauf":
                return self._json(verlauf())
            if u.path == "/api/einstellungen":
                e = einstellungen(); k = e.get("gemini_schluessel", "")
                return self._json({**e, "gemini_schluessel": ("•" * 8 + k[-4:]) if k else "", "gemini_gesetzt": bool(k)})
            if u.path == "/datei":
                return self._datei(_sicher(q["ordner"], q["pfad"]))
            return self._fehler("Unbekannte Adresse", 404)
        except PermissionError as e:
            return self._fehler(str(e), 403)
        except (KeyError, FileNotFoundError) as e:
            return self._fehler(f"Nicht gefunden: {e}", 404)

    def _eigene_seite(self) -> bool:
        """Nur Anfragen von der eigenen Oberfläche annehmen (Schutz gegen fremde Webseiten im Browser)."""
        port = self.server.server_address[1]
        erlaubt = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in erlaubt:
            return False
        herkunft = self.headers.get("Origin")
        return herkunft is None or herkunft.split("://", 1)[-1] in erlaubt

    def do_POST(self):
        u = urlparse(self.path)
        if not self._eigene_seite():
            return self._fehler("Anfrage abgelehnt (nicht von der eigenen Oberfläche).", 403)
        try:
            d = self._body()
            if u.path == "/api/analyse":
                if JOB["thread"] and JOB["thread"].is_alive():
                    return self._fehler("Es läuft bereits eine Analyse.", 409)
                eingabe = (d.get("eingabe") or "").strip()
                if not eingabe:
                    return self._fehler("Bitte einen YouTube-Link oder eine Videodatei angeben.")
                fs = analyse.Fortschritt()
                JOB.update(fs=fs, ordner=analyse.ordner_name(eingabe))
                def lauf():
                    try:
                        analyse.analysieren(eingabe, d.get("optionen") or {}, ARBEIT, CACHE, einstellungen(), fs)
                    except Exception:
                        pass
                JOB["thread"] = threading.Thread(target=lauf, daemon=True); JOB["thread"].start()
                return self._json({"ok": True, "ordner": JOB["ordner"]})
            if u.path == "/api/datei_waehlen":
                return self._json({"pfad": _dialog("datei", "Video auswählen")})
            if u.path == "/api/speichern":
                return self._speichern(d)
            if u.path == "/api/text_speichern":
                ziel = _dialog("ordner", "Wo soll die Datei gespeichert werden?")
                if not ziel:
                    return self._json({"abgebrochen": True})
                name = Path(d.get("name") or "text.txt").name
                p = _frei(Path(ziel) / name); p.write_text(d.get("inhalt", ""), encoding="utf-8")
                return self._json({"gespeichert": [str(p)]})
            if u.path == "/api/cartesia":
                o = d.get("optionen") or {}
                extra = {}
                for zeile in (o.get("aussprache") or "").splitlines():
                    if "=" in zeile:
                        a, b = zeile.split("=", 1)
                        if a.strip():
                            extra[a.strip()] = b.strip()
                r = cartesia.bauen(d.get("text", ""), int(o.get("satzpause", 400)), int(o.get("absatzpause", 700)),
                                   int(o.get("doppelpunktpause", 300)), o.get("fueller", "wenig"), extra,
                                   o.get("vorredner", ""), o.get("nachredner", ""), int(o.get("seed", 7)),
                                   int(o.get("aehm_pause", 200) or 0))
                r["api"] = cartesia.api_anfrage(r["text"], (o.get("modell") or "sonic-3").strip(), (o.get("stimme_id") or "").strip(),
                                                float(o.get("tempo") or 1.0))
                if o.get("modell") or o.get("stimme_id"):
                    einstellungen_speichern({"cartesia_modell": o.get("modell"), "cartesia_stimme": o.get("stimme_id")})
                return self._json(r)
            if u.path == "/api/einstellungen":
                neu = {k: d.get(k) for k in ("gemini_modell", "whisper_modell", "browser_cookies", "gemini_video")}
                if d.get("gemini_schluessel") is not None and "•" not in d["gemini_schluessel"]:
                    neu["gemini_schluessel"] = d["gemini_schluessel"].strip()
                einstellungen_speichern(neu)
                return self._json({"ok": True})
            if u.path == "/api/kapitel":
                e = ergebnis_laden(d["ordner"])
                e["kapitel"] = d["kapitel"]
                e["kapitel_hinweise"] = bericht.kapitel_pruefen(e["kapitel"])
                _sicher(d["ordner"], "ergebnis.json").write_text(bericht.als_json(e), encoding="utf-8")
                return self._json({"hinweise": e["kapitel_hinweise"],
                                   "beschreibung": bericht.youtube_beschreibung(e["zusammenfassung"].get("kurz", ""), e["kapitel"])})
            if u.path == "/api/ordner_oeffnen":
                p = _sicher(d["ordner"])
                if sys.platform == "win32":
                    os.startfile(p)  # noqa
                return self._json({"pfad": str(p)})
            if u.path == "/api/gemini_test":
                from . import gemini
                e = einstellungen(); k = (e.get("gemini_schluessel") or "").strip()
                if not k:
                    return self._fehler("Noch kein Gemini-Schlüssel gespeichert.")
                try:
                    return self._json(gemini.testen(k, e.get("gemini_modell") or gemini.STANDARD_MODELL))
                except Exception as ex:
                    return self._fehler(str(ex), 502)
            if u.path == "/api/alles_loeschen":
                if JOB["thread"] and JOB["thread"].is_alive():
                    return self._fehler("Es läuft gerade eine Analyse.", 409)
                anzahl = 0
                for p in list(ARBEIT.iterdir()) if ARBEIT.exists() else []:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True); anzahl += 1
                return self._json({"geloescht": anzahl})
            if u.path == "/api/loeschen":
                if JOB["thread"] and JOB["thread"].is_alive() and JOB["ordner"] == d["ordner"]:
                    return self._fehler("Diese Analyse läuft gerade.", 409)
                p = _sicher(d["ordner"])
                shutil.rmtree(p, ignore_errors=True)
                return self._json({"geloescht": not p.exists()})
            return self._fehler("Unbekannte Adresse", 404)
        except PermissionError as e:
            return self._fehler(str(e), 403)
        except Exception as e:
            return self._fehler(f"{e.__class__.__name__}: {e}", 500)

    def _speichern(self, d):
        """Fragt JEDES Mal nach dem Zielordner und kopiert die gewählten Dateien dorthin."""
        ordner, dateien, fmt = d["ordner"], d.get("dateien") or [], d.get("format", "original")
        quellen = [_sicher(ordner, x) for x in dateien]
        fehlend = [str(q) for q in quellen if not q.is_file()]
        if fehlend:
            return self._fehler("Fehlt: " + ", ".join(fehlend), 404)
        titel = d.get("titel") or "Download-Ordner wählen"
        ziel = _dialog("ordner", titel)
        if not ziel:
            return self._json({"abgebrochen": True})
        zielp = Path(ziel); zielp.mkdir(parents=True, exist_ok=True)
        praefix = (d.get("praefix") or "").strip()
        gespeichert = []
        if d.get("zip"):
            z = _frei(zielp / f"{praefix or ordner}.zip")
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for q in quellen:
                    zf.write(q, q.name)
            return self._json({"gespeichert": [str(z)]})
        for q in quellen:
            name = f"{praefix} – {q.name}" if praefix else q.name
            if fmt == "mp3" and q.suffix.lower() == ".wav":
                gespeichert.append(str(werkzeug.mp3_aus_wav(q, _frei(zielp / Path(name).with_suffix(".mp3")))))
            else:
                p = _frei(zielp / name); shutil.copy2(q, p); gespeichert.append(str(p))
        return self._json({"gespeichert": gespeichert})


def fenster_oeffnen(url: str):
    """Öffnet die Oberfläche als eigenes App-Fenster (Edge/Chrome im App-Modus), sonst im Standard-Browser."""
    if sys.platform == "win32":
        kandidaten = [Path(os.environ.get(v, "")) / rel for v in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData")
                      for rel in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")]
        for exe in kandidaten:
            if exe.is_file():
                try:
                    subprocess.Popen([str(exe), f"--app={url}", "--window-size=1440,900"])
                    return
                except OSError:
                    continue
    webbrowser.open(url)


def starten(port: int = 8765, browser: bool = True):
    ARBEIT.mkdir(parents=True, exist_ok=True); CACHE.mkdir(parents=True, exist_ok=True)
    for versuch in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", versuch), Handler)
            break
        except OSError:
            continue
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Video-Analyse läuft: {url}\nDieses Fenster offen lassen. Beenden mit Strg+C.")
    if browser:
        threading.Timer(0.8, lambda: fenster_oeffnen(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
