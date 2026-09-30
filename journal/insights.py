"""Date-complete reading of a selected period, with explicit gaps and evidence."""
from collections import Counter, defaultdict
from datetime import date, timedelta

from .rag import chunks_for, validated_findings
from .store import StaleSnapshot, ValidationError, iso_date


def coverage(entries, start, end, excluded=0):
    days = sorted({e["event_date"] for e in entries})
    gaps, cursor = [], date.fromisoformat(start)
    finish = date.fromisoformat(end)
    for value in days:
        day = date.fromisoformat(value)
        if day > cursor:
            gaps.append({"start": cursor.isoformat(), "end": (day-timedelta(days=1)).isoformat()})
        if day == date.max:
            cursor = None
            break
        cursor = day + timedelta(days=1)
    if cursor is not None and cursor <= finish:
        gaps.append({"start": cursor.isoformat(), "end": finish.isoformat()})
    return {"start": start, "end": end, "entries": len(entries), "recorded_days": len(days),
            "total_days": (finish-date.fromisoformat(start)).days+1, "gaps": gaps,
            "excluded_entries": excluded, "date_basis": "event_date"}


def batches(items, budget=6000):
    batch, size = [], 0
    for item in items:
        cost = len(item["text"]) + len(item.get("context", "")) + 250
        if batch and size + cost > budget:
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += cost
    if batch:
        yield batch


def _short_sentence(text, limit=120):
    # Keep the excerpt byte-for-byte present in the record, including whitespace.
    clean = text.strip()
    import re
    ending = re.search(r"[.!?](?:\s|$)", clean)
    if ending:
        clean = clean[:ending.start()+1]
    if len(clean) > limit:
        clean = clean[:limit]
        if " " in clean:
            clean = clean.rsplit(" ", 1)[0]
    return clean.rstrip()


def _fallback_sources(entry, quotes):
    chunks = chunks_for([entry])
    sources = []
    for quote in quotes:
        chunk = next((c for c in chunks if quote and quote in c["text"]), None)
        if not chunk:
            return []
        sources.append({"entry_id": entry["id"], "title": entry["title"],
                        "event_date": entry["event_date"], "written_at": entry["written_at"],
                        "quote": quote, "key": chunk["key"]})
    return sources


def recorded_fallback(entry, mode):
    """Return source-exact excerpts when the local model yields no safe summary."""
    if mode == "helpful":
        if not entry["helpful_note"]:
            return None
        fact = _short_sentence(entry["helpful_note"])
        # The dedicated field is already the user's explicit helpfulness report.
        text = f'{entry["event_date"]}: {fact}'
        quotes = ["Bana iyi gelen: " + fact]
    else:
        fact = _short_sentence(entry["body"])
        if not fact:
            return None
        mood = f' Duygu etiketi: {entry["mood"]}.' if entry["mood"] else ""
        text = f'{entry["event_date"]} — {entry["title"]}: {fact}{mood}'
        quotes = [fact]
        if entry["mood"]:
            quotes.append("Kendi duygu etiketim: " + entry["mood"])
    sources = _fallback_sources(entry, quotes)
    return {"text": text, "kind": "recorded", "sources": sources} if sources else None


def overview_fallback(entries):
    """Compare the first and last recorded states without inventing a trend."""
    ordered = sorted(entries, key=lambda e: (e["event_date"], e["written_at"]))
    if len(ordered) < 2:
        return []
    parts, sources = [], []
    for entry in (ordered[0], ordered[-1]):
        topic = _short_sentence(entry["body"], 90)
        mood = entry["mood"] or "etiket yok"
        parts.append(f'{entry["event_date"]} (duygu etiketi: {mood}): {topic}')
        quotes = [topic]
        if entry["mood"]:
            quotes.append("Kendi duygu etiketim: " + entry["mood"])
        cited = _fallback_sources(entry, quotes)
        if not cited:
            return []
        sources.extend(cited)
    return [{"text": " / ".join(parts), "kind": "recorded", "sources": sources}]


