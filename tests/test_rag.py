import pytest
from journal.ollama import AIError, Ollama
from journal.rag import Engine, chunks_for, validated_findings
from journal.store import Store


class FakeAI:
    embedding_model = "fake-local"
    def __init__(self):
        self.seen = []
    def embed(self, texts):
        self.seen.extend(texts)
        return [[1.0, 0.5] for text in texts]
    def generate(self, task, chunks):
        c = chunks[0]
        return [{"text": "Kaydedilmiş bir anı.", "kind": "recorded", "sources": [{"key": c["key"], "quote": c["text"][:40]}]}]


def data(body="Limon Kafe'de kahve içtim.", **kw):
    return dict(title="Tatil", body=body, event_date="2025-07-12", **kw)


def test_sources_dates_and_exclusion(tmp_path):
    store = Store(tmp_path / "journal.db")
    included = store.save(data())
    store.save(data("Gizli bilgi", analyze=False))
    ai = FakeAI()
    engine = Engine(store, ai)
    result = engine.ask("Kafenin adı neydi?")
    source = result["findings"][0]["sources"][0]
    assert source["entry_id"] == included["id"]
    assert source["event_date"] == "2025-07-12"
    assert source["written_at"] == included["written_at"]
    assert not any("Gizli" in text for text in ai.seen)
    store.save(data("Değişmiş anı"), included["id"])
    ai.seen.clear()
    newer = engine.ask("Kafe?")
    assert newer["revision"] > result["revision"]
    assert "Değişmiş" in newer["findings"][0]["sources"][0]["quote"]
    store.delete(included["id"])
    assert engine.ask("Kafe?")["findings"] == []
    assert not store.cached_vectors(ai.embedding_model)


def test_hallucinated_or_nonliteral_citations_rejected(tmp_path):
    store = Store(tmp_path / "journal.db")
    chunks = chunks_for([store.save(data())])
    valid = {"text": "Bir yorum", "kind": "inference", "sources": [{"key": chunks[0]["key"], "quote": "Limon Kafe"}]}
    bad_key = {**valid, "sources": [{"key": "invented", "quote": "Limon Kafe"}]}
    bad_quote = {**valid, "sources": [{"key": chunks[0]["key"], "quote": "Mavi Kafe"}]}
    assert validated_findings([valid, bad_key, bad_quote, {}, None], chunks) == [
        {"text": "Bir yorum", "kind": "inference", "sources": [{"entry_id": chunks[0]["entry_id"], "title": "Tatil", "event_date": "2025-07-12", "written_at": chunks[0]["written_at"], "quote": "Limon Kafe", "key": chunks[0]["key"]}]}]


def test_empty_scope_never_calls_model(tmp_path):
    store = Store(tmp_path / "journal.db")
    ai = FakeAI()
    result = Engine(store, ai).ask("Ne oldu?")
    assert not result["findings"] and result["message"]
    assert ai.seen == []


def test_cloud_and_invalid_vectors_rejected(monkeypatch):
    monkeypatch.setenv("JOURNAL_MODEL", "qwen3:cloud")
    with pytest.raises(AIError):
        Ollama()
    monkeypatch.delenv("JOURNAL_MODEL")
    ai = Ollama()
    monkeypatch.setattr(ai, "call", lambda *a, **kw: {"remote_host": "https://cloud.invalid"})
    with pytest.raises(AIError):
        ai.ensure_local("local-alias")
    monkeypatch.setattr(ai, "call", lambda route, *a, **kw: {} if route == "show" else {"embeddings": [[float("nan")]]})
    with pytest.raises(AIError):
        ai.embed(["test"])


@pytest.mark.parametrize("models", [None, {}, [None], [{}], [{"name": 3}]])
def test_malformed_model_inventory_is_not_ready(monkeypatch, models):
    ai = Ollama()
    monkeypatch.setattr(ai, "call", lambda *a, **kw: {"models": models})
    status = ai.status()
    assert status["ready"] is False
    assert status["error"]


