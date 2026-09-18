from journal.store import Store
from journal.insights import Insights, coverage
from journal.rag import chunks_for


class ReadingAI:
    def __init__(self):
        self.seen = []
    def generate(self, task, chunks):
        self.seen.extend(chunks)
        return [{"text": "Kaynaklı dönem yorumu", "kind": "inference",
                 "sources": [{"key": c["key"], "quote": c["text"][:80]}]} for c in chunks[:3]]


def create(store, date, **kw):
    return store.save(dict(title="Bir kayıt", body="Yürüyüş bana iyi geldi.", event_date=date, **kw))


def test_period_reads_all_chunks_and_reports_gaps(tmp_path):
    store = Store(tmp_path / "journal.db")
    one = create(store, "2024-01-01", mood="Zor")
    create(store, "2024-03-01", mood="İyi")
    excluded = create(store, "2024-02-15", analyze=False)
    ai = ReadingAI()
    result = Insights(store, ai).analyze("2024-01-01", "2024-03-03")
    c = result["coverage"]
    assert c["entries"] == 2 and c["excluded_entries"] == 1 and c["recorded_days"] == 2
    assert c["gaps"] == [{"start": "2024-01-02", "end": "2024-02-29"}, {"start": "2024-03-02", "end": "2024-03-03"}]
    assert result["sections"][0]["moods"] == {"Zor": 1}
    assert result["sections"][1]["moods"] == {"İyi": 1}
    assert not any(c["entry_id"] == excluded["id"] for c in ai.seen)
    store.delete(one["id"])
    ai.seen.clear()
    later = Insights(store, ai).analyze("2024-01-01", "2024-03-03")
    assert later["coverage"]["entries"] == 1
    assert all(c["entry_id"] != one["id"] for c in ai.seen)


def test_large_period_is_batched_without_skipping_source_text(tmp_path):
    store = Store(tmp_path / "journal.db")
    for year in (2024, 2025):
        for month in range(1, 13):
            create(store, f"{year}-{month:02d}-01", helpful_note="Uzun yürüyüş iyi geldi. "*100)
    ai = ReadingAI()
    result = Insights(store, ai).analyze("2024-01-01", "2025-12-31")
    expected = {c["key"] for c in chunks_for(store.entries(eligible=True))}
    assert expected <= {c["key"] for c in ai.seen}
    assert result["coverage"]["entries"] == 24
    assert len(result["overview"]) <= 3
    assert len(result["sections"]) == 24


def test_empty_period_and_date_max(tmp_path):
    store = Store(tmp_path / "journal.db")
    result = Insights(store, ReadingAI()).analyze("2025-01-01", "2025-01-03", "helpful")
    assert result["message"]
    assert result["coverage"]["gaps"] == [{"start": "2025-01-01", "end": "2025-01-03"}]
    assert coverage([{"event_date": "9999-12-31"}], "9999-12-31", "9999-12-31")["gaps"] == []
