"""Integrationstest: echte googleapiclient-Bibliothek, nur das Netzwerk wird simuliert."""
import json
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence
import youtube_upload as yu

def test_echter_api_aufruf(tmp_path):
    v = tmp_path / "v.mp4"; v.write_bytes(b"\0" * 4096)
    t = tmp_path / "t.png"; t.write_bytes(b"\x89PNG" + b"\0" * 50)
    http = HttpMockSequence([
        ({"status": "200", "location": "https://upload.example/resumable?id=1"}, ""),
        ({"status": "200"}, json.dumps({"id": "REAL42"})),
        ({"status": "200"}, json.dumps({"items": []})),
    ])
    dienst = build("youtube", "v3", http=http, static_discovery=True)
    link = yu.hochladen(yu.Paket(video=str(v), titel="Test", tags=["a"], thumbnail=str(t)), dienst=dienst, log=lambda s: None)
    assert link == "https://youtu.be/REAL42"
    # erste Anfrage = Start des Uploads mit Metadaten
    erste = http.request_sequence if hasattr(http, "request_sequence") else None

def test_metadaten_im_request():
    import conftest
    m, uri, body = conftest.calls[0]
    assert m == "POST" and "uploadType=resumable" in uri and "part=snippet%2Cstatus" in uri
    meta = json.loads(body)
    assert meta["status"]["privacyStatus"] == "unlisted" and meta["snippet"]["title"] == "Test"
    assert any("thumbnails/set" in c[1] and "videoId=REAL42" in c[1] for c in conftest.calls)


def test_dateien_nach_upload_geschlossen_und_geloescht(tmp_path, monkeypatch):
    """Windows-Fehler 32: Video war nach dem Upload noch geöffnet und konnte nicht gelöscht werden."""
    import googleapiclient.http as gh
    offen = []
    orig = gh.MediaFileUpload.__init__
    def merken(self, *a, **k):
        orig(self, *a, **k); offen.append(self)
    monkeypatch.setattr(gh.MediaFileUpload, "__init__", merken)
    arbeit = tmp_path / "arbeit"; ordner = arbeit / "job"; ordner.mkdir(parents=True)
    monkeypatch.setattr(yu, "ARBEIT", arbeit)
    v = ordner / "v.mp4"; v.write_bytes(b"\0" * 4096)
    t = ordner / "t.png"; t.write_bytes(b"\x89PNG" + b"\0" * 50)
    http = HttpMockSequence([
        ({"status": "200", "location": "https://upload.example/resumable?id=1"}, ""),
        ({"status": "200"}, json.dumps({"id": "ZU1"})),
        ({"status": "200"}, json.dumps({"items": []})),
    ])
    dienst = build("youtube", "v3", http=http, static_discovery=True)
    yu.hochladen(yu.Paket(video=str(v), titel="Test", thumbnail=str(t), arbeitsordner=str(ordner)), dienst=dienst, log=lambda s: None)
    assert len(offen) == 2 and all(m._fd.closed for m in offen)
    assert not ordner.exists()
