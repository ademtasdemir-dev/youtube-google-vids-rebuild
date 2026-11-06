"""Automatischer YouTube-Upload – Oberfläche. Start: Doppelklick auf start.bat"""
from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import youtube_upload as yu

BG, FG, AKZENT, FELD = "#f4f6f8", "#17202a", "#1f6f8b", "#ffffff"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Automatischer YouTube-Upload")
        self.geometry("760x780")
        self.minsize(640, 640)
        self.configure(bg=BG)
        self.q: queue.Queue = queue.Queue()
        self.link = ""
        self.ueberwachung = False
        self._stil()
        self._aufbau()
        self.after(150, self._queue_lesen)
        self._anmeldestatus()

    # ---------- Oberfläche ----------
    def _stil(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
        s.configure("TLabel", background=BG)
        s.configure("Kopf.TLabel", font=("Segoe UI", 16, "bold"))
        s.configure("Klein.TLabel", foreground="#5d6b78", font=("Segoe UI", 9))
        s.configure("TButton", padding=6)
        s.configure("Haupt.TButton", padding=(14, 8), font=("Segoe UI", 11, "bold"), foreground="#ffffff", background=AKZENT)
        s.map("Haupt.TButton", background=[("active", "#185a71"), ("disabled", "#9bb7c2")])
        s.configure("TCheckbutton", background=BG)
        s.configure("Horizontal.TProgressbar", background=AKZENT, troughcolor="#e3e8ec")

    def _aufbau(self):
        r = ttk.Frame(self, padding=18)
        r.pack(fill="both", expand=True)
        r.columnconfigure(1, weight=1)
        ttk.Label(r, text="Automatischer YouTube-Upload", style="Kopf.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.status_anmeldung = ttk.Label(r, text="", style="Klein.TLabel")
        self.status_anmeldung.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Button(r, text="Anmelden", command=self.anmelden).grid(row=1, column=2, sticky="e", pady=(0, 10))

        self.video = tk.StringVar(); self.thumb = tk.StringVar(); self.titel = tk.StringVar()
        self.tags = tk.StringVar(); self.sicht = tk.StringVar(value="nicht gelistet"); self.kinder = tk.BooleanVar(value=False)

        def zeile(i, text, var, knopf=None):
            ttk.Label(r, text=text).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 10))
            e = ttk.Entry(r, textvariable=var); e.grid(row=i, column=1, sticky="ew", pady=4)
            if knopf:
                ttk.Button(r, text="Wählen …", command=knopf).grid(row=i, column=2, padx=(8, 0))
            return e

        zeile(2, "Video", self.video, self.video_waehlen)
        zeile(3, "Thumbnail", self.thumb, self.thumb_waehlen)
        zeile(4, "Titel", self.titel)
        self.titel_info = ttk.Label(r, text="0 / 100", style="Klein.TLabel"); self.titel_info.grid(row=4, column=2, sticky="w", padx=(8, 0))
        self.titel.trace_add("write", lambda *_: self.titel_info.config(text=f"{len(self.titel.get())} / 100"))
        ttk.Label(r, text="Beschreibung").grid(row=5, column=0, sticky="nw", pady=4)
        self.beschreibung = tk.Text(r, height=9, wrap="word", font=("Segoe UI", 10), relief="solid", bd=1)
        self.beschreibung.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=4)
        r.rowconfigure(5, weight=1)
        zeile(6, "Tags", self.tags)
        ttk.Label(r, text="mit Komma trennen, zusammen max. 500 Zeichen", style="Klein.TLabel").grid(row=7, column=1, sticky="w")
        ttk.Label(r, text="Sichtbarkeit").grid(row=8, column=0, sticky="w", pady=4)
        ttk.Combobox(r, textvariable=self.sicht, values=["nicht gelistet", "privat", "öffentlich"], state="readonly", width=18).grid(row=8, column=1, sticky="w", pady=4)
        ttk.Checkbutton(r, text="Speziell für Kinder", variable=self.kinder).grid(row=9, column=1, sticky="w")

        leiste = ttk.Frame(r); leiste.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(14, 6))
        ttk.Button(leiste, text="Paket laden …", command=self.paket_laden).pack(side="left")
        ttk.Button(leiste, text="Prüfen", command=self.pruefen).pack(side="left", padx=8)
        self.knopf_upload = ttk.Button(leiste, text="Hochladen", style="Haupt.TButton", command=self.hochladen)
        self.knopf_upload.pack(side="right")

        self.balken = ttk.Progressbar(r, maximum=100); self.balken.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(4, 6))
        self.log = tk.Text(r, height=7, wrap="word", font=("Consolas", 9), state="disabled", relief="solid", bd=1, bg="#fbfbfc")
        self.log.grid(row=12, column=0, columnspan=3, sticky="nsew")
        unten = ttk.Frame(r); unten.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.knopf_link = ttk.Button(unten, text="Link öffnen", command=lambda: webbrowser.open(self.link), state="disabled")
        self.knopf_link.pack(side="left")
        self.knopf_kopie = ttk.Button(unten, text="Link kopieren", command=self.link_kopieren, state="disabled")
        self.knopf_kopie.pack(side="left", padx=8)
        self.knopf_wache = ttk.Button(unten, text="Warteschlange überwachen: aus", command=self.wache_umschalten)
        self.knopf_wache.pack(side="right")

    # ---------- Hilfen ----------
    def schreiben(self, text):
        self.log.config(state="normal"); self.log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        self.log.see("end"); self.log.config(state="disabled")

    def _queue_lesen(self):
        try:
            while True:
                art, wert = self.q.get_nowait()
                if art == "log": self.schreiben(wert)
                elif art == "fortschritt": self.balken["value"] = wert * 100
                elif art == "fertig": self._fertig(wert)
                elif art == "fehler": self._fehler(wert)
                elif art == "anmeldung": self._anmeldestatus()
        except queue.Empty:
            pass
        self.after(150, self._queue_lesen)

    def _anmeldestatus(self):
        if yu.TOKEN.exists():
            self.status_anmeldung.config(text="Angemeldet ✓  (token.json vorhanden)")
        elif yu.CLIENT_SECRET.exists():
            self.status_anmeldung.config(text="Noch nicht angemeldet – einmal auf „Anmelden“ klicken")
        else:
            self.status_anmeldung.config(text="client_secret.json fehlt – siehe ANLEITUNG.md")

    def paket(self) -> yu.Paket:
        return yu.Paket(video=self.video.get().strip(), titel=self.titel.get(), beschreibung=self.beschreibung.get("1.0", "end-1c"),
                        tags=[t.strip() for t in self.tags.get().split(",") if t.strip()], thumbnail=self.thumb.get().strip() or None,
                        sichtbarkeit=self.sicht.get(), fuer_kinder=self.kinder.get())

    # ---------- Aktionen ----------
    def video_waehlen(self):
        p = filedialog.askopenfilename(title="Video wählen", filetypes=[("Videos", "*.mp4 *.mov *.mkv *.avi *.webm"), ("Alle", "*.*")])
        if p: self.video.set(p)

    def thumb_waehlen(self):
        p = filedialog.askopenfilename(title="Thumbnail wählen", filetypes=[("Bilder", "*.png *.jpg *.jpeg")])
        if p: self.thumb.set(p)

    def paket_laden(self, pfad: str | None = None):
        pfad = pfad or filedialog.askopenfilename(title="Paket laden", filetypes=[("Paket", "*.json")])
        if not pfad: return
        try:
            p = yu.paket_laden(Path(pfad))
        except yu.UploadFehler as e:
            messagebox.showerror("Paket", str(e)); return
        self.video.set(p.video); self.thumb.set(p.thumbnail or ""); self.titel.set(p.titel)
        self.beschreibung.delete("1.0", "end"); self.beschreibung.insert("1.0", p.beschreibung)
        self.tags.set(", ".join(p.tags)); self.sicht.set(p.sichtbarkeit); self.kinder.set(p.fuer_kinder)
        self.schreiben(f"Paket geladen: {Path(pfad).name}")

    def pruefen(self):
        pr = self.paket().pruefen()
        if pr: self.schreiben("Bitte korrigieren:\n- " + "\n- ".join(pr))
        else: self.schreiben("Alles in Ordnung, bereit zum Hochladen.")
        return not pr

    def anmelden(self):
        def lauf():
            try:
                yu.anmelden(); self.q.put(("log", "Angemeldet.")); self.q.put(("anmeldung", None))
            except Exception as e:
                self.q.put(("log", f"Anmeldung fehlgeschlagen: {e}"))
        self.schreiben("Browser öffnet sich zur Anmeldung …")
        threading.Thread(target=lauf, daemon=True).start()

    def hochladen(self):
        if not self.pruefen(): return
        paket = self.paket()
        self.knopf_upload.config(state="disabled"); self.balken["value"] = 0
        def lauf():
            try:
                link = yu.hochladen(paket, fortschritt=lambda x: self.q.put(("fortschritt", x)), log=lambda t: self.q.put(("log", t)))
                self.q.put(("fertig", link))
            except Exception as e:
                self.q.put(("fehler", str(e)))
        threading.Thread(target=lauf, daemon=True).start()

    def _fertig(self, link):
        self.link = link; self.knopf_upload.config(state="normal"); self.balken["value"] = 100
        self.knopf_link.config(state="normal"); self.knopf_kopie.config(state="normal")
        self.schreiben(f"Fertig: {link}")

    def _fehler(self, text):
        self.knopf_upload.config(state="normal"); self.schreiben(text)

    def link_kopieren(self):
        self.clipboard_clear(); self.clipboard_append(self.link); self.schreiben("Link kopiert.")

    def wache_umschalten(self):
        self.ueberwachung = not self.ueberwachung
        self.knopf_wache.config(text=f"Warteschlange überwachen: {'an' if self.ueberwachung else 'aus'}")
        if self.ueberwachung:
            self.schreiben(f"Überwache {yu.WARTESCHLANGE} – neue Pakete werden automatisch hochgeladen.")
            threading.Thread(target=self._wache, daemon=True).start()

    def _wache(self):
        while self.ueberwachung:
            try:
                yu.warteschlange_einmal(log=lambda t: self.q.put(("log", t)))
            except Exception as e:
                self.q.put(("log", f"Warteschlange: {e}"))
            time.sleep(10)


if __name__ == "__main__":
    App().mainloop()
