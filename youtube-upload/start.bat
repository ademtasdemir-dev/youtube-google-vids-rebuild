@echo off
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo uv wurde nicht gefunden. Bitte zuerst nightcut installieren oder uv installieren: https://docs.astral.sh/uv/
  pause
  exit /b 1
)
uv run app.py
if errorlevel 1 pause
