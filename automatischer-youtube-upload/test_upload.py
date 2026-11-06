"""Funktionstests mit simulierter YouTube-API. Start: uv run --with pytest pytest -q"""
import json
from pathlib import Path
from unittest import mock

import pytest
from googleapiclient.errors import HttpError

import youtube_upload as yu


class Resp(dict):
    def __init__(self, status):
        super().__init__(status=str(status)); self.status = status; self.reason = "x"


def http_error(status, reason):
    body = json.dumps({"error": {"message": "msg", "errors": [{"reason": reason}]}}).encode()
    return HttpError(Resp(status), body)


class Status:
    def __init__(self, p): self._p = p
    def progress(self): return self._p


class FakeInsert:
    def __init__(self, schritte): self.schritte = list(schritte)
    def next_chunk(self):
        s = self.schritte.pop(0)
        if isinstance(s, Exception): raise s
        return s


class FakeDienst:
    def __init__(self, schritte, thumb_fehler=None):
        self.insert_kwargs = None; self.thumb_kwargs = None
        self._schritte = schritte; self._thumb_fehler = thumb_fehler
    def videos(self):
        d = self
        class V:
            def insert(self, **kw):
                d.insert_kwargs = kw; return FakeInsert(d._schritte)
        return V()
    def thumbnails(self):
        d = self
        class T:
            def set(self, **kw):
                d.thumb_kwargs = kw
                class E:
                    def execute(self_inner):
                        if d._thumb_fehler: raise d._thumb_fehler
                        return {}
                return E()
        return T()


@pytest.fixture
def dateien(tmp_path):
    v = tmp_path / "video.mp4"; v.write_bytes(b"\0" * 2048)
    t = tmp_path / "thumb.png"; t.write_bytes(b"\x89PNG" + b"\0" * 100)
    return v, t


def paket(v, t=None, **kw):
    d = dict(video=str(v), titel="Netzwerk & Backup", beschreibung="Kapitel:\n0:00 Start", tags=["VLAN", "RAID 6"], thumbnail=str(t) if t else None)
    d.update(kw); return yu.Paket(**d)


def test_body_nicht_gelistet_standard(dateien):
    v, t = dateien
    b = paket(v, t).body()
    assert b["status"]["privacyStatus"] == "unlisted"
    assert b["status"]["selfDeclaredMadeForKids"] is False
    assert b["snippet"]["title"] == "Netzwerk & Backup"
    assert b["snippet"]["tags"] == ["VLAN", "RAID 6"]


def test_upload_mit_thumbnail_und_fortschritt(dateien):
    v, t = dateien
    d = FakeDienst([(Status(0.5), None), (None, {"id": "abc123"})])
    werte = []
    link = yu.hochladen(paket(v, t), dienst=d, fortschritt=werte.append, log=lambda s: None)
    assert link == "https://youtu.be/abc123"
    assert d.insert_kwargs["part"] == "snippet,status"
    assert d.insert_kwargs["body"]["status"]["privacyStatus"] == "unlisted"
    assert d.thumb_kwargs["videoId"] == "abc123"
    assert werte == [0.5, 1.0]


def test_ohne_thumbnail_kein_thumbnail_aufruf(dateien):
    v, _ = dateien
    d = FakeDienst([(None, {"id": "x1"})])
    yu.hochladen(paket(v), dienst=d, log=lambda s: None)
    assert d.thumb_kwargs is None


def test_server_fehler_wird_wiederholt(dateien, monkeypatch):
    v, _ = dateien
    monkeypatch.setattr(yu.time, "sleep", lambda s: None)
    d = FakeDienst([http_error(503, "backendError"), (None, {"id": "r1"})])
    assert yu.hochladen(paket(v), dienst=d, log=lambda s: None) == "https://youtu.be/r1"


def test_verbindungsabbruch_wird_wiederholt(dateien, monkeypatch):
    v, _ = dateien
    monkeypatch.setattr(yu.time, "sleep", lambda s: None)
    d = FakeDienst([ConnectionError("weg"), (None, {"id": "c1"})])
    assert yu.hochladen(paket(v), dienst=d, log=lambda s: None) == "https://youtu.be/c1"


def test_quota_fehler_deutsch(dateien):
    v, _ = dateien
    d = FakeDienst([http_error(403, "quotaExceeded")])
    with pytest.raises(yu.UploadFehler, match="Tageslimit"):
        yu.hochladen(paket(v), dienst=d, log=lambda s: None)


