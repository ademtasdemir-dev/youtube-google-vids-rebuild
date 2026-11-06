"""Tests Video-Baukasten. Start: python -m pytest -q"""
import json, subprocess, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import ausrichten as au

W = [{"w": w, "s": i * 0.5, "e": i * 0.5 + 0.4} for i, w in enumerate(
    "Ja, danke dir. Wir haben 20 Arbeitsplätze. So, zum Schluss. Bei 2 ,5 Gigabit sind es fünf Minuten. Bei einem Gigabit sind wir".split())]


def test_anker_exakt_und_reihenfolge():
    i, t = au.anker_in_woertern("Wir haben 20", W)
    assert W[i]["w"] == "Wir" and t == W[i]["s"]


def test_anker_mit_komma_zahl():
    i, _ = au.anker_in_woertern("Bei 2,5 Gigabit", W)
    assert W[i]["w"] == "Bei" and W[i + 1]["w"] == "2"


def test_anker_unscharf():
    assert au.anker_in_woertern("wir haben zwanzig Arbeitsplätze", W) is not None  # 3 von 4 Wörtern


def test_anker_ab_position():
    i1, _ = au.anker_in_woertern("Bei", W)
    i2, _ = au.anker_in_woertern("Bei einem Gigabit", W, ab=i1 + 1)
    assert i2 > i1


def test_anker_fehlt():
    assert au.anker_in_woertern("Völlig anderer Satz hier", W) is None


def test_zeitplan_aus_woertern():
    d = {"folien": [{"nr": 1, "start": "Ja danke dir", "punkte": [{"anker": "Wir haben 20", "box": [0, 0, 10, 10]}]},
                    {"nr": 2, "start": "So zum Schluss", "punkte": [{"anker": "Bei 2,5 Gigabit", "box": [0, 0, 10, 10]},
                                                                    {"anker": "Bei einem Gigabit", "box": [0, 0, 10, 10]}]}]}
    z = au.zeitplan_aus_woertern(d, W, 20.0)
    f1, f2 = z["folien"]
    assert f1["start"] == 0 and f1["ende"] == f2["start"] and f2["ende"] == 20.0
    assert f1["punkte"][0]["t"] < f2["start"] <= f2["punkte"][0]["t"] < f2["punkte"][1]["t"]
    assert f2["punkte"][0]["ende"] == f2["punkte"][1]["t"]


def test_fehlender_anker_bricht_ab():
    d = {"folien": [{"nr": 1, "start": "Ja danke", "punkte": [{"anker": "gibt es nicht im Text", "box": [0, 0, 1, 1]}]}]}
    with pytest.raises(SystemExit, match="nicht gefunden"):
        au.zeitplan_aus_woertern(d, W, 10.0)


def test_render_kurz(tmp_path):
    """Rendert 2 Sekunden mit einem Punkt und prüft Länge und Auflösung."""
    from PIL import Image
    import render_lupe as rl
    Image.new("RGB", (3840, 2160), "white").save(tmp_path / "folie-01.png")
    z = {"dauer": 2.0, "folien": [{"nr": 1, "start": 0.0, "ende": 2.0, "punkte": [{"anker": "x", "box": [70, 134, 560, 166], "t": 0.2, "ende": 2.0}]}]}
    (tmp_path / "z.json").write_text(json.dumps(z))
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2", str(tmp_path / "a.wav")], check=True)
    rl.main([str(tmp_path / "z.json"), str(tmp_path), str(tmp_path / "a.wav"), "--ziel", str(tmp_path / "v.mp4")])
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration", "-of", "json", str(tmp_path / "v.mp4")],
                          capture_output=True, text=True).stdout
    j = json.loads(info)
    assert j["streams"][0]["width"] == 1920 and j["streams"][0]["height"] == 1080
    assert abs(float(j["format"]["duration"]) - 2.0) < 0.2
