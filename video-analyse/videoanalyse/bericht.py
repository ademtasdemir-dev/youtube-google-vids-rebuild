"""Ausgaben: Transkript (SRT, VTT, TXT, Markdown, JSON), Strukturplan als Markdown, Upload-Paket."""
import json

from .zeit import hms, srt_zeit, vtt_zeit


def srt(zeilen, sprecher=True) -> str:
    out = []
    for i, z in enumerate(zeilen, 1):
        ende = z["ende"] if z["ende"] > z["start"] else z["start"] + 2
        pre = f"[{z['sprecher']}] " if sprecher else ""
        out.append(f"{i}\n{srt_zeit(z['start'])} --> {srt_zeit(ende)}\n{pre}{z['text']}\n")
    return "\n".join(out)


def vtt(zeilen, sprecher=True) -> str:
    out = ["WEBVTT", ""]
    for z in zeilen:
        ende = z["ende"] if z["ende"] > z["start"] else z["start"] + 2
        txt = f"<v {z['sprecher']}>{z['text']}" if sprecher else z["text"]
        out += [f"{vtt_zeit(z['start'])} --> {vtt_zeit(ende)}", txt, ""]
    return "\n".join(out)


def txt(zeilen) -> str:
    return "\n".join(f"[{hms(z['start'])} – {hms(z['ende'])}] {z['sprecher']}: {z['text']}" for z in zeilen)


def nur_sprecher(zeilen, sprecher) -> str:
    return "\n".join(f"[{hms(z['start'])}] {z['text']}" for z in zeilen if z["sprecher"] == sprecher)


def youtube_beschreibung(einleitung: str, kapitel: list[dict]) -> str:
    zeilen = [f"{hms(k['start'])} {k['titel']}" for k in kapitel]
    if zeilen and not zeilen[0].startswith("0:00"):
        zeilen.insert(0, "0:00 Start")
    return (einleitung.strip() + "\n\nKapitel:\n" + "\n".join(zeilen)).strip()


def kapitel_pruefen(kapitel: list[dict]) -> list[str]:
    """YouTube-Regeln für anklickbare Kapitel."""
    h = []
    if not kapitel or kapitel[0]["start"] > 0.5:
        h.append("Erstes Kapitel muss bei 0:00 beginnen.")
    if len(kapitel) < 3:
        h.append("YouTube braucht mindestens 3 Kapitel.")
    for a, b in zip(kapitel, kapitel[1:]):
        if b["start"] - a["start"] < 10:
            h.append(f"Kapitel „{a['titel']}“ ist kürzer als 10 Sekunden.")
        if b["start"] <= a["start"]:
            h.append("Kapitel sind nicht aufsteigend sortiert.")
    return h


def markdown(e: dict) -> str:
    i, k, z = e["info"], e["kennzahlen"], e.get("zusammenfassung", {})
    md = [f"# {i.get('title') or 'Video'}", "",
          f"- **Kanal:** {i.get('uploader') or '–'}", f"- **Link:** {i.get('webpage_url') or '–'}",
          f"- **Länge:** {hms(k['dauer'])}  ·  **Sprecher:** {len(e['sprecher'])}  ·  **Kapitel:** {len(e['kapitel'])}",
          f"- **Analyse:** {e['analyse_art']}  ·  **Kapitelquelle:** {e['kapitel_quelle']}", "",
          "## 1. Zusammenfassung", "", z.get("kurz", ""), ""]
    if z.get("ausfuehrlich"):
        md += [z["ausfuehrlich"], ""]
    if z.get("kernaussagen"):
        md += ["**Kernaussagen**", ""] + [f"- {x}" for x in z["kernaussagen"]] + [""]
    if z.get("zielgruppe"):
        md += [f"**Zielgruppe:** {z['zielgruppe']}", ""]
    md += [f"**Schlagwörter:** {', '.join(e.get('schlagwoerter', []))}", "",
           "## 2. Strukturplan", "", "| Zeit | Phase | Kapitel | Inhalt | Bild / Darstellung | Wörter/Min. |", "|---|---|---|---|---|---|"]
    for c in e["kapitel"]:
        inhalt = (c.get("inhalt") or c["text"][:220] + ("…" if len(c["text"]) > 220 else "")).replace("|", "/").replace("\n", " ")
        vis = (c.get("visuell") or c["bildart"]).replace("|", "/").replace("\n", " ")
        md.append(f"| {hms(c['start'])}–{hms(c['ende'])} | {c['phase']} | {c['titel']} | {inhalt} | {vis} | {c['wpm']} |")
    md += ["", "## 3. Aufbau und Darstellung", "", f"- {e['tempo']}"]
    for art, sek in e["bild"]["bildarten"].items():
        md.append(f"- {art}: {hms(sek)} ({round(100 * sek / max(k['dauer'], 1))} %)")
    for titel, schl in (("Darstellung", "darstellung"), ("Dramaturgie", "dramaturgie")):
        if e.get(schl):
            md += ["", f"**{titel}**", ""] + [f"- **{a.replace('_', ' ').capitalize()}:** {b}" for a, b in e[schl].items()]
    md += ["", "## 4. Bilder im Video", "", "| Nr. | Zeit | Bildart | Beschreibung | Text im Bild |", "|---|---|---|---|---|"]
    for s in e["bild"]["szenen"]:
        md.append(f"| {s['nr']} | {hms(s['start'])}–{hms(s['ende'])} | {s.get('bildtyp') or s['bildart']} | "
                  f"{(s.get('beschreibung') or '–').replace('|', '/')} | {(s.get('text_im_bild') or '').replace('|', '/')} |")
    md += ["", "## 5. Sprecher", ""]
    for s in e["sprecher"]:
        rolle = f" – {s['rolle']}" if s.get("rolle") else ""
        md.append(f"- **{s['sprecher']}**{rolle}: {s['anteil']} % Redeanteil, {s['woerter']} Wörter")
    if e.get("titel_vorschlaege"):
        md += ["", "## 6. Titel-Vorschläge", ""] + [f"- {t}" for t in e["titel_vorschlaege"]]
    if e.get("verbesserungen"):
        md += ["", "## 7. Verbesserungsideen", ""] + [f"- {t}" for t in e["verbesserungen"]]
    md += ["", "## Transkript", "", "```", txt(e["zeilen"]), "```", ""]
    return "\n".join(md)


def upload_paket(e: dict, video_pfad: str = "", thumbnail: str = "") -> dict:
    i = e["info"]
    einl = e.get("zusammenfassung", {}).get("kurz") or (i.get("description") or "").split("\n")[0]
    return {"video": video_pfad, "thumbnail": thumbnail, "titel": (i.get("title") or "")[:100],
            "beschreibung": youtube_beschreibung(einl, e["kapitel"]),
            "tags": ", ".join((i.get("tags") or e.get("schlagwoerter", []))[:15]),
            "sichtbarkeit": "nicht gelistet", "fuer_kinder": False, "aufraeumen": True, "loeschen": [], "arbeitsordner": None}


def als_json(e: dict) -> str:
    return json.dumps(e, ensure_ascii=False, indent=1)
