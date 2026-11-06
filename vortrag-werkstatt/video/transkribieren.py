"""Hört die Audio-Datei ab und schreibt jedes gesprochene Wort mit Zeitstempel (lokal, ohne Cloud).

  uv run --with faster-whisper --with numpy transkribieren.py audio.wav --ziel arbeit/woerter.json

Damit richtet ausrichten.py die Lupe genau auf das aus, was WIRKLICH gesprochen wird.
"""
import argparse, json, subprocess, time
import numpy as np


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("audio"); ap.add_argument("--ziel", default="woerter.json")
    ap.add_argument("--modell", default="small"); a = ap.parse_args(argv)
    from faster_whisper import WhisperModel
    t = time.time()
    roh = subprocess.run(["ffmpeg", "-v", "error", "-i", a.audio, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    modell = WhisperModel(a.modell, device="cpu", compute_type="int8")
    segmente, _ = modell.transcribe(np.frombuffer(roh, np.float32), language="de", word_timestamps=True)
    woerter = [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for s in segmente for w in s.words]
    with open(a.ziel, "w", encoding="utf-8") as f:
        json.dump(woerter, f, ensure_ascii=False)
    print(f"{len(woerter)} Wörter in {round(time.time() - t)} s -> {a.ziel}")


if __name__ == "__main__":
    main()
