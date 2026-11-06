"""Schritt 3 Video-Baukasten: Zeitplan + Folienbilder + Audio -> Video mit Klick-Lupe.

  python render_lupe.py arbeit/zeitplan.json arbeit/ audio.wav --ziel Vortrag.mp4

Stil (fest eingestellt, so wie im Projekt Folie 7–12 abgenommen):
- 1920x1080, 25 fps, harte Schnitte zwischen den Folien, Ton durchgehend
- pro Punkt: Maus fährt EINMAL hin (0,5 s), Klick (roter Kreis), Punkt rot unterstrichen,
  Lupe (weißes Fenster, schwarzer Rand, Schatten) mit dem Punkt vergrößert, Rest der Folie bleibt sichtbar
- Lupe zeigt den Punkt immer in voller Breite (kein abgeschnittener Text), max. 1840 px breit, Zoom max. 1,9
"""
import argparse, json, subprocess, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

FPS, W, H = 25, 1920, 1080
ROT = (229, 57, 53)
MOVE, POP = 0.5, 0.25


def ease(t):
    t = max(0., min(1., t)); return t * t * (3 - 2 * t)


def cursor(d, x, y):
    s = 1.7; form = [(0, 0), (0, 25), (6, 19), (11, 30), (15, 28), (10, 17.5), (18, 17.5)]
    d.polygon([(x + px * s, y + py * s) for px, py in form], fill=(255, 255, 255), outline=(20, 20, 20), width=3)


def lupe(gross, basis, r):
    x0, y0, x1, y1 = r
    b4 = gross.copy(); ImageDraw.Draw(b4).line([(x0 * 4, y1 * 4 + 6), (x1 * 4, y1 * 4 + 6)], fill=ROT, width=10)
    f = basis.copy(); ImageDraw.Draw(f).line([(x0 * 2, y1 * 2 + 3), (x1 * 2, y1 * 2 + 3)], fill=ROT, width=5)
    cw = min(x1 - x0 + 20, 920); ch = (y1 - y0) + 16  # immer ganze Breite: kein abgeschnittener Text
    cx0 = max(0, x0 - 10); cy0 = max(0, y0 - 6)
    m = min(1840 / (cw * 2), 560 / (ch * 2), 1.9)
    lw, lh = int(cw * 2 * m), int(ch * 2 * m)
    crop = b4.crop((int(cx0 * 4), int(cy0 * 4), int((cx0 + cw) * 4), int((cy0 + ch) * 4))).resize((lw, lh), Image.LANCZOS)
    pad = 18; L = Image.new("RGBA", (lw + 2 * pad, lh + 2 * pad), (0, 0, 0, 0))
    maske = Image.new("L", L.size, 0); ImageDraw.Draw(maske).rounded_rectangle((0, 0, L.size[0] - 1, L.size[1] - 1), radius=46, fill=255)
    karte = Image.new("RGBA", L.size, (255, 255, 255, 255)); karte.paste(crop, (pad, pad)); L.paste(karte, (0, 0), maske)
    ImageDraw.Draw(L).rounded_rectangle((1, 1, L.size[0] - 2, L.size[1] - 2), radius=46, outline=(25, 25, 25, 255), width=4)
    mx = (x0 + x1) / 2 * 2; oben = y1 * 2 + 26
    lx = int(min(max(mx - L.size[0] / 2, 40), W - 40 - L.size[0]))
    if oben + L.size[1] > H - 30: oben = y0 * 2 - 26 - L.size[1]
    ly = int(min(max(oben, 30), H - 30 - L.size[1]))
    ziel = (x0 * 2 + min(160, (x1 - x0)), (y0 + y1) / 2 * 2)
    sch = Image.new("RGBA", (L.size[0] + 60, L.size[1] + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sch).rounded_rectangle((30, 36, 30 + L.size[0], 36 + L.size[1]), radius=46, fill=(0, 0, 0, 90))
    return f, L, (lx, ly), ziel, sch.filter(ImageFilter.GaussianBlur(14))


def folie_rendern(args):
    bild, folie, out = args
    dur = folie["ende"] - folie["start"]; s0 = folie["start"]
    gross = Image.open(bild).convert("RGB").resize((3840, 2160)); basis = gross.resize((W, H), Image.LANCZOS)
    cues = [(p["t"] - s0, p["ende"] - s0, lupe(gross, basis, p["box"])) for p in folie["punkte"]]
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    ruhe = (1750.0, 990.0); pos = ruhe; von = ruhe; akt = -1; t_wechsel = 0
    for i in range(int(round(dur * FPS))):
        t = i / FPS
        k = next((j for j, (a, b, _) in enumerate(cues) if a <= t < b), -1)
        if k != akt: von = pos; akt = k; t_wechsel = t
        if k >= 0:
            _, _, (f, L, (lx, ly), ziel, sch) = cues[k]
            e = ease((t - t_wechsel) / MOVE)
            pos = (von[0] + (ziel[0] - von[0]) * e, von[1] + (ziel[1] - von[1]) * e)
            lt = t - t_wechsel - MOVE
            img = (f if lt >= 0 else basis).copy()
            if lt >= 0:
                p = ease(lt / POP); sc = 0.85 + 0.15 * p
                Ls = L if p >= 1 else L.resize((max(1, int(L.size[0] * sc)), max(1, int(L.size[1] * sc))))
                if p < 1:
                    Ls = Ls.copy(); Ls.putalpha(Ls.split()[3].point(lambda v: int(v * p)))
                else:
                    img.paste(sch, (lx - 30, ly - 30), sch)
                img.paste(Ls, (lx + (L.size[0] - Ls.size[0]) // 2, ly + (L.size[1] - Ls.size[1]) // 2), Ls)
            d = ImageDraw.Draw(img)
            if 0 <= lt < 0.35:
                rr = 10 + 40 * (lt / 0.35); d.ellipse((pos[0] - rr, pos[1] - rr, pos[0] + rr, pos[1] + rr), outline=ROT, width=4)
        else:
            img = basis.copy(); d = ImageDraw.Draw(img)
        cursor(d, pos[0], pos[1]); ff.stdin.write(img.tobytes())
    ff.stdin.close(); ff.wait()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("zeitplan"); ap.add_argument("folien_ordner"); ap.add_argument("audio")
    ap.add_argument("--ziel", default="Vortrag.mp4"); a = ap.parse_args(argv)
    z = json.loads(Path(a.zeitplan).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [(str(Path(a.folien_ordner) / f"folie-{f['nr']:02d}.png"), f, str(Path(tmp) / f"s{f['nr']:02d}.mp4")) for f in z["folien"]]
        with ProcessPoolExecutor() as ex:
            teile = list(ex.map(folie_rendern, jobs))
        liste = Path(tmp) / "liste.txt"; liste.write_text("".join(f"file '{t}'\n" for t in teile))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(liste), "-i", a.audio, "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.ziel], check=True)
    print(f"Fertig: {a.ziel}")


if __name__ == "__main__":
    main()
