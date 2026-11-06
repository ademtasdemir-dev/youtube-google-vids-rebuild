"""Schritt 2 Video-Baukasten: Drehbuch + Audio -> Zeitplan (wann welche Folie, wann welcher Punkt).

  python ausrichten.py drehbuch.json audio.wav --woerter arbeit/woerter.json --ziel arbeit/zeitplan.json

Empfohlen: zuerst transkribieren.py laufen lassen und --woerter angeben. Dann wird jeder Anker im
tatsächlich Gesprochenen gesucht (genau). Ohne --woerter wird nur geschätzt (Silben + Pausen) – ungenau.

drehbuch.json:
{
  "text": "kompletter gesprochener Text (Lesefassung)",
  "folien": [
    {"nr": 7, "start": "Danke dir, Marcel",            <- erster Satzanfang der Folie
     "punkte": [{"anker": "Wir haben 20", "box": [70,134,560,166]}, ...]}   <- Satzanfang + Bereich (960x540)
  ]
}
Verfahren: Silben-Anteil jedes Ankers im Text -> Sprechzeit ohne Pausen -> echte Zeit; danach Einrasten
auf das Ende der nächstgelegenen Sprechpause (max. 2,5 s Abstand).
"""
import argparse, json, re, subprocess
from pathlib import Path


def silben(t: str) -> int:
    t = t.lower()
    for a, b in (("nas", "naas"), ("ssd", "es es de"), ("dhcp", "de ha ze pe"), ("usv", "u es vau"),
                 ("cad", "käd"), ("raid", "räid"), ("vlan", "wi lan"), ("vpn", "vau pe en")):
        t = t.replace(a, b)
    t = re.sub(r"\d+", lambda m: " zahl " * max(1, len(m.group())), t)
    return len(re.findall(r"[aeiouäöüy]+", t))


def pausen(wav: str, db: int = -40, dauer: float = 0.25):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", wav, "-af", f"silencedetect=n={db}dB:d={dauer}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(s, e))


def laenge(wav: str) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                                capture_output=True, text=True).stdout)


def _norm(t: str) -> list[str]:
    t = t.lower().replace("ß", "ss")
    t = re.sub(r"[^\wäöü]+", " ", t)
    return t.split()


def anker_in_woertern(anker: str, woerter: list, ab: int = 0):
    """Sucht den Anker (Satzanfang) in der Wortliste ab Position ab. Gibt (index, startzeit) oder None zurück."""
    from difflib import SequenceMatcher
    ziel = _norm(anker)
    if not ziel:
        return None
    # Wörter normalisieren; "2,5" wird zu "2" "5" – Index aufs Originalwort merken
    flach, idx = [], []
    for i, w in enumerate(woerter):
        for teil in _norm(w["w"]):
            flach.append(teil); idx.append(i)
    n = len(ziel); bester = (0.0, None)
    for j in range(len(flach)):
        if idx[j] < ab:
            continue
        r = SequenceMatcher(None, ziel, flach[j:j + n]).ratio()
        if r > bester[0] + 1e-9:
            bester = (r, j)
        if r == 1.0:
            break
    if bester[1] is None or bester[0] < 0.6:
        return None
    i = idx[bester[1]]
    return i, woerter[i]["s"]


