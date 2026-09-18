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


def test_production_server_accepts_large_backup_headers(monkeypatch, tmp_path):
    import sys
    from journal import __main__ as launcher
    from waitress.adjustments import Adjustments
    from waitress.parser import HTTPRequestParser

    settings = {}
    monkeypatch.setattr(sys, "argv", ["journal", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(launcher, "serve", lambda app, **kwargs: settings.update(kwargs))
    launcher.main()
    parser = HTTPRequestParser(Adjustments(**settings))
    parser.received(b"POST /api/restore HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Length: 1073741825\r\n\r\n")
    assert parser.error is None
    assert not parser.completed
