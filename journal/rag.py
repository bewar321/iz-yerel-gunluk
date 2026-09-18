"""Hybrid local retrieval; only validated source quotations leave the engine."""
import math
import re
from .ollama import AIError
from .store import ValidationError, iso_date


def tokens(text):
    return set(re.findall(r"[^\W_]+", text.replace("I", "ı").replace("İ", "i").lower(), re.UNICODE))


def source_text(entry):
    parts = [entry["title"], entry["body"]]
    for key, label in (("reason", "Gerekçem"), ("expectation", "Beklentim"),
                       ("outcome", "Sonuç"), ("helpful_note", "Bana iyi gelen")):
        if entry[key]:
            parts.append(label + ": " + entry[key])
    if entry["mood"]:
        parts.append("Kendi duygu etiketim: " + entry["mood"])
    return "\n\n".join(parts)


def chunks_for(entries):
    chunks = []
    for entry in entries:
        text = source_text(entry)
        for number, offset in enumerate(range(0, len(text), 1050)):
            chunks.append({"key": entry["id"] + ":" + str(number), "entry_id": entry["id"],
                           "chunk_no": number, "title": entry["title"], "event_date": entry["event_date"],
                           "written_at": entry["written_at"], "text": text[offset:offset+1200]})
            if offset + 1200 >= len(text):
                break
    return chunks


def cosine(a, b):
    if len(a) != len(b):
        raise AIError("Arama modeli değişti. Uygulamayı aynı embedding modeliyle başlatın veya indeksi yeniden oluşturun.")
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / norm if norm else 0


def validated_findings(raw, chunks):
    lookup = {chunk["key"]: chunk for chunk in chunks}
    valid = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip() or len(item["text"]) > 2000:
            continue
        if item.get("kind") not in ("recorded", "inference") or not isinstance(item.get("sources"), list) or not item["sources"]:
            continue
        sources = []
        for reference in item["sources"]:
            if not isinstance(reference, dict) or not isinstance(reference.get("key"), str):
                break
            chunk = lookup.get(reference["key"])
            quote = reference.get("quote")
            if not chunk or not isinstance(quote, str) or len(quote.strip()) < 3 or quote not in chunk["text"]:
                break
            sources.append({"entry_id": chunk["entry_id"], "title": chunk["title"],
                            "event_date": chunk["event_date"], "written_at": chunk["written_at"],
                            "quote": quote, "key": chunk["key"]})
        else:
            valid.append({"text": item["text"].strip(), "kind": item["kind"], "sources": sources})
    return valid


class Engine:
    def __init__(self, store, ai):
        self.store, self.ai = store, ai

    def retrieve(self, question, entries):
        chunks = chunks_for(entries)
        if not chunks:
            return []
        cached = self.store.cached_vectors(self.ai.embedding_model)
        pending = [c for c in chunks if (c["entry_id"], c["chunk_no"]) not in cached or cached[(c["entry_id"], c["chunk_no"])][0] != c["text"]]
        for start in range(0, len(pending), 16):
            batch = pending[start:start+16]
            vectors = self.ai.embed([c["text"] for c in batch])
            self.store.put_vectors([(c["entry_id"], c["chunk_no"], c["text"], v) for c, v in zip(batch, vectors)], self.ai.embedding_model)
            for c, vector in zip(batch, vectors):
                cached[(c["entry_id"], c["chunk_no"])] = (c["text"], vector)
        query = self.ai.embed([question])[0]
        terms = tokens(question)
        ranked = []
        for chunk in chunks:
            vector = cached[(chunk["entry_id"], chunk["chunk_no"])][1]
            semantic = cosine(query, vector)
            lexical = len(terms & tokens(chunk["text"])) / max(1, len(terms))
            ranked.append((0.75 * semantic + 0.25 * lexical, chunk))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [c for _, c in ranked[:5]]

    def ask(self, question, start=None, end=None):
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            raise ValidationError("1–1000 karakter uzunluğunda bir soru yazın.")
        for boundary in (start, end):
            if boundary is not None and boundary != "":
                iso_date(boundary)
        with self.store.lock:
            entries = self.store.entries(start, end, eligible=True)
            selected = self.retrieve(question, entries)
            raw = self.ai.generate(question, selected) if selected else []
            findings = validated_findings(raw, selected)
            return {"findings": findings, "message": "" if findings else "Bu soruyu yanıtlamak için günlüklerinde yeterli, doğrulanabilir bilgi bulamadım.",
                    "revision": self.store.revision(), "searched_entries": len(entries),
                    "used_entries": len({s["entry_id"] for f in findings for s in f["sources"]}),
                    "rejected_findings": len(raw) - len(findings)}