def test_thumbnail_fehler_bricht_nicht_ab(dateien):
    v, t = dateien
    logs = []
    d = FakeDienst([(None, {"id": "t1"})], thumb_fehler=http_error(403, "forbidden"))
    assert yu.hochladen(paket(v, t), dienst=d, log=logs.append) == "https://youtu.be/t1"
    assert any("Thumbnail konnte nicht" in l for l in logs)


@pytest.mark.parametrize("aenderung,erwartet", [
    (dict(titel=""), "Titel fehlt"),
    (dict(titel="x" * 101), "erlaubt sind 100"),
    (dict(beschreibung="a <b>"), "< oder >"),
    (dict(tags=["t" * 60] * 9), "erlaubt sind 500"),
    (dict(video="/gibt/es/nicht.mp4"), "Videodatei nicht gefunden"),
    (dict(sichtbarkeit="geheim"), "Unbekannte Sichtbarkeit"),
])
def test_pruefung(dateien, aenderung, erwartet):
    v, t = dateien
    pr = paket(v, t, **aenderung).pruefen()
    assert any(erwartet in p for p in pr), pr


def test_pruefung_bricht_vor_upload_ab(dateien):
    v, _ = dateien
    d = FakeDienst([])
    with pytest.raises(yu.UploadFehler, match="Titel fehlt"):
        yu.hochladen(paket(v, titel=""), dienst=d, log=lambda s: None)
    assert d.insert_kwargs is None


def test_paket_json_relative_pfade_und_tags_string(tmp_path, dateien):
    v, t = dateien
    (tmp_path / "p.json").write_text(json.dumps({"video": "video.mp4", "thumbnail": "thumb.png", "titel": "T",
                                                 "tags": "a, b ,c", "sichtbarkeit": "privat"}), encoding="utf-8")
    p = yu.paket_laden(tmp_path / "p.json")
    assert p.video == str(tmp_path / "video.mp4") and p.thumbnail == str(tmp_path / "thumb.png")
    assert p.tags == ["a", "b", "c"] and p.body()["status"]["privacyStatus"] == "private"


def test_kaputtes_json(tmp_path):
    (tmp_path / "p.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(yu.UploadFehler, match="kein gültiges JSON"):
        yu.paket_laden(tmp_path / "p.json")


def test_warteschlange(tmp_path, dateien, monkeypatch):
    v, t = dateien
    ws = tmp_path / "warteschlange"
    monkeypatch.setattr(yu, "WARTESCHLANGE", ws); monkeypatch.setattr(yu, "ERLEDIGT", ws / "erledigt"); monkeypatch.setattr(yu, "FEHLER", ws / "fehler")
    ws.mkdir()
    (ws / "gut.json").write_text(json.dumps({"video": str(v), "titel": "Gut", "thumbnail": str(t)}), encoding="utf-8")
    (ws / "schlecht.json").write_text(json.dumps({"video": str(v), "titel": ""}), encoding="utf-8")
    d = FakeDienst([(None, {"id": "w1"})])
    n = yu.warteschlange_einmal(dienst_fabrik=lambda interaktiv: d, log=lambda s: None)
    assert n == 2
    links = list((ws / "erledigt").glob("*.link.txt")); fehler = list((ws / "fehler").glob("*.fehler.txt"))
    assert len(links) == 1 and links[0].read_text().strip() == "https://youtu.be/w1"
    assert len(fehler) == 1 and "Titel fehlt" in fehler[0].read_text()
    assert not list(ws.glob("*.json"))


def test_kommandozeile_pruefen(dateien, capsys):
    v, _ = dateien
    assert yu.main(["--video", str(v), "--titel", "Ok", "--tags", "a, b", "--pruefen"]) == 0
    assert "Alles in Ordnung" in capsys.readouterr().out
    assert yu.main(["--video", str(v), "--titel", "", "--pruefen"]) == 1


def test_anmelden_ohne_client_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(yu, "TOKEN", tmp_path / "token.json"); monkeypatch.setattr(yu, "CLIENT_SECRET", tmp_path / "client_secret.json")
    with pytest.raises(yu.UploadFehler, match="client_secret.json fehlt"):
        yu.anmelden()


def test_beispielpaket_ist_gueltig():
    d = json.loads((Path(__file__).parent / "beispiel" / "paket.json").read_text(encoding="utf-8"))
    p = yu.Paket.aus_dict(d, Path("."))
    probleme = [x for x in p.pruefen() if "nicht gefunden" not in x]  # Pfade gibt es nur auf Adems PC
    assert probleme == [], probleme
