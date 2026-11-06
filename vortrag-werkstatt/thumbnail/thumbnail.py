"""Thumbnail-Baukasten: baut ein YouTube-Titelbild (1280x720) aus einer kleinen JSON-Datei und PRÜFT es automatisch.

  python thumbnail.py thumbnail.json --ziel Thumbnail.png

thumbnail.json:
{
  "oberzeile": "IT-INFRASTRUKTUR · ARCHITEKTURBÜRO",
  "titel_weiss": "NETZWERK", "titel_gelb": "& BACKUP",
  "untertitel": "einfach erklärt",
  "chips": ["VLANs", "RAID 6", "10 Gbit", "Firewall"],      <- abwechselnd rot / weiß
  "folie": "arbeit/folie-08.png",                             <- echte Folie (Bild)
  "lupe_text": "Wichtig: Ein RAID ist kein Backup!",          <- ODER lupe_bild + lupe_ausschnitt
  "lupe_unterstrichen": "kein Backup!",
  "lupe_bild": "arbeit/folie-08.png", "lupe_ausschnitt": [58,178,378,212],   (Folienpunkte 960x540)
  "hintergrund": "blau"                                       <- "blau" (Standard) oder "schwarz"
}
Prüfung (bricht mit Fehler ab, statt ein fehlerhaftes Bild zu liefern):
- Überschrift, Untertitel und Chips überlappen nicht mit Folie oder Lupe
- Folie und Lupe liegen komplett im Bild, Lupe verdeckt die Folie nicht
- kein Text läuft aus seinem Kasten heraus
Braucht: Python-Paket playwright (Chromium) und Pillow.
"""
import argparse, base64, html, io, json, sys
from pathlib import Path
from PIL import Image, ImageDraw

HINTERGRUND = {
    "blau": "linear-gradient(135deg,#0b1d2b 0%,#0d2a3a 55%,#0f3a45 100%)",
    "schwarz": "#050607",
}


def data_uri(img: Image.Image) -> str:
    b = io.BytesIO(); img.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def baue_html(c: dict, basis: Path) -> str:
    folie = Image.open(basis / c["folie"]).convert("RGB").resize((1600, 900))
    if c.get("lupe_bild"):
        g = Image.open(basis / c["lupe_bild"]).convert("RGB").resize((3840, 2160))
        x0, y0, x1, y1 = c["lupe_ausschnitt"]
        crop = g.crop((int(x0 * 4), int(y0 * 4), int(x1 * 4), int(y1 * 4)))
        d = ImageDraw.Draw(crop); d.line([(10, crop.height - 16), (crop.width - 10, crop.height - 16)], fill=(229, 57, 53), width=12)
        lupe = f'<img src="{data_uri(crop)}" alt="">'
    else:
        t = html.escape(c["lupe_text"]); u = html.escape(c.get("lupe_unterstrichen", ""))
        lupe = t.replace(u, f"<u>{u}</u>", 1) if u and u in t else t
    chips = "".join(f'<div class="chip{" alt" if i % 2 else ""}">{html.escape(x)}</div>' for i, x in enumerate(c.get("chips", [])))
    bg = HINTERGRUND.get(c.get("hintergrund", "blau"), HINTERGRUND["blau"])
    return f"""<html><head><meta charset="utf-8"><style>
*{{margin:0;box-sizing:border-box}}
body{{width:1280px;height:720px;overflow:hidden;font-family:"Inter Display","Inter","Segoe UI",sans-serif;background:{bg};position:relative}}
.glow{{position:absolute;right:-220px;top:-220px;width:1050px;height:1050px;background:radial-gradient(circle,rgba(79,179,169,.42),transparent 62%)}}
.slide{{position:absolute;right:22px;top:110px;width:530px;transform:rotate(-4deg);border-radius:14px;box-shadow:0 30px 70px rgba(0,0,0,.6);border:6px solid #fff}}
.lens{{position:absolute;right:40px;top:520px;max-width:660px;background:#fff;border:5px solid #111;border-radius:30px;padding:18px 26px;box-shadow:0 24px 50px rgba(0,0,0,.6);transform:rotate(-4deg);font-weight:700;font-size:40px;color:#111;white-space:nowrap}}
.lens img{{width:600px;display:block}}
.lens u{{text-decoration:none;border-bottom:7px solid #e53935;padding-bottom:2px}}
.left{{position:absolute;left:56px;top:70px;width:640px}}
.eyebrow{{color:#4fb3a9;font-weight:800;letter-spacing:.14em;font-size:24px}}
h1{{color:#fff;font-weight:900;font-size:108px;line-height:.95;margin-top:18px;letter-spacing:-.02em}}
h1 span{{color:#ffd34d;display:block}}
.sub{{color:#dfe8ee;font-size:34px;font-weight:700;margin-top:18px}}
.chips{{display:flex;flex-wrap:wrap;gap:12px;margin-top:30px;width:560px}}
.chip{{background:#e53935;color:#fff;font-weight:900;font-size:30px;padding:8px 18px;border-radius:10px}}
.chip.alt{{background:#fff;color:#0f2a3d}}
</style></head><body>
<div class="glow"></div>
<img class="slide" src="{data_uri(folie)}" alt="">
<div class="lens">{lupe}</div>
<div class="left">
 <div class="eyebrow">{html.escape(c.get("oberzeile", ""))}</div>
 <h1><b class="w">{html.escape(c["titel_weiss"])}</b><span>{html.escape(c.get("titel_gelb", ""))}</span></h1>
 <div class="sub">{html.escape(c.get("untertitel", ""))}</div>
 <div class="chips">{chips}</div>
</div></body></html>"""


