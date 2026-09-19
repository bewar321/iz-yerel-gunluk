# İz — Yerel RAG Günlüğü

Gününü yaz, geçmişine soru sor, zaman içindeki değişimini kaynaklarıyla gör.
Türkçe, tek kullanıcılı ve tamamen yerel. MIT lisanslı açık kaynak proje.

## Neler yapar?

- Günlük yazma/düzenleme/silme; olay tarihi ve yazılma zamanı ayrımı.
- Kaynaklı doğal dil araması: gerçek alıntılar, tarihler ve özgün kayda bağlantı.
- Dönemdeki **tüm izinli kayıtları** parça parça okuyan konu/duygu analizi; gün bazında kayıt boşlukları.
- Kullanıcının düzeltilebilir duygu etiketleri, AI özeti ve çıkarım ayrımı.
- Kararın gerekçesi, beklentisi ve sonradan eklenen sonucu yan yana.
- Kendi yazdıklarından “bana iyi gelenler” arşivi.
- Kayıt bazında AI dışında tutma, JSON yedekleme ve atomik geri yükleme.

## Hızlı başlangıç

Python **3.9+** gerekir (3.12 önerilir). Yerel modeller için yaklaşık 4 GB indirme alanı ve
16 GB RAM önerilir. Daha az bellekte model hızları değişir. İnternet yalnız ilk kurulumda
bağımlılıkları ve modelleri indirmek için kullanılır; günlükler bu indirmelere dahil edilmez.

```bash
python3 scripts/setup.py
```

