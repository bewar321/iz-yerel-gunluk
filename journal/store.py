"""Local journal persistence. All derived data belongs to a source revision."""
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

MOODS = ("", "Çok zor", "Zor", "Dengeli", "İyi", "Çok iyi")
TEXT_LIMITS = {"title": 160, "body": 20000, "reason": 5000,
               "expectation": 5000, "outcome": 5000, "helpful_note": 5000}
FIELDS = (*TEXT_LIMITS, "event_date", "mood", "kind", "analyze")


class ValidationError(ValueError):
    pass


class StaleSnapshot(RuntimeError):
    pass


def iso_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValidationError("Tarih YYYY-AA-GG biçiminde olmalı.")
    try:
        parsed = date.fromisoformat(value).isoformat()
        if parsed != value:
            raise ValueError()
        return parsed
    except ValueError as exc:
        raise ValidationError("Geçerli bir tarih girin.") from exc


def validate_entry(data):
    if not isinstance(data, dict):
        raise ValidationError("Kayıt bir nesne olmalı.")
    result = {}
    for name, limit in TEXT_LIMITS.items():
        value = data.get(name, "")
        if not isinstance(value, str) or len(value) > limit:
            raise ValidationError(f"{name}: en fazla {limit} karakter kullanılabilir.")
        result[name] = value.strip()
    if not result["title"] or not result["body"]:
        raise ValidationError("Başlık ve günlük metni gerekli.")
    result["event_date"] = iso_date(data.get("event_date"))
    result["mood"] = data.get("mood", "")
    result["kind"] = data.get("kind", "journal")
    result["analyze"] = data.get("analyze", True)
    if result["mood"] not in MOODS or result["kind"] not in ("journal", "decision"):
        raise ValidationError("Geçersiz duygu veya kayıt türü.")
    if type(result["analyze"]) is not bool:
        raise ValidationError("Analiz izni true veya false olmalı.")
    return result


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                PRAGMA secure_delete=ON;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
                INSERT OR IGNORE INTO meta VALUES ('revision', 0);
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
                    event_date TEXT NOT NULL, written_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    mood TEXT NOT NULL, kind TEXT NOT NULL, analyze INTEGER NOT NULL,
                    reason TEXT NOT NULL, expectation TEXT NOT NULL,
                    outcome TEXT NOT NULL, helpful_note TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vectors (
                    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                    chunk_no INTEGER NOT NULL, model TEXT NOT NULL,
                    text TEXT NOT NULL, vector TEXT NOT NULL,
                    PRIMARY KEY (entry_id, chunk_no, model)
                );
            """)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def revision(self):
        with self.connection() as db:
            return db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]

    @staticmethod
    def changed(db):
        db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")

    @staticmethod
    def decode(row):
        entry = dict(row)
        entry["analyze"] = bool(entry["analyze"])
        return entry

    def entries(self, start=None, end=None, eligible=False):
        clauses, args = [], []
        if start:
            clauses.append("event_date>=?")
            args.append(iso_date(start))
        if end:
            clauses.append("event_date<=?")
            args.append(iso_date(end))
        if start and end and start > end:
            raise ValidationError("Başlangıç tarihi bitişten sonra olamaz.")
        if eligible:
            clauses.append("analyze=1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as db:
            return [self.decode(row) for row in db.execute(
                "SELECT * FROM entries" + where + " ORDER BY event_date DESC, written_at DESC", args)]

    def get(self, entry_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        return self.decode(row) if row else None

    def save(self, data, entry_id=None):
        fields = validate_entry(data)
        with self.lock, self.connection() as db:
            stamp = now()
            if entry_id:
                old = db.execute("SELECT id FROM entries WHERE id=?", (entry_id,)).fetchone()
                if not old:
                    raise KeyError(entry_id)
                fields["updated_at"] = stamp
                assignments = ",".join(f"{name}=?" for name in fields)
                db.execute(f"UPDATE entries SET {assignments} WHERE id=?", (*fields.values(), entry_id))
                db.execute("DELETE FROM vectors WHERE entry_id=?", (entry_id,))
            else:
                entry_id = str(uuid.uuid4())
                fields.update(id=entry_id, written_at=stamp, updated_at=stamp)
                columns = ",".join(fields)
                placeholders = ",".join("?" for _ in fields)
                db.execute(f"INSERT INTO entries ({columns}) VALUES ({placeholders})", tuple(fields.values()))
            self.changed(db)
        return self.get(entry_id)

    def delete(self, entry_id):
        with self.lock, self.connection() as db:
            if db.execute("DELETE FROM entries WHERE id=?", (entry_id,)).rowcount == 0:
                raise KeyError(entry_id)
            self.changed(db)

    def export(self):
        with self.lock:
            return {"format": "yerel-gunluk", "version": 1, "exported_at": now(), "entries": self.entries()}

    def restore(self, backup):
        if not isinstance(backup, dict) or backup.get("format") != "yerel-gunluk" or type(backup.get("version")) is not int or backup["version"] != 1:
            raise ValidationError("Desteklenmeyen yedek biçimi.")
        rows = backup.get("entries")
        if not isinstance(rows, list):
            raise ValidationError("Yedek kayıtları bir liste olmalı.")
        prepared, seen = [], set()
        for row in rows:
            fields = validate_entry(row)
            try:
                entry_id = str(uuid.UUID(row["id"]))
                for field in ("written_at", "updated_at"):
                    value = row[field]
                    if not isinstance(value, str) or len(value) > 40:
                        raise ValueError()
                    stamp = datetime.fromisoformat(value)
                    if stamp.tzinfo is None:
                        raise ValueError()
                    fields[field] = stamp.isoformat()
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValidationError("Yedekte geçersiz kimlik veya kayıt zamanı.") from exc
            if entry_id in seen:
                raise ValidationError("Yedekte tekrarlanan kayıt kimliği.")
            seen.add(entry_id)
            fields["id"] = entry_id
            prepared.append(fields)
        # Validate the whole backup BEFORE replacing anything; the replace is atomic.
        with self.lock, self.connection() as db:
            db.execute("DELETE FROM entries")
            for fields in prepared:
                cols = ",".join(fields)
                placeholders = ",".join("?" for _ in fields)
                db.execute(f"INSERT INTO entries ({cols}) VALUES ({placeholders})", tuple(fields.values()))
            self.changed(db)
        return len(prepared)

    def cached_vectors(self, model):
        with self.connection() as db:
            return {(r["entry_id"], r["chunk_no"]): (r["text"], json.loads(r["vector"]))
                    for r in db.execute("SELECT vectors.* FROM vectors JOIN entries ON entries.id=vectors.entry_id WHERE model=? AND analyze=1", (model,))}

    def put_vectors(self, rows, model):
        # Caller holds self.lock from snapshot through completion.
        with self.connection() as db:
            db.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?)",
                           [(eid, number, model, text, json.dumps(vector)) for eid, number, text, vector in rows])