def zeitplan_aus_woertern(drehbuch: dict, woerter: list, dur: float, log=print) -> dict:
    folien, pos = [], 0
    for f in drehbuch["folien"]:
        r = anker_in_woertern(f["start"], woerter, pos)
        if r is None:
            raise SystemExit(f"Folienanfang nicht gefunden: {f['start']!r} (Folie {f['nr']})")
        pos, start = r
        punkte = []
        for p in f["punkte"]:
            r = anker_in_woertern(p["anker"], woerter, pos)
            if r is None:
                raise SystemExit(f"Anker nicht gefunden: {p['anker']!r} (Folie {f['nr']})")
            pos, t = r
            punkte.append({"anker": p["anker"], "box": p["box"], "t": t})
        folien.append({"nr": f["nr"], "start": 0.0 if not folien else start, "punkte": punkte})
    for i in range(1, len(folien)):  # Folienwechsel mittig in der Pause vor dem ersten Wort
        s = folien[i]["start"]
        vorher = max((w["e"] for w in woerter if w["e"] <= s + 0.01), default=s)
        folien[i]["start"] = round((vorher + s) / 2, 2)
    for i, f in enumerate(folien):
        f["ende"] = folien[i + 1]["start"] if i + 1 < len(folien) else round(dur, 2)
        for j, p in enumerate(f["punkte"]):
            p["ende"] = f["punkte"][j + 1]["t"] if j + 1 < len(f["punkte"]) else f["ende"]
            p["t"] = max(p["t"], f["start"])
    return {"dauer": round(dur, 2), "verfahren": "woerter", "folien": folien}


def zeitplan(drehbuch: dict, sil: list, dur: float) -> dict:
    text = " ".join(drehbuch["text"].split())
    sprech, t = [], 0.0
    for a, b in sil:
        if a > t: sprech.append((t, a))
        t = b
    if t < dur: sprech.append((t, dur))
    gesamt = sum(b - a for a, b in sprech); ges_silben = silben(text)

    def real(x):
        acc = 0.0
        for a, b in sprech:
            if acc + (b - a) >= x: return a + (x - acc)
            acc += b - a
        return dur

    def finde(anker):
        i = text.find(" ".join(anker.split()))
        if i < 0: raise SystemExit(f"Anker nicht im Text gefunden: {anker!r}")
        est = real(silben(text[:i]) / ges_silben * gesamt)
        nah = [b for a, b in sil if abs(b - est) < 2.5]
        return round(min(nah, key=lambda b: abs(b - est)) if nah else est, 2), round(est, 2)

    folien = []
    for f in drehbuch["folien"]:
        start = 0.0 if not folien else finde(f["start"])[0]
        punkte = [{"anker": p["anker"], "box": p["box"], "t": finde(p["anker"])[0]} for p in f["punkte"]]
        folien.append({"nr": f["nr"], "start": start, "punkte": punkte})
    # Folienwechsel kurz vor dem ersten Wort der neuen Folie (Mitte der Pause davor)
    for i in range(1, len(folien)):
        s = folien[i]["start"]
        davor = [p for p in sil if abs(p[1] - s) < 0.05]
        folien[i]["start"] = round((davor[0][0] + davor[0][1]) / 2, 2) if davor else round(max(0, s - 0.3), 2)
    for i, f in enumerate(folien):
        f["ende"] = folien[i + 1]["start"] if i + 1 < len(folien) else round(dur, 2)
        for j, p in enumerate(f["punkte"]):
            p["ende"] = f["punkte"][j + 1]["t"] if j + 1 < len(f["punkte"]) else f["ende"]
            p["t"] = max(p["t"], f["start"])
    return {"dauer": round(dur, 2), "folien": folien}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("drehbuch"); ap.add_argument("audio"); ap.add_argument("--ziel", default="zeitplan.json")
    ap.add_argument("--woerter", help="Ausgabe von transkribieren.py (empfohlen)")
    a = ap.parse_args(argv)
    d = json.loads(Path(a.drehbuch).read_text(encoding="utf-8"))
    if a.woerter:
        z = zeitplan_aus_woertern(d, json.loads(Path(a.woerter).read_text(encoding="utf-8")), laenge(a.audio))
    else:
        print("Hinweis: ohne --woerter nur Schätzung. Für genaue Zeiten transkribieren.py nutzen.")
        z = zeitplan(d, pausen(a.audio), laenge(a.audio))
    Path(a.ziel).write_text(json.dumps(z, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in z["folien"]:
        print(f"Folie {f['nr']}: {f['start']:7.2f}–{f['ende']:7.2f} s, {len(f['punkte'])} Punkte")


if __name__ == "__main__":
    main()