macOS'ta betik resmî Ollama 0.34.2 çalıştırıcısını proje içindeki `data/runtime/` dizinine
indirir; sistem uygulamalarını değiştirmez. Linux/Windows'ta önce
[Ollama](https://ollama.com/download) kurun, sonra aynı betiği çalıştırın.
Kurulum `qwen3:4b` ve `embeddinggemma:latest` modellerini indirir.
Modeller kendi lisanslarına tabidir; uygulamanın MIT lisansı model ağırlıklarını kapsamaz.

**macOS:** `Başlat.command` dosyasını çift tıklayın.

**Linux/macOS terminal:**

```bash
.venv/bin/python3 scripts/run.py
```

**Windows terminal:**

```powershell
.venv\Scripts\python.exe scripts\run.py
```

Arayüz: **http://127.0.0.1:8765**. Terminal açık kalmalıdır; Ctrl+C durdurur.
Model servisi hazır değilse günlük yazma ve yedekleme çalışır; AI ekranı kurulum durumunu gösterir.

### Elle çalıştırma / geliştirme

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
# Ayrı terminalde (model klasörünü açıkça seçebilirsiniz):
OLLAMA_NO_CLOUD=1 ollama serve
ollama pull qwen3:4b
ollama pull embeddinggemma
python3 -m journal
```

Model servisi yalnız `127.0.0.1:11434` üzerinden çağrılır. Çalıştırıcı yeni bir Ollama süreci
başlatırken bulut özelliğini kapatır. Önceden çalışan bir Ollama varsa onu kullanır ve sonlandırmaz;
kullanılan modelin yerel olduğu ayrıca API üzerinden kontrol edilir.
`JOURNAL_MODEL` ve `JOURNAL_EMBED_MODEL` ortam değişkenleriyle kurulu yerel modeller seçilebilir.
Bulut model adları ve uzak modele yönlendiren modeller reddedilir.

## İlk kullanım

1. **Yeni kayıt** ile bir sayfa yaz. Olay tarihini ve istersen duygu etiketini seç.
2. **Geçmişime sor** ekranında bir soru sor. İlk sorgu arama indeksini hazırlar.
3. **Zaman içinde** ekranında tarih aralığı seç. Uzun günlüklerde analiz birkaç dakika veya
   kayıt sayısına göre daha uzun sürebilir. Model hatası olursa eksik rapor gösterilmez.
4. **Kararlarım** için kayıt türünü Karar seç. Gerekçe/beklenti gir, sonucu öğrendiğinde aynı
   kaydı düzenle. Yazılma zamanı korunur; son düzenlenme zamanı veritabanında ayrıca saklanır.
5. **Ayarlar ve yedekler** üzerinden JSON yedeği indir. Geri yükleme mevcut kayıtların tamamının
   yerini alır; önce güncel yedek al. Yedek bütünü doğrulanmadan hiçbir kayıt değiştirilmez.

`examples/kurgu-yedek.json` tamamen uydurulmuş örnekler içerir. Kendi günlüğüne otomatik
aktarılmaz. Yalnız deneme için ayrı bir veri klasörüyle başlatıp ayarlardan geri yükleyebilirsin:

```bash
python3 -m journal --port 8766 --data-dir ./data/demo
```

## Gizlilik ve doğruluk sınırları

- Hesap, telemetri, uzak font/CDN veya bulut AI çağrısı yoktur. Web sunucusu yalnız loopback'e bağlanır.
- Veriler varsayılan olarak proje içindeki git-ignore edilmiş `data/journal.sqlite3` dosyasındadır.
  `JOURNAL_DATA_DIR` veya `--data-dir` ile başka bir yerel klasör seçilebilir.
- Dosyalar uygulama tarafından şifrelenmez. Disk şifrelemesi ve işletim sistemi hesabı güvenliği kullanın.
  Yedek JSON dosyaları açık metindir; kendiniz koruyun. Kaydın silinmesi önceden indirdiğiniz yedekleri silmez.
- AI dışında bırakılan kayıtlar embedding veya analiz için modele gönderilmez. Kayıt düzenleme,
  silme ve geri yükleme arama vektörlerini temizler. Özetler kalıcı saklanmaz; değişikliklerde
  açık ekranlardaki sonuçlar yenilenmek üzere kaldırılır. Başka sekmedeki değişiklikler kısa aralıkla kontrol edilir.
- Alıntının kayıt içinde bulunduğu ve kayıt kimliği doğrulanır. **Bu, AI özetinin anlam bakımından
  doğru olduğunu garanti etmez.** Her AI yorumu özgün alıntıyla kontrol edilmelidir. Kayıtta olmayan
  bir ayrıntı için modelin boş yanıt vermesi istenir; modeller yine hata yapabilir.
- Soru-cevap en ilgili beş metin parçasını kullanır; tam dönem analizi değildir. Zaman içinde
  görünümü tüm izinli parçaları okur, fakat özetleme her ayrıntının çıktıya gireceğini garanti etmez.
- Tarih filtreleri olay tarihine göredir. Göreli zaman yorumuna yerel bugünün tarihi verilir;
  kesin sınırlar için tarih filtresi kullanın. Kayıt bulunmayan gün “olay olmadı” anlamına gelmez.
- Duygu etiketleri özbildirimdir. AI çıkarımları ve “iyi gelenler” tıbbi teşhis veya tedavi önerisi değildir.
- Tek süreç/tek kullanıcı için tasarlanmıştır. Aynı veri klasörüne birden fazla sunucu başlatmayın.

## Mimari ve testler

Python/Flask + Waitress, SQLite, bağımlılıksız tarayıcı arayüzü, Ollama.
Arama: parçalama + yerel embedding + kosinüs/kelime puanı; dönem analizi: ay bazında
sınırlandırılmış bağlamlarla okuma ve özgün alıntıları koruyan kademeli özetleme.
Veri değişimi ve analizler ortak kilitle seri yürütülür; uzun analiz sırasında kayıt işlemi bekleyebilir.

```bash
source .venv/bin/activate
python3 -m pytest
```

Testler sahte model ile deterministik çalışır ve model indirmez. Gerçek model denemesi ayrıca yapılmalıdır.
CI Python 3.9 ve 3.12 üzerinde çalışır. Onaylanmış geliştirme kapsamı `docs/do-task/yerel-gunluk/contract.md` içindedir.

## GitHub'a paylaşma

Yalnız kodu ve kurgu örnekleri paylaşın. `.gitignore` veri/model/venv dosyalarını dışarıda tutar;
kişisel bir JSON yedeğini proje içine eklemeyin. Yayımlamadan önce `git ls-files` ile içeriği inceleyin.
Bu proje için henüz uzak depo ayarlanmadı; uygulama kurulum sırasında GitHub'a veri yüklemez.

Kaynak belgeler: [Ollama embeddings](https://docs.ollama.com/api/embed),
[structured generation](https://docs.ollama.com/api/generate), [yerel çalışma ayarları](https://docs.ollama.com/faq).