@pytest.mark.parametrize("boundary", [False, 0, [], {}, "2025-99-01"])
def test_invalid_dates_do_not_broaden_search(tmp_path, boundary):
    from journal.store import ValidationError
    engine = Engine(Store(tmp_path / "journal.db"), FakeAI())
    for kwargs in ({"start": boundary}, {"end": boundary}):
        with pytest.raises(ValidationError):
            engine.ask("Ne oldu?", **kwargs)
    assert engine.ai.seen == []


def test_date_scope_and_withdrawn_consent(tmp_path):
    store = Store(tmp_path / "journal.db")
    inside = store.save(data())
    store.save({**data("Dönem dışındaki kayıt"), "event_date": "2024-01-01"})
    ai = FakeAI()
    engine = Engine(store, ai)
    result = engine.ask("Ne oldu?", "2025-07-12", "2025-07-12")
    assert result["searched_entries"] == 1
    assert result["findings"][0]["sources"][0]["entry_id"] == inside["id"]
    assert not any("Dönem dışındaki" in text for text in ai.seen)
    store.save(data(analyze=False), inside["id"])
    ai.seen.clear()
    assert not engine.ask("Ne oldu?", "2025-07-12", "2025-07-12")["findings"]
    assert not ai.seen
    assert not store.cached_vectors(ai.embedding_model)


@pytest.mark.parametrize("response", [{}, {"response": "not-json"}, {"response": "[]"}, {"response": '{"findings":null}'}, {"done_reason": "length"}])
def test_malformed_generation_fails_closed(monkeypatch, response):
    ai = Ollama()
    monkeypatch.setattr(ai, "call", lambda route, *a, **kw: {} if route == "show" else response)
    with pytest.raises(AIError):
        ai.generate("Ne oldu?", [])


def test_generation_anchors_relative_dates_without_changing_sources(monkeypatch):
    import json
    from datetime import date
    import journal.ollama as transport

    class LocalDate:
        @staticmethod
        def today():
            return date(2026, 1, 1)

    monkeypatch.setattr(transport, "date", LocalDate)
    ai = Ollama()
    captured = {}

    def call(route, payload=None, **kwargs):
        if route == "generate":
            captured.update(payload)
            return {"response": '{"findings":[]}'}
        return {}

    monkeypatch.setattr(ai, "call", call)
    chunks = [{"key": "record:0", "text": "Kahve içtim.",
               "event_date": "2025-07-12", "written_at": "2026-01-01T09:00:00+00:00"}]
    assert ai.generate("Geçen yıl ne yaptım?", chunks) == []
    prompt = json.loads(captured["prompt"])
    assert prompt["BAĞLAM"] == {"today_local": "2026-01-01"}
    assert prompt["GÖREV"] == "Geçen yıl ne yaptım?"
    assert prompt["KAYNAKLAR"] == chunks
    assert "event_date" in captured["system"] and "written_at" in captured["system"]
    assert "günlükten gelen bir kanıt sayma" in captured["system"]


@pytest.mark.parametrize("verdict", [None, {}, {"supported": [1]}, {"supported": []},
                                     {"supported": [True, False]}, {"supported": ["true"]}])
def test_malformed_support_verdict_fails_closed(monkeypatch, verdict):
    import json
    ai = Ollama()
    replies = iter([{"response": json.dumps({"findings": [{"text": "Limon Kafe"}]})},
                    {"response": json.dumps(verdict)}])
    monkeypatch.setattr(ai, "call", lambda route, *a, **kw: {} if route == "show" else next(replies))
    with pytest.raises(AIError, match="kaynak desteği"):
        ai.generate("Kafenin adı?", [])


