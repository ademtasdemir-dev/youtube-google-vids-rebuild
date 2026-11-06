# YouTube-Upload – Anleitung

Lädt Videos ohne Browser auf YouTube hoch: Titel, Beschreibung, Tags, Thumbnail, Sichtbarkeit (Standard: **Nicht gelistet**).
Kostenlos über die offizielle YouTube Data API.

## Einmalige Einrichtung (ca. 10 Minuten)

### 1. Zugang bei Google anlegen
1. Öffne <https://console.cloud.google.com> und melde dich mit dem **Google-Konto deines YouTube-Kanals** an.
2. Oben links auf die Projektauswahl → **Neues Projekt** → Name: `YouTube Upload` → **Erstellen**.
3. Links **APIs & Dienste → Bibliothek** → nach **YouTube Data API v3** suchen → **Aktivieren**.
4. Links **APIs & Dienste → OAuth-Zustimmungsbildschirm** (heißt teils auch „Google Auth Platform“):
   - App-Name: `YouTube Upload`, Support-E-Mail: deine Adresse.
   - Zielgruppe: **Extern**.
   - Unter **Zielgruppe / Testnutzer** dein Google-Konto eintragen.
   - Danach **App veröffentlichen** („In Produktion“). Sonst läuft die Anmeldung alle 7 Tage ab.
5. Links **Clients** (bzw. **Anmeldedaten**) → **Client erstellen** → Anwendungstyp **Desktop-App** → **Erstellen**.
6. **JSON herunterladen**, die Datei in diesen Ordner legen und in **`client_secret.json`** umbenennen.

### 2. Einmal anmelden
1. Doppelklick auf **`start.bat`** → das Fenster „YouTube-Upload“ öffnet sich.
2. Oben rechts auf **Anmelden** → der Browser öffnet sich.
3. Google zeigt „Google hat diese App nicht überprüft“ → **Erweitert → Weiter zu YouTube Upload** (das ist deine eigene App).
4. Zugriff erlauben. Danach steht oben „Angemeldet ✓“. Die Anmeldung liegt in `token.json` und bleibt gespeichert.

> `client_secret.json` und `token.json` sind dein Schlüssel zum Kanal: nicht weitergeben, nicht auf GitHub hochladen (ist per `.gitignore` gesperrt).

## Benutzen

### A) Mit dem Fenster
`start.bat` → Video und Thumbnail wählen, Titel, Beschreibung, Tags eintragen → **Prüfen** → **Hochladen**.
Am Ende stehen **Link öffnen** und **Link kopieren** bereit. Mit **Paket laden …** übernimmst du alle Felder aus einer `paket.json` (die erstellt Claude für dich).

### B) Im Hintergrund über die Warteschlange
1. `warteschlange_starten.bat` starten (Fenster offen lassen) – oder im Fenster **Warteschlange überwachen: an**.
2. Jede `*.json`-Datei, die im Ordner `warteschlange` landet, wird automatisch hochgeladen.
3. Danach liegt sie in `warteschlange/erledigt` mit einer `.link.txt` (Video-Link) – oder bei Problemen in `warteschlange/fehler` mit einer `.fehler.txt`.

Claude kann die `paket.json` direkt in den Ordner `warteschlange` legen, dann läuft der Upload ohne dein Zutun.

### C) Kommandozeile
```
uv run youtube_upload.py --paket beispiel\paket.json
uv run youtube_upload.py --video film.mp4 --titel "Mein Titel" --beschreibung-datei text.txt --tags "a, b" --thumbnail bild.png
uv run youtube_upload.py --paket paket.json --pruefen      (nur prüfen, nichts hochladen)
```

## Aufbau einer paket.json
```json
{
  "video": "C:/Pfad/zum/Video.mp4",
  "thumbnail": "C:/Pfad/zum/Thumbnail.png",
  "titel": "Max. 100 Zeichen, keine < >",
  "beschreibung": "Text mit Kapiteln\n0:00 Start\n0:38 Teil 2",
  "tags": "Tag1, Tag2, Tag3",
  "sichtbarkeit": "nicht gelistet",
  "fuer_kinder": false
}
```
Pfade dürfen auch relativ zur paket.json sein.

## Grenzen
- Titel max. 100 Zeichen, Beschreibung max. 5000 Bytes, Tags zusammen max. 500 Zeichen, kein `<` oder `>` – wird vor dem Upload geprüft.
- Thumbnail: PNG oder JPG, max. 2 MB, Kanal muss per Telefon bestätigt sein.
- Bis zu 100 Uploads pro Tag über die Schnittstelle.
- Der PC muss während des Uploads laufen. Bricht die Verbindung ab, versucht das Skript es automatisch erneut.
