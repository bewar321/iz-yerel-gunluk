"""Date-complete reading of a selected period, with explicit gaps and evidence."""
from collections import Counter, defaultdict
from datetime import date, timedelta

from .rag import chunks_for, validated_findings
from .store import ValidationError, iso_date


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
            entries = [e for e in all_entries if e["analyze"]]
            info = coverage(entries, start, end, len(all_entries)-len(entries))
            months = defaultdict(list)
            for entry in entries:
                months[entry["event_date"][:7]].append(entry)
            sections, all_findings, all_chunks = [], [], []
            rejected = 0
            if mode == "helpful":
                task = ("Yalnız kullanıcının kendisine yardımcı olduğunu AÇIKÇA yazdığı davranış veya deneyimleri bul. "
                        "Sadece bir etkinliğin yapılması yardımcı olduğunun kanıtı değildir. Genel tavsiye verme; "
                        "yazılmamış fayda çıkarma. Her bulguya kaynaktaki tarihi bağla. Yoksa boş findings dön.")
            else:
                task = ("Bu dönemdeki başlıca konuları, kullanıcının kaydettiği duyguları ve varsa değişimleri özetle. "
                        "Tarihleri ayırt et. Özbildirim olmayan duygu yorumlarını inference olarak işaretle. "
                        "Eksik sonuçları tamamlamadan beklenti ve kaydedilmiş sonuçları karşılaştır.")
            for month, month_entries in sorted(months.items()):
                chunks = chunks_for(sorted(month_entries, key=lambda e: (e["event_date"], e["written_at"])))
                findings = []
                for batch in batches(chunks):
                    raw = self.ai.generate(task, batch)
                    checked = validated_findings(raw, batch)
                    rejected += len(raw)-len(checked)
                    findings.extend(checked)
                # Remove exact duplicates introduced by chunk overlap.
                unique = { (f["text"], tuple(s["key"] for s in f["sources"])): f for f in findings }
                findings = list(unique.values())
                sections.append({"month": month, "entries": len(month_entries),
                                 "moods": dict(Counter(e["mood"] or "Etiket yok" for e in month_entries)),
                                 "findings": findings})
                all_findings.extend(findings)
                all_chunks.extend(chunks)
            overview = []
            if mode == "period" and all_findings:
                # Hierarchical reduction; every level retains quotes from original records.
                # Each group is at most eight compact pieces and produces at most three findings.
                current = all_findings
                task = ("Dönemler arasında konu ve duygu değişimlerini karşılaştır. context önceki AI yorumudur, "
                        "kanıt değildir; yalnız text içindeki özgün alıntılara dayan. Her bulguda tarihleri belirt. "
                        "Yalnız bir dönem varsa o dönemi özetle, değişim uydurma. En fazla 3 bulgu üret. "
                        "Genelleme ve değişim yorumlarını inference olarak işaretle.")
                while True:
                    next_level = []
                    for offset in range(0, len(current), 8):
                        group = current[offset:offset+8]
                        atoms = []
                        for finding in group:
                            # A single original citation supplies each compact evidence atom.
                            source = finding["sources"][0]
                            atoms.append({"key": source["key"], "entry_id": source["entry_id"],
                                          "title": source["title"], "event_date": source["event_date"],
                                          "written_at": source["written_at"], "text": source["quote"][:350],
                                          "context": finding["text"][:150]})
                        raw = self.ai.generate(task, atoms)
                        checked = validated_findings(raw, atoms)
                        rejected += len(raw)-len(checked)
                        next_level.extend(checked[:3])
                    if len(current) <= 8 or not next_level:
                        overview = next_level
                        break
                    current = next_level
            return {"mode": mode, "coverage": info, "sections": sections,
                    "overview": overview, "revision": self.store.revision(),
                    "rejected_findings": rejected,
                    "message": "" if all_findings else "Seçilen dönemde bu analiz için yeterli, doğrulanabilir bilgi bulunamadı."}
