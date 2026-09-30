import copy
import pytest
from journal.app import create_app
from journal.store import Store, ValidationError


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")


def entry(**overrides):
    return dict(title="Bir gün", body="Bugün yürüyüş bana iyi geldi.", event_date="2025-06-04", **overrides)


def test_edit_delete_invalidates_vectors_and_preserves_written_time(store):
    row = store.save(entry())
    store.put_vectors([(row["id"], 0, row["body"], [1, 0])], "local")
    edited = store.save(entry(analyze=False, mood="İyi"), row["id"])
    assert edited["written_at"] == row["written_at"]
    assert edited["event_date"] != edited["written_at"][:10]
    assert not store.cached_vectors("local")
    assert not store.entries(eligible=True)
    assert store.revision() == 2
    store.delete(row["id"])
    assert store.get(row["id"]) is None
    assert store.revision() == 3


def test_backup_roundtrip_and_atomic_invalid_restore(store):
    original = store.save(entry(kind="decision", reason="Öğrenmek", expectation="Yeni beceriler", outcome="Kursu bitirdim"))
    backup = store.export()
    bad = copy.deepcopy(backup)
    bad["entries"].append({"title": "Eksik"})
    with pytest.raises(ValidationError):
        store.restore(bad)
    assert store.get(original["id"]) == original
    store.delete(original["id"])
    assert store.restore(backup) == 1
    assert store.get(original["id"]) == original
    bad = copy.deepcopy(backup)
    bad["entries"] *= 2
    with pytest.raises(ValidationError):
        store.restore(bad)
    assert len(store.entries()) == 1


@pytest.mark.parametrize("changes", [{"event_date": "2025-02-30"}, {"analyze": "false"}, {"mood": "unknown"}, {"body": ""}, {"title": "a"*161}])
def test_invalid_records(store, changes):
    data = entry()
    data.update(changes)
    with pytest.raises(ValidationError):
        store.save(data)
    assert store.revision() == 0


def test_local_security_and_api(tmp_path):
    app = create_app(tmp_path)
    client = app.test_client()
    auth = {"X-Journal-Token": app.config["LOCAL_TOKEN"]}
    assert client.get("/api/entries").status_code == 403
    assert client.get("/", base_url="http://evil.example").status_code == 403
    assert client.post("/api/entries", json=entry(), headers={**auth, "Origin": "http://evil.example"}).status_code == 403
    created = client.post("/api/entries", json=entry(), headers=auth)
    assert created.status_code == 201
    eid = created.json["id"]
    assert client.put("/api/entries/"+eid, json=entry(mood="İyi"), headers=auth).json["mood"] == "İyi"
    backup = client.get("/api/backup", headers=auth).json
    assert client.post("/api/restore", json={"backup": backup}, headers=auth).status_code == 400
    assert client.post("/api/restore", json={"backup": backup, "confirm_replace": True}, headers=auth).json["count"] == 1
    assert client.delete("/api/entries/"+eid, headers=auth).status_code == 200
    assert client.get("/api/entries/"+eid, headers=auth).status_code == 404
    assert "no-store" in client.get("/").headers["Cache-Control"]


@pytest.mark.parametrize("value", ["2025-W01-1", "2025-W02-1"])
def test_week_dates_are_rejected_consistently(store, value):
    data = entry()
    data["event_date"] = value
    with pytest.raises(ValidationError):
        store.save(data)
    with pytest.raises(ValidationError):
        store.entries(start=value)


def test_backup_above_previous_record_and_http_limits(tmp_path):
    import uuid
    app = create_app(tmp_path)
    store = app.extensions["store"]
    row = store.save(entry())
    backup = store.export()
    backup["entries"] = [dict(row, id=str(uuid.UUID(int=i + 1)), body="x" * 1800)
                         for i in range(10001)]
    assert store.restore(backup) == 10001
    client = app.test_client()
    auth = {"X-Journal-Token": app.config["LOCAL_TOKEN"]}
    exported = client.get("/api/backup", headers=auth)
    assert len(exported.data) > 16 * 1024 * 1024
    response = client.post("/api/restore", json={"backup": exported.json, "confirm_replace": True}, headers=auth)
    assert response.status_code == 200
    assert response.json["count"] == 10001
    assert len(store.entries()) == 10001


