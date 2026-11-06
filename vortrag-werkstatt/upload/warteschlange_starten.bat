@echo off
cd /d "%~dp0"
echo Warteschlange wird ueberwacht. Dieses Fenster offen lassen. Beenden mit Strg+C.
uv run youtube_upload.py --warteschlange
pause