PRUEF_JS = r"""() => {
  const box = el => { const r = el.getBoundingClientRect(); return {l:r.left,t:r.top,r:r.right,b:r.bottom}; };
  const text = el => { const rg = document.createRange(); rg.selectNodeContents(el); const r = rg.getBoundingClientRect(); return {l:r.left,t:r.top,r:r.right,b:r.bottom}; };
  const hit = (a,b) => !(a.r <= b.l || b.r <= a.l || a.b <= b.t || b.b <= a.t);
  const fehler = [];
  const slide = box(document.querySelector('.slide')), lens = box(document.querySelector('.lens'));
  const links = [...document.querySelectorAll('.eyebrow,.w,h1 span,.sub,.chip')].map(e => [e.className || e.tagName, text(e)]);
  for (const [n,b] of links) { if (hit(b,slide)) fehler.push(n+' überlappt Folie'); if (hit(b,lens)) fehler.push(n+' überlappt Lupe'); }
  for (const [n,b] of [['Folie',slide],['Lupe',lens]]) if (b.l < 0 || b.t < 0 || b.r > 1280 || b.b > 720) fehler.push(n+' ragt aus dem Bild');
  if (hit(slide, lens)) fehler.push('Lupe verdeckt die Folie');
  for (const e of document.querySelectorAll('.chip,.lens,.eyebrow,.sub')) if (e.scrollWidth > e.clientWidth + 1) fehler.push((e.className)+' Text läuft über');
  return fehler;
}"""


def rendern(c: dict, basis: Path, ziel: Path) -> list:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); s = b.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
        s.set_content(baue_html(c, basis)); s.wait_for_timeout(300)
        fehler = s.evaluate(PRUEF_JS)
        s.screenshot(path=str(ziel)); b.close()
    return fehler


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("konfig"); ap.add_argument("--ziel", default="Thumbnail.png")
    a = ap.parse_args(argv)
    k = Path(a.konfig); c = json.loads(k.read_text(encoding="utf-8"))
    fehler = rendern(c, k.resolve().parent, Path(a.ziel))
    if fehler:
        print("Thumbnail NICHT in Ordnung:\n- " + "\n- ".join(fehler), file=sys.stderr); return 1
    print(f"Thumbnail geprüft und gespeichert: {a.ziel} ({Path(a.ziel).stat().st_size // 1024} KB)"); return 0


if __name__ == "__main__":
    sys.exit(main())
