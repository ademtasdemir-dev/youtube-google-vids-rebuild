# Vortrag-Werkstatt

Aus einer PowerPoint wird: Sprechtext → Teleprompter → Video mit Klick-Lupe → Thumbnail → YouTube-Upload → Aufräumen.
Gesteuert wird alles über den Prompt „Vortrag-Paket“ in der Prompt-Bibliothek. Claude nutzt diese Werkzeuge.

| Baukasten | Ordner | Läuft wo | Eingabe → Ergebnis |
|---|---|---|---|
| Video | `video/` | bei Claude (Cloud) | PPTX + Audio + Drehbuch → MP4 mit Klick-Lupe |
| Thumbnail | `thumbnail/` | bei Claude (Cloud) | kleine JSON → 1280×720 PNG, automatisch geprüft |
| Teleprompter | `teleprompter/` | Browser | Lesetext → HTML-Seite |
| Automatischer YouTube-Upload | `upload/` | dein PC | paket.json → Video auf YouTube + Aufräumen |

## Ablauf Video (Claude)
```
python video/folien.py Praesentation.pptx --von 7 --bis 11 --ziel arbeit
uv run --with faster-whisper --with numpy video/transkribieren.py audio.wav --ziel arbeit/woerter.json
python video/ausrichten.py drehbuch.json audio.wav --woerter arbeit/woerter.json --ziel arbeit/zeitplan.json
python video/render_lupe.py arbeit/zeitplan.json arbeit audio.wav --ziel Vortrag.mp4
```
Das Drehbuch (`video/drehbuch_beispiel.json`) legt pro Folie fest: erster Satz der Folie und pro Punkt Satzanfang + Bereich auf der Folie.
Die Zeiten kommen aus dem, was in der Audio wirklich gesprochen wird (lokale Spracherkennung, keine Cloud-Kosten).

## Thumbnail
```
python thumbnail/thumbnail.py thumbnail/beispiele/raid_satz.json --ziel Thumbnail.png
```
Bricht mit Fehlermeldung ab, wenn sich etwas überlappt, aus dem Bild ragt oder Text überläuft.

## Teleprompter
```
python teleprompter/baue_prompter.py lesetext.json --ziel Prompter.html --titel "Prompter Folie 7–12"
```

## Speicher-Regel
Auf dem PC bleibt nur das Upload-Tool. Alles andere entsteht bei Claude.
Nach erfolgreichem Upload löscht das Upload-Tool Video, Thumbnail, PPTX/WAV und den Arbeitsordner (siehe `upload/ANLEITUNG.md`).

## Tests
```
cd upload && uv run --with pytest pytest -q     # 28 Tests
cd video  && python -m pytest -q               # 8 Tests
```