def test_production_server_bounds_backup_headers(monkeypatch, tmp_path, capsys):
    import sys
    from journal import __main__ as launcher
    from waitress.adjustments import Adjustments
    from waitress.parser import HTTPRequestParser

    settings = {}
    monkeypatch.setattr(sys, "argv", ["journal", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(launcher, "serve", lambda app, **kwargs: settings.update(kwargs))
    launcher.main()
    assert (tmp_path / "access.key").read_text() not in capsys.readouterr().out
    parser = HTTPRequestParser(Adjustments(**settings))
    parser.received(b"POST /api/restore HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Length: 134217729\r\n\r\n")
    assert parser.error is not None
    allowed = HTTPRequestParser(Adjustments(**settings))
    allowed.received(b"POST /api/restore HTTP/1.1\r\nHost: localhost\r\n"
                     b"Content-Length: 20000000\r\n\r\n")
    assert allowed.error is None


def test_access_key_is_private_and_not_served_in_home(tmp_path):
    import os
    app = create_app(tmp_path)
    key = app.config["LOCAL_TOKEN"]
    assert (tmp_path / "access.key").read_text() == key
    if os.name == "posix":
        assert (tmp_path / "access.key").stat().st_mode & 0o077 == 0
    home = app.test_client().get("/").text
    assert key not in home and 'journal-token' not in home
    assert create_app(tmp_path).config["LOCAL_TOKEN"] == key
    client = app.test_client()
    assert client.get("/api/backup").status_code == 403
    assert client.get("/api/backup", headers={"X-Journal-Token": key}).status_code == 200


@pytest.mark.parametrize("route,payload", [
    ("ask", {"question": "Ne oldu?"}),
    ("insights", {"start": "2025-06-01", "end": "2025-06-30"}),
])
def test_slow_model_does_not_block_read_or_edit_and_stale_answer_is_rejected(tmp_path, route, payload):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    class BlockingAI:
        embedding_model = "blocking-test"

        def __init__(self):
            self.entered = threading.Event()
            self.release = threading.Event()

        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

        def generate(self, task, chunks, summary=False):
            self.entered.set()
            assert self.release.wait(5)
            return []

    ai = BlockingAI()
    app = create_app(tmp_path, ai)
    row = app.extensions["store"].save(entry())
    auth = {"X-Journal-Token": app.config["LOCAL_TOKEN"]}

    def analyze():
        with app.test_client() as client:
            return client.post("/api/" + route, json=payload, headers=auth).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(analyze)
        try:
            assert ai.entered.wait(3)
            with app.test_client() as client:
                assert client.get("/api/entries", headers=auth).status_code == 200
                assert client.put("/api/entries/" + row["id"], json={**entry(), "mood": "İyi"}, headers=auth).status_code == 200
        finally:
            ai.release.set()
        assert future.result(timeout=5) == 409


@pytest.mark.parametrize("token", ["é", "ş", "invalidé"])
def test_non_ascii_api_token_is_rejected(tmp_path, token):
    app = create_app(tmp_path)
    app.testing = True
    response = app.test_client().get("/api/entries", headers={"X-Journal-Token": token})
    assert response.status_code == 403


def test_entry_snapshot_revision_cannot_overtake_entries(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    app = create_app(tmp_path)
    store = app.extensions["store"]
    original = store.save(entry())
    read_entries = store.entries

    def competing_writer():
        if store.lock.acquire(blocking=False):
            try:
                store.save(entry(mood="İyi"), original["id"])
            finally:
                store.lock.release()

    def read_while_writer_attempts(*args, **kwargs):
        snapshot = read_entries(*args, **kwargs)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(competing_writer).result(timeout=5)
        return snapshot

    monkeypatch.setattr(store, "entries", read_while_writer_attempts)
    auth = {"X-Journal-Token": app.config["LOCAL_TOKEN"]}
    response = app.test_client().get("/api/entries", headers=auth)
    assert response.status_code == 200
    assert response.json == {"entries": [original], "revision": 1}
    # A writer can still update after the response, advancing the next snapshot.
    edited = store.save(entry(mood="İyi"), original["id"])
    response = app.test_client().get("/api/entries", headers=auth)
    assert response.json == {"entries": [edited], "revision": 2}
