# YouTube → Google Vids Rebuild Tool

Analysiere ein YouTube-Video und erstelle daraus ein **Szenen-Skript** + **Google Vids Prompt** für dein eigenes Thema.

## Features
- 🎯 **Szenen-Erkennung** – Automatische Aufteilung nach Pausen
- 🪝 **Hook-Erkennung** – Erste 15 Sekunden als Vorlage
- ⚡ **Pacing-Analyse** – Wörter/Minute, Tempo-Klassifizierung
- 🔑 **Keyword-Extraktion** – Top 10 Schlüsselwörter (DE + EN)
- 📋 **Google Vids Prompt** – Copy-Paste in Google Vids "Erstellen"
- 📝 **Szenen-Skript** – Szene-für-Szene Vorlage mit Platzhaltern

## Setup
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn analyzer:app --host 127.0.0.1 --port 8000
```

Dann öffne http://127.0.0.1:8000 im Browser.

## Tech Stack
- **Backend:** FastAPI + youtube-transcript-api
- **Frontend:** Vanilla HTML/CSS/JS (Dark Theme, Glassmorphism)
