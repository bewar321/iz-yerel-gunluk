# Implementation Contract: Yerel RAG Günlüğü

Mode: DEVELOPMENT
Test command: `python3 -m pytest`

## Target
- Türkçe arayüzden günlük yazılabilecek, düzenlenebilecek ve silinebilecek. Olay tarihi ile yazılma tarihi ayrı tutulacak.
- Uygulama ve AI bilgisayarda çalışacak. İlk kurulum ve model indirmelerinden sonra internet gerekmeyecek; günlükler dış servislere gönderilmeyecek.
- Günlüklere doğal dille soru sorulabilecek. Yanıtlar ilgili kayıtların tarihlerini, alıntılarını ve kayda bağlantılarını gösterecek. Yeterli bilgi yoksa bunu açıkça belirtecek.
- Seçilen dönem için konu ve duygu değişimleri özetlenecek. Analizin kapsadığı kayıtlar ve kayıt bulunmayan dönemler belirtilecek; çıkarımlar açıkça ayrılacak ve duygu etiketleri düzeltilebilecek.
- Karar günlüğü: Kararın gerekçeleri, beklentiler ve sonradan kaydedilen sonuçlar birlikte incelenebilecek.
- Bana iyi gelenler: Kullanıcının geçmişte yardımcı olduğunu yazdığı davranışlar, kaynaklarıyla bulunabilecek.
- Kayıtlar AI analizinden çıkarılabilecek. Düzenleme ve silme işlemleri arama indeksine ve türetilen özetlere yansıyacak.
- Günlükler dışa aktarılabilecek ve yedekten geri alınabilecek.
- GitHub'da paylaşılmaya hazır kod, kurulum belgeleri ve kurgu örnek veriler hazırlanacak. Kişisel veriler depoya dahil edilmeyecek.

## Scope
- In: Yukarıdaki hedefler; tek kullanıcı; yerel günlük ve AI.
- Out: Alzheimer modu, çok kullanıcılı hesaplar, bulut senkronizasyonu, ses/fotoğraf işleme, otomatik bildirimler ve tıbbi teşhis.

## Decision Lock
- Tek kullanıcı, tamamen yerel çalışma, sıfırdan başlangıç ve açık kaynak paylaşılabilecek proje.
- Türkçe arayüz; kaynaklı yanıtlar; kayıt ve çıkarım ayrımı; dönem kapsamının görünmesi; kullanıcı tarafından düzeltilebilir duygu etiketleri.
- İlk sürüm: günlük, doğal dille hatırlama, dönem analizi, karar günlüğü ve bana iyi gelenler arşivi.
- Kayıt bazlı AI hariç tutma, düzenleme/silmenin türetilen verilere yansıması, yedek dışa aktarma ve geri yükleme.
- Olay tarihi ve yazılma zamanı ayrı tutulur. Özel veriler açık kaynak depoya girmez.
- Alzheimer özellikleri sonraya bırakıldı. Tıbbi teşhis kapsam dışı.

## Phases
| # | Phase | Risk | Done when |
|---|-------|------|-----------|
| 1 | Günlük ve yerel saklama | HIGH | Kayıt işlemleri, analiz izinleri ve yedekleme testleri geçer. |
| 2 | Yerel RAG ve kaynaklı yanıtlar | HIGH | Kaynak doğruluğu, yetersiz bilgi ve silme/düzenleme senaryoları doğrulanır. |
| 3 | Dönem analizi ve kişisel içgörü | HIGH | Dönem kapsamı, karar karşılaştırması ve kaynaklı öneriler doğrulanır. |
| 4 | Kullanılabilirlik ve açık kaynak hazırlığı | STANDARD | Kurulum belgeleri, örnekler ve tüm testler tamamlanır. |
