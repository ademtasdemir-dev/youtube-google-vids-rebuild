"""Teleprompter-Baukasten: Lesetext -> fertige Teleprompter-Seite (HTML, funktioniert offline).

  python baue_prompter.py lesetext.json --ziel Prompter.html --titel "Prompter Folie 7–12"

lesetext.json:  [["Folie 7", "Text der Folie ..."], ["Folie 8", "..."]]
Eingestellt (wie abgenommen): Wort-für-Wort-Markierung, Atempausen Komma 0,35 s, Doppelpunkt 0,5 s,
Punkt 0,8 s, Folienende 2 s, Start-Tempo 150 W/min, Leertaste Start/Pause, Klick aufs Wort springt,
Restzeit-Anzeige, hell/dunkel.
"""
import argparse, json, html
from pathlib import Path

VORLAGE = Path(__file__).with_name("vorlage.html")


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("lesetext"); ap.add_argument("--ziel", default="Prompter.html")
    ap.add_argument("--titel", default="Teleprompter"); a = ap.parse_args(argv)
    folien = json.loads(Path(a.lesetext).read_text(encoding="utf-8"))
    if not (isinstance(folien, list) and all(isinstance(f, list) and len(f) == 2 for f in folien)):
        raise SystemExit('lesetext.json muss so aussehen: [["Folie 7", "Text …"], …]')
    s = VORLAGE.read_text(encoding="utf-8")
    s = s.replace("/*FOLIEN*/[]", json.dumps(folien, ensure_ascii=False).replace("</", "<\\/"))
    s = s.replace("/*TITEL*/", html.escape(a.titel))
    Path(a.ziel).write_text(s, encoding="utf-8")
    woerter = sum(len(t.split()) for _, t in folien)
    print(f"Teleprompter gespeichert: {a.ziel} ({len(folien)} Folien, {woerter} Wörter)")


if __name__ == "__main__":
    main()
