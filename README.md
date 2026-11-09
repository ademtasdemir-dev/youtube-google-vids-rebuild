# YouTube → Google Vids Rebuild Tool

Analysiere ein YouTube-Video und erstelle daraus ein **Szenen-Skript** + **Google Vids Prompt** für dein eigenes Thema.

## Features
- 🎯 **Szenen-Erkennung** – Automatische Aufteilung nach Pausen
- 🪝 **Hook-Erkennung** – Erste 15 Sekunden als Vorlage
- ⚡ **Pacing-Analyse** – Wörter/Minute, Tempo-Klassifizierung
- 🔑 **Keyword-Extraktion** – Top 10 Schlüsselwörter (DE + EN)
- 📋 **Google Vids Prompt** – Copy-Paste in Google Vids "Erstellen"
- 📝 **Szenen-Skript** – Szene-für-Szene Vorlage mit Platzhaltern

## EXE (Windows, ohne Installation)

**Download:** [`Download/YouTubeRebuildTool-1.1.0-portable.exe`](Download/YouTubeRebuildTool-1.1.0-portable.exe)
öffnen → rechts „Download raw file“ (⤓) → doppelklicken. Keine Installation nötig.
Die App öffnet sich dann automatisch im Browser.
Beim ersten Start zeigt Windows evtl. „Unbekannter Herausgeber“ → *Weitere Informationen* → *Trotzdem ausführen*.

Hinweis: YouTube blockiert Anfragen von Cloud-/VPN-IPs. Starte die EXE auf deinem
Heim-PC ohne VPN, damit das Transkript abgerufen werden kann.

## Entwicklung (lokales Setup)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

Dann öffne die automatisch geöffnete Browser-Seite (bzw. http://127.0.0.1:8000,
wenn du `uvicorn analyzer:app` nutzt).

## EXE selbst bauen

Lokal auf Windows:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name YouTubeRebuildTool ^
  --add-data "static;static" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  run.py
```

Oder automatisch per GitHub Actions: Workflow **Build Windows EXE** manuell starten
(Actions-Tab → Build Windows EXE → Run workflow). Die fertige EXE liegt dann unter
Artifacts.

## Tech Stack
- **Backend:** FastAPI + youtube-transcript-api
- **Frontend:** Vanilla HTML/CSS/JS (Dark Theme, Glassmorphism)
- **Build:** PyInstaller (onefile EXE), GitHub Actions