class Insights:
    def __init__(self, store, ai):
        self.store, self.ai = store, ai

    def analyze(self, start, end, mode="period"):
        start, end = iso_date(start), iso_date(end)
        if start > end:
            raise ValidationError("Başlangıç tarihi bitişten sonra olamaz.")
        if mode not in ("period", "helpful"):
            raise ValidationError("Geçersiz analiz türü.")
        with self.store.lock:
            all_entries = self.store.entries(start, end)
            revision = self.store.revision()
        def ensure_fresh():
            with self.store.lock:
                if self.store.revision() != revision:
                    raise StaleSnapshot()
        entries = [e for e in all_entries if e["analyze"]]
        info = coverage(entries, start, end, len(all_entries)-len(entries))
        months = defaultdict(list)
        for entry in entries:
            months[entry["event_date"][:7]].append(entry)
        sections, all_findings = [], []
        rejected = 0
        if mode == "helpful":
            task = ("Yalnız kullanıcının kendisine yardımcı olduğunu AÇIKÇA yazdığı davranış veya deneyimleri bul. "
                    "Sadece bir etkinliğin yapılması yardımcı olduğunun kanıtı değildir. Genel tavsiye verme; "
                    "yazılmamış fayda çıkarma. Her bulgunun text alanında olay tarihini, yardımcı davranışı "
                    "ve yazılmış etkisini tek kısa cümlede özetle. Başlık, günlük metninin bütünü, "
                    "ilgisiz olaylar ve sonucu bilinmeyen planlar yanıt değildir. Yoksa boş findings dön.")
        else:
            task = ("Bu dönemdeki başlıca konuları, kullanıcının kaydettiği duyguları ve varsa değişimleri özetle. "
                    "Her bulgunun text alanında olay tarihini ve ana konuyu kısa bir cümlede özetle; "
                    "yalnız başlık veya duygu etiketi verme. Duygu etiketinin yanında o kayıtta anlatılan "
                    "konuyu da belirt. Tarihleri ayırt et. Özbildirim olmayan duygu yorumlarını "
                    "inference olarak işaretle. "
                    "Eksik sonuçları tamamlamadan beklenti ve kaydedilmiş sonuçları karşılaştır.")
        for month, month_entries in sorted(months.items()):
            chunks = chunks_for(sorted(month_entries, key=lambda e: (e["event_date"], e["written_at"])))
            findings = []
            for batch in batches(chunks):
                ensure_fresh()
                raw = self.ai.generate(task, batch, summary=True)
                checked = validated_findings(raw, batch)
                rejected += len(raw)-len(checked)
                findings.extend(checked)
            # Remove exact duplicates introduced by chunk overlap.
            unique = { (f["text"], tuple(s["key"] for s in f["sources"])): f for f in findings }
            findings = list(unique.values())
            if not findings:
                findings = [finding for entry in month_entries
                            if (finding := recorded_fallback(entry, mode)) is not None][:5]
            sections.append({"month": month, "entries": len(month_entries),
                             "moods": dict(Counter(e["mood"] or "Etiket yok" for e in month_entries)),
                             "findings": findings})
            all_findings.extend(findings)
        overview = []
        if mode == "period" and all_findings:
            # Hierarchical reduction; every level retains quotes from original records.
            # Each group is at most eight compact pieces and produces at most three findings.
            current = all_findings
            task = ("Tek görev: kaynaklarda farklı tarihler varsa ilk ve sonraki tarihteki konu/duygu "
                    "durumlarını AYNI CÜMLEDE karşılaştır; yalnız bir tarihte ne olduğunu anlatmak görevi "
                    "karşılamaz. Karşılaştırmanın sources alanında iki tarihten kanıt bulunmalı. "
                    "context önceki AI yorumudur, kanıt değildir; yalnız text içindeki özgün alıntılara dayan. "
                    "Her bulgunun text alanında tarihleri ve bu tarihlerdeki somut farkı tam bir cümleyle açıkla. "
                    "Yalnız kayıt başlıklarını veya ayrı ayrı etiketleri sıralama. "
                    "Örnek biçim: [ilk tarih] tarihinde ... yazılmışken [son tarih] tarihinde ... kaydedilmiş. "
                    "Örneğin boşluklarını yalnız kaynak bilgisiyle doldur. Yalnız bir olay tarihi varsa "
                    "o tarihteki durumu özetle, değişim uydurma. En fazla 3 bulgu üret. "
                    "Genelleme ve değişim yorumlarını inference olarak işaretle.")
            while True:
                next_level = []
                for offset in range(0, len(current), 8):
                    group = current[offset:offset+8]
                    atoms, original_keys = [], {}
                    for finding in group:
                        for source in finding["sources"]:
                            # Distinct quotes from the same chunk must not overwrite
                            # one another in the validator's key lookup.
                            key = "evidence:" + str(len(atoms))
                            original_keys[key] = source["key"]
                            atoms.append({"key": key, "entry_id": source["entry_id"],
                                          "title": source["title"], "event_date": source["event_date"],
                                          "written_at": source["written_at"], "text": source["quote"],
                                          "context": finding["text"][:150]})
                    reduced = []
                    for evidence in batches(atoms):
                        ensure_fresh()
                        raw = self.ai.generate(task, evidence, summary=True)
                        checked = validated_findings(raw, evidence)
                        rejected += len(raw)-len(checked)
                        for finding in checked:
                            for source in finding["sources"]:
                                source["key"] = original_keys[source["key"]]
                        reduced.extend(checked)
                    # Guaranteed contraction even if a model exceeds its requested
                    # output limit or a group needs several evidence batches.
                    next_level.extend(reduced[:3])
                if len(current) <= 8 or not next_level:
                    overview = next_level
                    break
                current = next_level
            if not overview:
                overview = overview_fallback(entries)
        ensure_fresh()
        return {"mode": mode, "coverage": info, "sections": sections,
                "overview": overview, "revision": revision,
                "rejected_findings": rejected,
                "message": "" if all_findings else "Seçilen dönemde bu analiz için yeterli, doğrulanabilir bilgi bulunamadı."}