def test_support_verification_keeps_only_supported_answers(monkeypatch):
    import json
    ai = Ollama()
    candidates = [{"text": "Limon Kafe", "kind": "recorded", "sources": [{"key": "a", "quote": "Limon Kafe"}]},
                  {"text": "Kariyer kursuna gittim", "kind": "inference", "sources": [{"key": "b", "quote": "kurs"}]}]
    chunks = [{"key": "a", "text": "Limon Kafe"}, {"key": "b", "text": "kurs"}]
    captured = []
    def call(route, payload=None, **kwargs):
        if route == "show":
            return {}
        captured.append(payload)
        return {"response": json.dumps({"findings": candidates} if len(captured) == 1 else {"supported": [True, False]})}
    monkeypatch.setattr(ai, "call", call)
    assert ai.generate("Kafenin adı?", chunks) == [candidates[0]]
    assert len(captured) == 2
    verification = json.loads(captured[1]["prompt"])
    assert verification["ADAYLAR"] == candidates and verification["KAYNAKLAR"] == chunks


def test_question_echo_is_not_an_answer(monkeypatch):
    import json
    ai = Ollama()
    calls = []
    def call(route, *args, **kwargs):
        calls.append(route)
        return {} if route == "show" else {"response": json.dumps({"findings": [{"text": "Kafenin adı?"}]})}
    monkeypatch.setattr(ai, "call", call)
    assert ai.generate("Kafenin adı?", []) == []
    assert calls == ["show", "generate"]


def test_verifier_sees_only_cited_excerpt_not_uncited_claims(monkeypatch):
    import json
    ai = Ollama()
    candidate = {"text": "Yürüyüş rahatlamama yardımcı oldu.", "kind": "recorded",
                 "sources": [{"key": "a", "quote": "Yürüyüş iyi geldi."}]}
    captured = []
    def call(route, payload=None, **kwargs):
        if route == "show":
            return {}
        captured.append(payload)
        return {"response": json.dumps({"findings": [candidate]} if len(captured) == 1
                                       else {"supported": [True]})}
    monkeypatch.setattr(ai, "call", call)
    chunks = [{"key": "a", "title": "Akşam", "event_date": "2026-09-18",
               "text": "Yoğun çalıştım. Yürüyüş iyi geldi. Erken yatacağım.",
               "context": "Önceki AI yorumu"}]
    assert ai.generate("Bana ne iyi geldi?", chunks) == [candidate]
    evidence = json.loads(captured[1]["prompt"])["KAYNAKLAR"]
    assert evidence == [{"key": "a", "title": "Akşam", "event_date": "2026-09-18",
                         "text": "Yürüyüş iyi geldi."}]


@pytest.mark.parametrize("answer", ["Akşam", "2026-01-01: Akşam - İyi", "x" * 360, "x" * 361])
def test_bare_source_title_and_whole_long_source_are_not_summaries(monkeypatch, answer):
    import json
    ai = Ollama()
    calls = []
    def call(route, *args, **kwargs):
        calls.append(route)
        return {} if route == "show" else {"response": json.dumps({"findings": [{"text": answer}]})}
    monkeypatch.setattr(ai, "call", call)
    assert ai.generate("Dönemi özetle", [{"key": "a", "title": "Akşam", "text": "x" * 361}], summary=True) == []
    assert calls == ["show", "generate"]


def test_factual_answer_may_equal_source_title(monkeypatch):
    import json
    ai = Ollama()
    candidate = {"text": "Limon Kafe", "kind": "recorded",
                 "sources": [{"key": "a", "quote": "Limon Kafe"}]}
    replies = iter([{"response": json.dumps({"findings": [candidate]})},
                    {"response": json.dumps({"supported": [True]})}])
    monkeypatch.setattr(ai, "call", lambda route, *a, **kw: {} if route == "show" else next(replies))
    assert ai.generate("Kafenin adı?", [{"key": "a", "title": "Limon Kafe",
                       "text": "Limon Kafe'de kahve içtim."}]) == [candidate]
