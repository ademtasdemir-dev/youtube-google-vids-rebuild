"""Schritt 1 Video-Baukasten: PowerPoint -> Folienbilder (3840x2160) + Textzeilen mit Position.

  python folien.py Praesentation.pptx --von 7 --bis 12 --ziel arbeit/
Ergebnis: arbeit/folie-07.png ... und arbeit/folien.json (Zeilen je Folie, Koordinaten in 960x540-Punkten).
Braucht: LibreOffice (soffice) und Poppler (pdftoppm, pdftotext).
"""
import argparse, json, re, subprocess, tempfile
from pathlib import Path


def pptx_zu_pdf(pptx: Path, ziel: Path) -> Path:
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(ziel), str(pptx)],
                   check=True, capture_output=True)
    pdf = ziel / (pptx.stem + ".pdf")
    if not pdf.exists():
        raise SystemExit(f"PDF wurde nicht erzeugt: {pdf}")
    return pdf


def zeilen(pdf: Path, von: int, bis: int) -> dict:
    with tempfile.TemporaryDirectory() as t:
        html = Path(t) / "b.html"
        subprocess.run(["pdftotext", "-f", str(von), "-l", str(bis), "-bbox-layout", str(pdf), str(html)], check=True)
        h = html.read_text(encoding="utf-8")
    seiten = re.findall(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', h, re.S)
    out = {}
    for nr, (w, hh, body) in enumerate(seiten, von):
        sx, sy = 960 / float(w), 540 / float(hh)
        z = []
        for m in re.finditer(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', body, re.S):
            text = " ".join(re.findall(r">([^<]+)</word>", m.group(5)))
            z.append({"text": text, "box": [round(float(m.group(1)) * sx, 1), round(float(m.group(2)) * sy, 1),
                                            round(float(m.group(3)) * sx, 1), round(float(m.group(4)) * sy, 1)]})
        out[str(nr)] = z
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("pptx"); ap.add_argument("--von", type=int, required=True)
    ap.add_argument("--bis", type=int, required=True); ap.add_argument("--ziel", default="arbeit")
    a = ap.parse_args(argv)
    ziel = Path(a.ziel); ziel.mkdir(parents=True, exist_ok=True)
    pdf = pptx_zu_pdf(Path(a.pptx), ziel)
    subprocess.run(["pdftoppm", "-f", str(a.von), "-l", str(a.bis), "-scale-to-x", "3840", "-scale-to-y", "2160",
                    "-png", str(pdf), str(ziel / "folie")], check=True)
    # pdftoppm benennt je nach Seitenzahl folie-7.png oder folie-07.png -> vereinheitlichen
    for p in ziel.glob("folie-*.png"):
        n = int(p.stem.split("-")[1]); p.rename(ziel / f"folie-{n:02d}.png")
    (ziel / "folien.json").write_text(json.dumps(zeilen(pdf, a.von, a.bis), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fertig: {a.bis - a.von + 1} Folien in {ziel}")


if __name__ == "__main__":
    main()
