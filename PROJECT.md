# PROJECT.md — Yeniden Kullanılabilir RAG Chatbot (ilk proje: Teknopark Yönergesi)

## Şu an neredeyiz (sonraki oturum için)
> **Claude'a not:** bir sonraki oturumun başında, işe girişmeden önce bu bölümü kullanıcıya kısaca (birkaç cümleyle) anlat: ne bitti, sırada ne var, bekleyen kararlar neler. Sonra bu bölümü güncel tut.

- **Son biten (26.11.2026):** ayrı routing kaldırıldı (mentor önerisi) ve yerine **uçtan uca cevap akışı** yazıldı: `rag/answer.py` (girdi kontrolü → retrieval → `prompts/system.md` → Gemini → cevap + kaynaklar). Sohbet / konu dışı / "bilgim yok" kararını cevabı üreten LLM veriyor. `route.py`, `routing.md`, `routing.jsonl` ve `routing.scope` silindi (git geçmişinde duruyor). Test seti `eval/testset.jsonl` (32 soru). LLM'siz kısım test edildi (girdi kontrolü 4/4, 10 cevaplı soruda doğru bölüm LLM'e giden 5 parçanın içinde).
- **İlk LLM testi (26.11):** `answer.py --eval` 30/32, elle inceleme sonrası 32/32 (u02 ve z02 etiket hatası), kaynak 10/10, uydurma yok; q01 cevabı eksik (retrieval). Ayrıntı 9. adımda. Rapor aracı eklendi (mentor için Markdown rapor; şimdi `tests/report.py`).
- **Test seti genişletildi (26.11):** 32 → 67 soru; belgenin 21 ana bölümünün hepsinde en az bir `cevap` sorusu var (önce 6 bölüm). u02 → `cevap`, z02 → `bilgi_yok` düzeltildi; yeni x/u/k/s/g/z soruları eklendi.
- **İkinci LLM testi (26.11, 67 soru, `eval/results/cevaplar2.json`):** otomatik 66/67, inceleme sonrası 67/67 (u06 etiket hatası, düzeltildi), kaynak 30/31. Eksik/yanlış cevap: q01, q21, z09; üçü de **retrieval** kaynaklı (doğru parça LLM'e gitmedi). Ayrıntı 9. adımda.
- **Test kodu ayrıldı (26.11):** ölçüm kodu `rag/`'dan yeni `tests/` klasörüne taşındı (`retrieval_test.py`, `answer_test.py`, `report.py`, açıklaması `tests/README.md`). `rag/` artık yalnızca chatbot'un kendisi. Davranış değişmedi.
- **Son biten (27.11):** reranking (adım 8) denendi ve çıkarıldı. bge-reranker-v2-m3 ve gte-multilingual-reranker-base, 50 aday, CPU: MRR 0.817 → 0.840 / 0.850, Hit@1 7 → 8, ama soru başına ~32 / ~98 sn; bge q01'i 3.'den 15.'ye düşürdü. Kalan hatalar sıralama değil kelime uyuşmazlığı. Ayrıntı 8. adımda.
- **Son biten (27.11, akşam): query rewriting (kural listesi) kodlandı ve LLM'siz ölçüldü, karar bekliyor.** `rag/rewrite.py` + `project.json › queryRewrite` (3 kural: firma → Girişimci, teknopark → Bölge, uymaz/ihlal/ceza → aykırı faaliyet). Kural uyan soruda ikinci bir soru üretilip onunla da aranıyor. Kodda şu an **RRF** birleştirmesi var ve bu en kötü sonuç veren yöntem çıktı (q01 3. → 6.). En iyi görünen "**yalnızca yeni soru**" (C): cevaplı 32 soruda MRR 0.808 → 0.825, Hit@1 23 → 24, Hit@5 31 → 31 (q21 9. → 2. girdi, q24 2. → 7. çıktı). Ayrıntı 5. adımda ("Query rewriting deneyi").
- **Bekleyen karar (kullanıcı, "sonra bakacağız"):** birleştirme yöntemi: RRF / B en yüksek cosine / C yalnızca yeni soru / rewriting'i kaldırmak. Seçildikten sonra: kod buna göre değiştirilir (RRF değilse `search.py › Retriever.search`), `tests/retrieval_test.py` ve `tests/answer_test.py` + `tests/report.py --compare eval/results/answer-20261127-153718.json` ile ölçülür. Uçtan uca LLM testi henüz yapılmadı.
- **Sonra (ölçüme göre):** multi-query (z09, tek mesajda iki soru), İngilizce sorular (z08, z02); sparse/hybrid retrieval yalnızca doğru parça büyük havuzda bile yoksa. Ödev şimdilik bekletiliyor (kullanıcı, 27.11).
- **Repo (27.11):** reranking kaydı ve query rewriting kodu `feat/docker-pgvector` dalına commit edildi (push edilmedi, `main`'e birleşmedi). `eval/reports/` altında kullanıcının yeniden adlandırdığı raporlar (`ilk_test.md`, `vectordb_sonrasi_test.md`; eski adları silinmiş görünüyor) commit'e girmedi.
- **Bekleyenler:**
  - **Docker hazır (26.11):** Sanal Makine Platformu açıldı, motor çalışıyor (`docker info` → 29.9.3, Docker Desktop). Yapılacaklar "Yol haritası › Ara iş"te. 27.11: `hello-world` çalıştı, Docker temel kavramları adım adım öğreniliyor (ders 1: image, container, `run`, `ps -a`, `rm`, `--rm`; ders 2: `-d`, `-p`, `logs`, `exec`, `stop`/`start`; ders 3: volume, `--env-file`). **Veritabanı PostgreSQL + pgvector seçildi** (MySQL bırakıldı, 27.11), container `tkpark-db` 5432'de çalışıyor (volume `tkpark-pg-data`), oyuncak vektörlerle `<=>` doğrulandı. **Compose hazır** (`docker compose up -d`, `(healthy)`), DBeaver kurulu (bağlantı henüz denenmedi, gerekince). **DB işi 5 aşama:** 1 altyapı ✅ · 2 tablo tasarımı ✅ (`rag/schema.sql` → `rag_indexes` + `rag_chunks`, `embedding vector` boyutsuz (A seçeneği; boyutu kod kontrol eder), `position` FAISS sırasını korur) · 3 `embed.py` DB'ye yazıyor ✅ · 4 `search.py` DB'den sorguluyor ✅ · 5 doğrulama ✅ (Hit@5 10/10, MRR 0.817, FAISS'le aynı). **DB ara işi bitti (27.11); chatbot artık pgvector'le çalışıyor** (`vectorStore.type: "pgvector"`; Docker'sız yedek `"flat"`). Dal `feat/docker-pgvector`, `main`'e henüz birleşmedi. Sırada (takvime göre): Streamlit/Gradio arayüzü (ödev). **Çalışma biçimi (27.11):** komutları kullanıcı kendisi çalıştırıyor, Claude önce anlatıyor ve çıktıyı açıklıyor; uzun/zor yerlerde Claude devralıyor. Kullanıcı tercihi: her Docker adımı çalıştırılmadan önce anlatılacak.
  - 7. adımın retrieval testi 26.11'de tekrar çalıştırıldı, sonuç aynı (Hit@5 10/10, MRR 0.817).
  - `feat/1.5-retrieval-test` dalının silinmesi karar bekliyor.
  - Query rewriting ve multi-query reranking'den sonra ölçüme göre değerlendirilecek.
  - Agentic RAG fikri "Yol haritası"nda not edildi (ileride).
  - **Ara iş (mentor, 26.11):** vector DB'yi Docker'da çalışan bir veritabanına taşı, vektör sorgularını oradan yap. Önce MySQL; MySQL'de vektör araması yoksa başka bir veritabanına geç. Docker Compose ilk aşamada yalnızca DB, sonra backend ve frontend eklenecek. Ayrıntı "Yol haritası"nda.
- **Takvim (26.11'de yapıldı, LLM ödevi teslimi ~6.12):** gün 1–3 Docker + DB (3. günün sonunda bitmediyse bırakılıp ödeve geçilecek) · gün 4–5 adım 9 prompt, LLM cevabı, kaynak gösterme, uçtan uca akış · gün 6 test ("bilgim yok": x01–x03, u01–u03) · gün 7–8 Streamlit/Gradio arayüzü ve rapor · gün 9–10 tampon. Ödev "kullanılabilir, belgeye dayanan (uydurmayan) chatbot" istiyor. Belge: aynı yönerge; vakit kalırsa farklı bir belgeyle yeni proje paketi (taşınabilirlik testi). Reranking ödev için şart değil.
- **Dikkat:** Gemini ücretsiz planı dakikada 15 istekle sınırlı (aşağıda "API sınırı"). Eval'ler bu yüzden yavaş çalışabilir.

## Durum (26.11.2026)
Proje 9 adımlık RAG akışına göre ilerliyor. **1–4 ve 6 tamam, 7 (retrieval) bitmek üzere** (commit edildi; reranking'den önce test yeniden çalıştırılacak). Retrieval deneyinde Hit@5 10/10, MRR 0.817. `minScore` 0.0'da kalıyor. 5. adımdaki ayrı routing 26.11'de kaldırıldı; konu dışı ve sohbet mesajlarını 9. adımdaki cevap prompt'u yönetiyor. 9 (prompt) ve LLM cevabı `rag/answer.py`'de yazıldı, LLM ile test bekliyor. Sırada LLM testi, arayüz ve 8 (reranking) var. Query rewriting ve multi-query, reranking'den sonra ölçüme göre değerlendirilecek.

| # | Adım | Durum | Nerede | Kısaca |
|---|---|---|---|---|
| 1 | Metin hazırlığı + metadata | ✅ | `extract.py`, `loaders/pdf.py`, `chunk.py` | PyMuPDF; 37 sayfa; 96 başlık; sayfa/bölüm/başlık metadata'sı |
| 2 | Chunking | ✅ | `chunk.py` | Başlığa göre bölme + `RecursiveCharacterTextSplitter`; 300 token / 50 overlap; 186 chunk |
| 3 | Embedding | ✅ | `embed.py` | `multilingual-e5-base`, 768 boyut, `passage:` öneki, normalize |
| 4 | Vector DB | ✅ | `embed.py` → `faiss.index` | FAISS `IndexFlatIP` (kesin arama) |
| 5 | Query processing | 🔶 | `answer.py › check_input`, `rewrite.py`, `search.py` | Ayrı routing kaldırıldı (26.11), yönlendirme 9'da prompt ile. Girdi kontrolü (kural) var. Query rewriting (kural listesi) 27.11'de yazıldı, birleştirme yöntemi karar bekliyor. Multi-query sonra |
| 6 | Query embedding | ✅ | `search.py` | Aynı model, `query:` öneki, normalize |
| 7 | Retrieval | 🔶 | `search.py`, `tests/retrieval_test.py`, `eval/retrieval.jsonl` | Top-5; Hit@5 10/10, Hit@1 7/10, MRR 0.817; `minScore` 0.0; reranking'den önce test tekrarlanacak |
| 8 | Reranking | ❌ | — | 27.11 denendi (bge-reranker-v2-m3, gte-multilingual-reranker-base): MRR 0.817 → 0.84–0.85, ama CPU'da soru başına 32–98 sn; çıkarıldı |
| 9 | Prompt oluşturma | 🔶 | `prompts/system.md`, `answer.py` | system prompt + numaralı chunk'lar (bölüm, sayfa) + soru; sohbet / konu dışı / "bilgim yok" kararı burada. LLM testi bekliyor |
| → | LLM cevabı, kaynak gösterme, değerlendirme | 🔶 | `answer.py`, `tests/answer_test.py`, `eval/testset.jsonl` | 67 soruda 66/67 (inceleme sonrası 67/67), kaynak 30/31; kalan hatalar retrieval kaynaklı |

## RAG akışı: adım adım

### 1. Metin hazırlığı + metadata ✅
- **Okuma:** PyMuPDF (`rag/loaders/pdf.py`). 41 sayfadan 37'si alınıyor. Kapak (s.1) ve İçindekiler (s.2–4) `skipPages` ile atlanıyor. Çıktı `index/<id>/pages.json` (~148 bin karakter).
- **Temizlik** (`chunk.py`): fazla boşluklar teke indiriliyor, PDF'in kırdığı satırlar paragraf/madde olarak birleştiriliyor, satır sonunda `-` ile bölünen kelimeler birleştiriliyor. Unicode zaten NFC. Küçük harfe çevirme ve noktalama silme yok, çünkü embedding modeli doğal metinle çalışıyor.
- **Yapı tespiti:** `project.json › chunking.headingPatterns` regex'leriyle 4 seviye (`1.`, `7.1.`, `7.1.5.`, `a.`). 96 başlık bulunuyor; 84'ünün altında metin var, kalanlar yalnızca üst başlık. Yakalanan biçimler: numara ile başlık ayrı satırda, boşluksuz `8.1.BAŞLIK`, alt satıra taşan büyük harfli başlık.
- **Metadata** (kendi kodumuz, LangChain değil): `source`, `section` (ör. `7.1.5`), `title`, `path` (başlık yolu), `pages`. 186 chunk'ın hepsinde sayfa bilgisi var; 27'si iki sayfaya yayılıyor.
- **Tablo/görsel:** içerikte yok. PyMuPDF'in bulduğu 3 tablo İçindekiler sayfalarında (atlanıyor). Görseller logo ve kapak resimleri.

### 2. Chunking ✅
- **Strateji:** önce numaralı bölüme göre bölme; bir chunk asla iki bölümü karıştırmıyor. 300 tokeni aşan bölüm kendi içinde LangChain `RecursiveCharacterTextSplitter` ile bölünüyor. Bölme sırası: `•` madde başı → satır → cümle sonu → boşluk.
- **Boyut token cinsinden** (`maxTokens` 300, `overlap` 50 ≈ %17). Token sayımı embedding modelinin tokenizer'ıyla yapılıyor (`embedding.model`'den okunuyor). Neden token: model 512 tokenden fazlasını sessizce kesiyor ve Türkçede karakter sayısı token sayısını tutmuyor (benzer token sayıları 205–1426 karaktere denk geliyor).
- **Etiket:** her chunk başlık yoluyla başlıyor: `7. … > 7.1. … > 7.1.5. …` (186/186).
- **Sonuç:** 186 chunk, 58–298 token (medyan ~227). 30 bölüm bölündü ve bunlardan 132 chunk çıktı; 54 bölüm tek parça. Overlap yalnızca bölünen bölümlerde var. Metin kaybı yok. Sınırı aşan chunk oluşursa `chunk.py` hata verip duruyor.

### 3. Embedding ✅
- **Model:** `intfloat/multilingual-e5-base`, `sentence-transformers` ile yerelde (adaptör yok). 768 boyut, 512 token sınırı, ~1.1 GB. Düz `e5-base` değil, **multilingual** sürüm.
- **Önekler:** chunk'lar `passage: `, sorular `query: ` (`project.json › embedding`). Önekler olmadan kalite belirgin düşüyor.
- **Kontroller** (`embed.py`, kaydetmeden önce): `chunks.json` güncel mi (ayarlar, tokenizer, `pages.json`'dan yeni mi), önek dahil token ≤ 512 (en fazla 302), vektör sayısı = chunk sayısı, NaN yok, norm = 1. Biri başarısızsa hiçbir dosya yazılmıyor.
- **Süre:** 186 chunk ~17 sn (Apple M2, CPU). Tepe RAM ~750 MB.

### 4. Vector DB ✅
- **FAISS `IndexFlatIP`** (`faiss-cpu`): kesin arama. Soru bütün vektörlerle karşılaştırılıyor. Vektörler normalize olduğu için iç çarpım = cosine benzerliği.
- **Dosyalar:** vektörler `index/<id>/faiss.index` (0.57 MB), metin ve metadata `index.json` (0.26 MB). Vektör `i` → `chunks[i]`.
- **Kontrol:** `embed.py` diskten okunan indeksin ilk `topK` sonucunu numpy kesin aramasıyla karşılaştırıyor (yonerge: 1.000).
- **Neden flat, HNSW değil:** 186 vektörde kesin arama HNSW'den ~10 kat hızlı (22 µs ve 208 µs), ayar gerektirmiyor ve hiçbir sonucu kaçırmıyor. Ölçümler karar günlüğünde (24.11). On binlerce vektörü geçerse `faiss.IndexHNSWFlat(dim, 16)`'ya geçilir.

### 5. Query processing 🔶
- **26.11.2026 kararı: ayrı routing adımı kaldırıldı** (mentor önerisi). Her geçerli soru retrieval'a girer. Sohbet, konu dışı ve "bilgim yok" davranışını 9. adımdaki cevap prompt'u (`prompts/system.md`) yönetir. LLM kararı kendisine verilen chunk'lara bakarak verir; belgenin kapsamını ayrıca bilmesi gerekmez. Gerekçe karar günlüğünde (26.11).
- **Yeni akış:** soru → girdi kontrolü → query embedding (6) → retrieval (7) → reranking (8) → LLM: system prompt + chunk'lar + soru (9) → cevap. Soru başına **tek LLM çağrısı**.
- **Kalan: girdi kontrolü (kural, LLM'e gitmez).** `answer.py › check_input`. Boşluklar kırpıldıktan sonra `input.minChars` (3) altı, `input.maxChars` (1000) üstü ya da hiç harf içermeyen mesaj → `messages.json › geçersiz`. Bu routing değil, basit bir doğrulama. Test: 4/4 (boş, tek harf, harfsiz, ~1350 karakter).
- **Dosyalar (26.11):** `rag/route.py`, `prompts/routing.md`, `eval/routing.jsonl` silindi; `project.json`'da `routing` yerine `input: {minChars, maxChars}` var. `routing.jsonl`'daki 32 soru `eval/testset.jsonl`'a dönüştürüldü (bkz. 9. adım).
- **Önceki deneme: LLM ile routing (24.11, kaldırıldı).** Kayıt için:
  - `geçersiz` kuralla; `belge` / `sohbet` / `konu_dışı` ayrı bir Gemini çağrısıyla (JSON şeması, enum) ayrılıyordu. Prompt'a belgenin kapsamı `routing.scope` cümlesiyle veriliyordu. `sohbet` cevabını aynı çağrı yazıyordu. LLM hata verirse soru `belge` sayılıyordu.
  - Test seti 32 soru (`belge` 15, `konu_dışı` 9, `sohbet` 4, `geçersiz` 4), sonuç **32/32**. İlk çalıştırmada u01 (yemekhane) `belge` etiketliydi, LLM `konu_dışı` dedi; yemekhane belgede geçmediği için etiket değiştirildi. Bir sohbet cevabında "olabildigime" yazım hatası görüldü.
  - Bedeli: soru başına ek bir LLM çağrısı (ortalama ~870 ms, en fazla 2.3 sn) ve ücretsiz kotanın yarısı.
  - Neden kaldırıldı: `routing.scope` tek bir belgeyi tek cümleyle anlatıyor. Çok belgede bu cümle ya eksik kalır (geçerli sorular reddedilir) ya da sürekli elle güncellenir; yani ölçeklenmez. Ayrıca 9. adımdaki "bilgim yok" kuralı konu dışı soruları zaten karşılıyor.
  - Embedding ile sınıflandırma ve retrieval puan eşiği daha önce elenmişti (örnek cümlelere bağlılık; konu dışı 0.76–0.78, cevaplı 0.80–0.86, fark 0.02).
- **Query rewriting deneyi (27.11, kural listesi) 🔶 karar bekliyor:**
  - **Neden:** kalan retrieval hataları kelime uyuşmazlığı. Kullanıcı "firma" diyor, belge "Girişimci" diyor (belgede "firma" 7, "Girişimci" 552 kez); "teknopark" 41, "Bölge" 477; q21'in cevabı 17. bölüm "AYKIRI FAALİYET UYGULAMA YETKİSİ", soruda ise "kurallarına uymazsam" var ("ihlal" 4, "ceza" 6 kez geçiyor). Reranking bunu çözmedi (8. adım).
  - **Seçenekler ve seçim (kullanıcı):** LLM ile yeniden yazma (soru başına ek Gemini çağrısı, ücretsiz planda dakikada ~7 soru) yerine **kural listesi** seçildi: ücretsiz, anında, deterministik. Bedeli: İngilizce soruya ve z09'a (tek mesajda iki soru) yaramaz, liste proje başına elle yazılır. Aramada **orijinal + yeni soru** birlikte kullanılsın dendi (yeniden yazma kötüyse orijinalin bulduğu parçalar kaybolmasın diye).
  - **Kurallar (`project.json › queryRewrite.rules`):** `firma` → `Girişimci`, `teknopark` → `Bölge`, `uymaz` / `ihlal` / `ceza` → `aykırı faaliyet`. İlk ikisi `system.md`'de zaten tanımlı belge terimleri. **`şirket` → `Girişimci` bilerek konmadı:** belgede "şirket" 391 kez geçiyor, 376'sı "Yönetici Şirket" (işletmeci); eşleme Yönetici Şirket sorularını bozardı.
  - **Nasıl çalışıyor (`rag/rewrite.py`):** her kural kelime başından eşleşir, büyük/küçük harf fark etmez, ek de kapsanır ("Teknoparktan", "firmanın", "İhlal"); eşleşen kelimenin tamamı yerine geçer. Hiçbir kural uymazsa soru değişmez ve arama eskisiyle birebir aynı. Üretilen cümle dil bilgisi açısından bozuk olabilir ("Bölge ayrılmak istersem…"); amaç düzgün cümle değil belgenin kelimesini aramaya katmak. Örnekler: "Firma kabul şartları nelerdir?" → "Girişimci kabul şartları nelerdir?", "Yönerge kurallarına uymazsam ne olur?" → "Yönerge kurallarına aykırı faaliyet ne olur?", "Bakanlık teknoparktaki firmaları denetleyebilir mi?" → "Bakanlık Bölge Girişimci denetleyebilir mi?".
  - **Kodda şu an (`rag/search.py › Retriever.search`):** soru yeniden yazıldıysa iki soru da embed edilip aranır (~15 ms ek), iki sıralama **RRF** ile birleştirilir (`rrf_merge`, her chunk 1 / (60 + sıra) toplar); gösterilen puan chunk'ın iki aramadaki en yüksek cosine'i (rapordaki puan aralıkları eskisiyle karşılaştırılabilsin diye). `Retriever(project, rewrite=None/True/False)`, testlerde `--no-rewrite`. `answer.py` sonucunda `rewrite` alanı (aramada kullanılan ikinci soru), `settings()`'te `queryRewrite`.
  - **Ölçüm 1, `tests/retrieval_test.py` (RRF, 16 soru, 4'ü yeniden yazıldı: q01, q05, q10, u03):** Hit@1 7 → 8/10, Hit@3 10 → 9, Hit@5 10 → **9**/10, MRR 0.817 → 0.850. q05 2. → 1., ama **q01 3. → 6.** (ilk 5'ten çıktı). Konu dışı/cevapsız puan ayrımı değişmedi (boşluk 0.02; u02, u03 ayrılamıyor).
  - **Neden RRF q01'i bozdu:** yeni soru tek başına daha iyi; 10.1 parçaları orijinal soruda 3./31./33. sırada, yeni soruda 3./6./15. sırada (10.1-1 komisyon kabulü 3., 10.1-0 online başvuru 6.). RRF iki listede de orta sıralarda olan parçaları (15.1-0, 3-7) öne çıkarıyor, yalnızca tek listede yüksekte olan doğru parçayı geri itiyor.
  - **Ölçüm 2, birleştirme yöntemleri karşılaştırması (LLM yok, geçici betikle; testset.jsonl'daki `sections`'ı olan 32 soru, 7'si yeniden yazıldı):**

    | Yöntem | retrieval.jsonl (10) Hit@1 / Hit@5 / MRR | testset.jsonl (32) Hit@1 / Hit@5 / MRR |
    |---|---|---|
    | A. Rewriting yok | 7 / 10 / 0.817 | 23 / 31 / 0.808 |
    | RRF (kodda olan) | 8 / 9 / 0.850 | 24 / 30 / 0.820 |
    | B. En yüksek cosine (chunk'ın iki aramadaki en yüksek puanı) | 8 / 10 / 0.867 | 24 / 30 / 0.814 |
    | C. Yalnızca yeni soru (kural uyduysa orijinal aramaya katılmaz) | 8 / 10 / 0.867 | **24 / 31 / 0.825** |

    | Yeniden yazılan soru | A | RRF | B | C |
    |---|---|---|---|---|
    | q01 Firma kabul şartları | 3 | 6 | 3 | 3 |
    | q05 Teknoparktan ayrılma bildirimi | 2 | 1 | 1 | 1 |
    | q10 Öğretim üyeleri | 1 | 1 | 1 | 1 |
    | q15 Yönetim kurulu kaç kişi | 1 | 1 | 1 | 1 |
    | q16 Yerleşkeler | 1 | 1 | 1 | 1 |
    | **q21 Kurallara uymazsam** | 9 | 6 | 7 | **2** |
    | **q24 Bakanlık denetimi** | 2 | 2 | 7 | **7** |

  - **Yorum:** C en iyi görünüyor; q21 ilk kez ilk 5'e girdi ve q01'de 10.1'in ikinci bir parçası (online başvuru) 31. → 6. sıraya geldi. Ama q24 bozuldu: iki kelime birden değişince ("teknoparktaki firmaları" → "Bölge Girişimci") soru anlamını yitirdi ve orijinal soru aramada olmadığı için telafi edilemedi (kural listesinin bilinen riski). B'de de q24 7. sıraya düştü. Net kazanç küçük: 32 soruda +1 Hit@1, ilk 5'te değişim yok (C'de q21 girdi, q24 çıktı).
  - **Dikkat (iyimserlik):** kurallar q01/q21 hataları bilinerek seçildi; sonuç test setine göre ayarlanmış olabilir. Gerçek sorularda kazanç daha az olabilir. Kural sayısı ve yeniden yazılan soru az (32'de 7).
  - **Bekleyen karar:** RRF / B / C / rewriting'i kaldırmak. Olası iyileştirmeler (denenmedi): C'de bir soruda birden çok kural uyunca yalnızca birini uygulamak; C + orijinal soruyu düşük ağırlıkla katmak (ağırlıklı RRF).
  - **Ölçüm komutları:** `python tests/retrieval_test.py` ve `--no-rewrite`; uçtan uca `python tests/answer_test.py` → `python tests/report.py --compare eval/results/answer-20261127-153718.json` (önceki: pgvector, rewriting yok, tür 67/67, kaynak 31/32). Ölçüm 2'deki betik projede değil (geçiciydi); karar sonrası gerekirse `tests/`'e eklenebilir.
- **Sonra (ölçüme göre):**
  - **Multi-query:** soruyu birkaç parçaya/biçime bölüp sonuçları birleştirme (z09: tek mesajda iki soru). LLM gerektirir.
  - **İngilizce sorular:** kural listesi yardım etmez; LLM ile rewriting veya multi-query'de ele alınır.
  - Hit@5 zaten 31/32 olduğu için kazanç Hit@1 ve MRR'de, bir de LLM'e giden parçaların kapsamında (q01'in 3 parçası) aranır.

### 6. Query embedding ✅
- `search.py`: soru, chunk'larla aynı modelle (`embedding.model`) `query:` önekiyle ve normalize edilerek embed ediliyor.
- Açılışta `index.json`'daki model `project.json` ile uyuşmazsa ya da `faiss.index` ile chunk sayısı farklıysa program duruyor.
- Süre: soru başına ~15 ms. Uçtan uca darboğaz bu adım (arama ~0.02 ms).

### 7. Retrieval 🔶
- **Kullanım:** `python rag/search.py "soru"` (tek soru), `python tests/retrieval_test.py` (soru seti, Hit@K/MRR). `topK` = 5.
- **Soru seti** `projects/yonerge/eval/retrieval.jsonl`, 16 soru:
  - 10 cevaplı (kolay/orta/zor)
  - 3 konu dışı (hava durumu, makarna tarifi, maç sonucu)
  - 3 cevapsız: konusu belgede var ama cevabı yok (yemekhane saati, metrekare fiyatı, genel müdürün adı)
- **Sonuç (e5-base + FAISS flat):**

  | Metrik | Sonuç |
  |---|---|
  | Hit@1 | 7/10 |
  | Hit@3 | 10/10 |
  | **Hit@5** | **10/10** (hedef tuttu) |
  | MRR | 0.817 |

  | Doğru bölüm kaçıncı sırada | Sorular |
  |---|---|
  | 1. | q02 ortak alanlar, q03 kira/aidat gecikmesi, q04 tadilat izni, q06 personel takibi, q07 muafiyet raporu, q09 kuluçka mezuniyeti, q10 öğretim üyeleri |
  | 2. | q05 ayrılma bildirimi |
  | 3. | q01 firma kabul şartları, q08 yazılım KDV istisnası |

- **q10 etiketi (24.11):** beklenen bölümlere 16.3 eklendi. 16.3 "Araştırma İş Birliği", öğretim üyelerinin projelerde yer alabileceğini doğrudan söylüyor. Önce yalnızca 16.1 doğru sayılıyordu ve q10 21. sıradaydı. Sebep dosyadaki `note` alanında yazıyor.
- **Puan aralıkları (1. sonucun cosine puanı):**

  | Grup | min | max |
  |---|---|---|
  | Cevaplı | 0.804 | 0.860 |
  | Konu dışı | 0.762 | 0.784 |
  | Cevapsız | 0.768 (u01) | 0.859 (u03) |

  - Konu dışı sorular puanla **ayrılabiliyor**, ama boşluk yalnızca 0.02.
  - Cevapsızlardan u02 (0.835) ve u03 (0.859) cevaplı sorulardan **ayrılamıyor**; bunları LLM'in "bilgim yok" demesi yakalamalı.
- **`minScore` kararı (24.11): 0.0.** Boşluk çok dar olduğu için puan eşiği kullanılmıyor. Konu dışı ve cevapsız soruları 9. adımdaki cevap prompt'u ("bilgim yok" kuralı) yakalar (26.11'e kadar konu dışı soruları ayrı routing yakalıyordu). (Elenen seçenek: ~0.79 eşikle konu dışı soruları baştan elemek.)

### 8. Reranking ❌ (27.11 denendi, kullanılmıyor)
- **Neden denendi:** Hit@1 %70 ve ilk sonuçların puanları birbirine çok yakın (ör. q01'de 0.827 / 0.826 / 0.825).
- **Deney (27.11):** dense aramadan (e5-base + pgvector) ilk 50 aday → cross-encoder (`sentence-transformers` `CrossEncoder`, `max_length` 512) → ilk 5. `project.json › rerank` ile açılıp kapanıyordu. Ölçüm `tests/retrieval_test.py` (16 soru, 10 cevaplı), CPU (Ryzen 7 7730U, GPU yok). Uçtan uca LLM testi yapılmadı.

  | Metrik | Reranking yok | `BAAI/bge-reranker-v2-m3` (568M) | `Alibaba-NLP/gte-multilingual-reranker-base` (306M) |
  |---|---|---|---|
  | Hit@1 / Hit@3 / Hit@5 | 7 / 10 / 10 | 8 / 9 / 9 | 8 / 8 / 10 |
  | MRR | 0.817 | 0.840 | 0.850 |
  | Soru başına ek süre | ~0 | ~32 sn | ~98 sn (sebebi araştırılmadı) |
  | Disk / RAM | — | 2.2 GB / süreç ~4.2 GB | 0.6 GB / ölçülmedi |
  | Konu dışı ↔ cevaplı puan boşluğu | 0.02 (cosine) | 0.023 | 0.31 |

  - Değişenler (doğru bölümün sırası, önce → bge / gte): q01 3 → 15 / 4, q04 1 → 3 / 1, q05 2 → 1 / 1, q08 3 → 1 / 4; diğer 6 soru hep 1.
  - bge q01'de 50 adayın hepsine ~0.02 verdi (hiçbirini ilgili bulmadı); "firma" ↔ "Girişimci" eşleşmesini yapamıyor.
  - Modeller: ikisi de çok dilli (gte README'sinde `tr` var), Apache-2.0; gte `transformers` ≥ 5.18'de `trust_remote_code` gerektirmiyor.
- **Neden işe yaramadı:** Hit@5 zaten 10/10, iyileşecek yer yalnızca Hit@1'di. Kalan hatalar (q01, q21, z09) sıralama değil kelime uyuşmazlığı ("firma" ↔ "Girişimci", "kural ihlali" ↔ yaptırım) ve tek mesajda iki soru; cross-encoder parçaları tek tek puanlar, soruyu bölemez. Modeller web arama verisiyle eğitilmiş, alan Türkçe yönetmelik. Test seti küçük (bir soru = %10). CPU'da cross-encoder 50 çifti baştan okuduğu için pahalı.
- **Karar (27.11, kullanıcı):** reranker çıkarıldı (kod geri alındı, `project.json`'da `rerank` yok). Sırada query rewriting.
- **Aday havuzu notu (27.11, dense sırası):** q21'de 17. bölüm 9./13./17. sırada, z09'da 5.4 17. sırada, q01'de 10.1'in diğer parçaları 28./31./33. sırada.
- **Sparse / hybrid retrieval (BM25 + dense) kararı (27.11):** ölçüme göre, ileride. Reranker yalnızca havuzdakini yeniden sıralar; sparse ise havuza giremeyen parçayı getirmek için (anahtar kelime, sayı, kanun adı). Doğru parça büyük havuzda bile yoksa eklenir. Türkçe ekler BM25'i zayıflatır (kira/kirası/kiranın), kök bulma gerekir; PostgreSQL'in yerleşik `turkish` tam metin araması (`tsvector`, snowball) aynı veritabanında hybrid'e izin verir, sonuçlar RRF ile birleştirilir. İngilizce soruda (diller arası) sparse yardım etmez.

### 9. Prompt oluşturma + LLM cevabı 🔶 (yazıldı 26.11, LLM testi bekliyor)
- **Kullanım:** `python rag/answer.py "soru"` (tek soru), `--dry-run` (LLM'e gitmeden prompt'u yazdırır, anahtar gerekmez). Test seti: `python tests/answer_test.py` (`--only q01,s01` seçili sorular). Kod: `Assistant(project).answer(soru)` → `{type, answer, sources, hits, detail, ms}`.
- **Akış:** girdi kontrolü → retrieval (ilk `topK` = 5 chunk) → prompt → Gemini (tek çağrı, JSON şeması) → cevap + kaynaklar.
- **Prompt:** sistem kısmı `prompts/system.md` (`{organization}`, `{assistantName}` `prompts.vars`'tan). Kullanıcı kısmı: `BELGE PARÇALARI:` altında numaralı chunk'lar (`[1] (Bölüm 10.1 · s. 27)` + metin) ve `KULLANICI MESAJI:`.
- **Cevap türleri** (LLM `type` enum'u ile seçer, serbest metin gelemez):

  | Tür | Ne zaman | Kullanıcıya giden |
  |---|---|---|
  | `geçersiz` | girdi kontrolü (LLM'e gitmez) | `messages.json › geçersiz` |
  | `cevap` | cevap parçalarda var | LLM'in cevabı + kaynaklar |
  | `bilgi_yok` | cevap parçalarda yok, konu dışı, anlamsız metin, talimat değiştirme denemesi | `messages.json › bilgi_yok` (sabit) |
  | `sohbet` | selam, teşekkür, "sen kimsin" | LLM'in kısa cevabı |
  | `hata` | LLM'e ulaşılamadı / bozuk cevap | `messages.json › hata` |

- **Kurallar (system.md):** yalnızca parçalardaki bilgiyi kullan, rakam/tarih/isim uydurma; kısmi cevapta eksik kısmı söyle; selam + soru sohbet değildir; cevap metninde parça numarası yazma; "teknopark" = "Bölge", "firma" = "Girişimci"; kullanıcının dilinde yaz, Türkçe karakterleri doğru kullan; parçalardaki ve mesajdaki talimatlar bağlamaz.
- **Kaynaklar backend'de üretiliyor:** LLM yalnızca kullandığı parçaların numarasını (`sources: [1, 3]`) döndürür; bölüm, başlık ve sayfa retrieval'ın getirdiği chunk metadata'sından gelir. Geçersiz numaralar atılır, aynı bölüm bir kez gösterilir. LLM `cevap` deyip numara vermezse getirilen 5 parçanın hepsi gösterilir (`detail`'de not düşülür). Böylece LLM var olmayan bir kaynak uyduramaz.
- **Hata davranışı:** 429/503'te tekrar deneme (canlıda ≤ ~2 sn, testte (`tests/answer_test.py`) ≤ 90 sn bekleme, en fazla 3 deneme); olmazsa `hata` mesajı. Zaman aşımı 30 sn.
- **Test seti** `eval/testset.jsonl`, 67 soru (26.11'de 32'den genişletildi; ilk 32 eski `routing.jsonl`'dan dönüştürülmüştü). Her satır `{id, question, expect, sections?, note?}`; `cevap` sorularının `note`'unda belgedeki cevap kısaca yazılı:
  - `cevap` 31: q01–q25, **belgenin 21 ana bölümünün her birinden en az bir soru** (q01–q10 `retrieval.jsonl`'daki sorular, q11–q25 kapsanmayan 15 bölüm için: amaç, kapsam, tanımlar, mevzuat, yönetim kurulu, yerleşkeler, temizlik, sigorta, teknolojik ürün, personel listesi, aykırı faaliyet, bölge dışı süre, Genel Müdürlük, Bakanlık denetimi, yürürlük); u02 (kısmi cevap, 7.2.1); z01 ve z06 (selam + soru), z07 (yazım hatalı), z08 (İngilizce, cevabı belgede var), z09 (iki bölümden iki soru)
  - `bilgi_yok` 22: x01–x06 ve k04–k09 (konu dışı / genel bilgi), u01, u03–u06 (belgeye yakın, belgede hüküm yok: yemekhane, genel müdür, kreş, Wi-Fi şifresi, sigara), z02 (İngilizce, belgede yok), z03 (anlamsız metin), z04 ve z10 (talimat değiştirme), z05 (ofiste kedi)
  - `sohbet` 7 (s01–s07), `geçersiz` 7 (g01–g07: boş, kısa, yalnızca boşluk, harfsiz, çok uzun)
  - **Etiketleme kuralı (u02/z02 hatasından sonra):** etiket soruya göre değil belgeye göre konur. Belgede konuyla ilgili hüküm varsa ama sorulan ayrıntı yoksa soru **kısmi `cevap`** sayılır; `bilgi_yok` yalnızca ilgili hiçbir hüküm yoksa. Her `cevap` sorusunun bölümü chunk'larla eşleştirildi; u sorularındaki terimlerin belgede geçmediği arandı.
- **Ekran özeti (`tests/answer_test.py`):** tür doğruluğu ve karışıklık tablosu, kaynak doğruluğu (beklenen bölüm gösterilen kaynaklarda mı), **uydurma riski** (`bilgi_yok` beklenirken cevap verdi), **fazla temkin** (cevap beklenirken `bilgi_yok` dedi), gecikme. Cevap metinlerinin doğruluğu otomatik ölçülmüyor; çıktıdaki cevaplar elle okunmalı.
- **LLM'siz test (26.11):** `--dry-run` ile prompt doğru oluşuyor; girdi kontrolü 4/4; 10 cevaplı sorunun hepsinde beklenen bölüm LLM'e giden 5 parçanın içinde.
- **İlk LLM sonucu (26.11, gemini-3.5-flash-lite, temperature 0.1, topK 5):**

  | Ölçüm | Sonuç |
  |---|---|
  | Tür doğruluğu (otomatik) | 30/32 (%94) |
  | Tür doğruluğu (elle inceleme sonrası) | 32/32: iki "hata" etiket hatası (u02, z02) |
  | Kaynak doğruluğu | 10/10 |
  | Uydurma | yok (otomatik işaretlenen u02 incelemede uydurma değil) |
  | geçersiz / sohbet | 4/4 / 4/4 (sohbet cevapları kısa ve Türkçe karakterleri doğru) |
  | Gecikme (bekleme hariç) | ort 2.9 sn, medyan 2.5 sn, en fazla 5.8 sn (28 çağrı) |
  | Geçici API hatası | 503 ×3, 429 ×2 (bir kez 60 sn kota beklemesi) |

  - **u02 "metrekare başına kaç TL" → `cevap`:** LLM, 7.2.1'deki "bedeller her yıl Yönetim Kurulu tarafından belirlenir" bilgisini verip TL tutarının belgede olmadığını söyledi. Belgede doğrulandı; uydurma değil, doğru kısmi cevap. Etiket `bilgi_yok` yanlış.
  - **z02 İngilizce "Can foreign companies apply…" → `bilgi_yok`:** belgede yabancı şirket başvurusuna dair hüküm yok ("Yabancı" yalnızca mevzuat listesinde bir kanun adında geçiyor). Karar doğru, etiket routing setinden kalmış. Ek gözlem: İngilizce sorunun 1. parça puanı 0.774, konu dışı sorular düzeyinde; diller arası retrieval zayıf.
  - **q01 "Firma kabul şartları" → doğru ama eksik:** 10.1 üç parça (10.1-0 online başvuru, 10.1-1 komisyon kabulü, 10.1-2 findeks/borç belgesi); LLM'e yalnızca 10.1-2 gitti. LLM "şartlar şunlardır" diye tam liste gibi sundu. Kaynak ölçümü bunu yakalamıyor (bölüm doğru). Çözüm adayları: reranking (adım 8) veya aynı bölümün diğer parçalarını eklemek.
  - Etiketler düzeltildi (26.11): u02 → `cevap` + `sections: ["7.2.1"]`, z02 → `bilgi_yok`; eski etiket `note`'ta duruyor. Bu ilk çalıştırma 32 soruluk eski setle yapıldı ve JSON'u yok (kaydetme sonradan eklendi); 67 soruluk setle `--eval` yeniden çalıştırılmalı.
- **İkinci LLM sonucu (26.11, 67 soru, aynı ayarlar, `eval/results/cevaplar2.json`):**

  | Ölçüm | Sonuç |
  |---|---|
  | Tür doğruluğu (otomatik) | 66/67 (%99) |
  | Tür doğruluğu (elle inceleme sonrası) | 67/67: u06 etiket hatası |
  | Kaynak doğruluğu | 30/31 (q21 ✗) |
  | Retrieval: beklenen bölüm 1. sırada / ilk 5'te | 23/31 / 30/31 |
  | Uydurma | yok |
  | geçersiz / sohbet | 7/7 / 7/7 (s02'de "olabildigim" yazım hatası yine var) |
  | Gecikme (bekleme hariç) | ort 3.4 sn, medyan 2.7 sn, p90 6.7 sn, en fazla 11.7 sn (60 çağrı) |
  | Geçici API hatası | 503 ×18, 429 ×3 (Gemini yoğundu; toplam bekleme 132 sn) |

  - **u06 "ofiste sigara" → `cevap`:** belgede "sigara" kelimesi yok ama 7.1.6 ve 7.1.7 "Tütün Ürünleri… Kanunu" kısıtlamalarından söz ediyor; LLM doğru. Etiket kelime aranarak konmuştu → `cevap` + `sections: ["7.1.6", "7.1.7"]` yapıldı. Ders: etiket koyarken kelime değil konu aranmalı.
  - **z09 (tek mesajda iki soru) → yarısı yanlış:** 5 parçanın hepsi kuluçka ile ilgili, 5.4 gelmedi; LLM "yönetim kurulu sayısı belgede yok" dedi (belgede var: 7 kişi). Uydurma değil, ama kullanıcıya yanlış bilgi gidiyor ve otomatik ölçüm bunu ✓ sayıyor. Aday: multi-query (soruyu bölme), reranking.
  - **q21 "kurallara uymazsam ne olur" → eksik:** asıl cevap 17'de (3–30 gün süre, kurul, ihraç), 17/18 hiç getirilmedi; LLM 7.1.x'teki dağınık yaptırımlardan cevap kurup "diğer sonuçlar belirtilmemiş" dedi. Aday: reranking, query rewriting.
  - **Ortak sonuç:** LLM tarafı sağlam (uydurma yok, belge dışını reddediyor, İngilizce soru z08 doğru). Kalan hataların hepsi retrieval'da: doğru parça ilk 5'e girmiyor. Reranking (adım 8) için somut gerekçe.
- **Analiz ve rapor (`tests/report.py`, 26.11; önce `rag/analyze.py`):** cevap testi sonucu `eval/results/answer-<zaman>.json`'a kaydediyor (soru, beklenen, çıkan, cevap, kaynaklar, LLM'e giden parça id'leri ve puanları, gecikme, bekleme, tekrar denemeler, ayarlar, system prompt'un sha1'i). `python tests/report.py` en yeni sonucu (dosya adına değil içindeki `createdAt`'e göre) okuyup `eval/reports/<aynı ad>.md` raporunu yazıyor: özet (otomatik ve elle inceleme sonrası doğruluk, kaynak doğruluğu, uydurma şüphesi, fazla temkin, API hataları, gecikme ort/medyan/p90), tür başına, karışıklık tablosu, incelenen soruların ayrıntısı (cevap, kaynak, LLM'e giden parçalar, inceleme yorumu), retrieval sırası, gecikme dağılımı, tüm sonuçlar. `--compare <eski.json>` iki çalıştırmayı karşılaştırır (prompt değişikliği öncesi/sonrası için).
- **Elle inceleme (`eval/review.jsonl`):** otomatik ölçüm cevap metninin doğruluğunu ölçemediği için inceleme notları ayrı dosyada: `{id, when_type, type_ok?, label_issue?, quality?, comment}`. `when_type` notun yazıldığı sıradaki sonuç; yeni çalıştırmada tür farklıysa not uygulanmaz, rapor "yeniden incele" der. Şu an q01, q21 (eksik), z09 (yarısı yanlış) ve u06 (etiket hatası, `cevaplar2.json` için) notları var; u02 ve z02 notları etiketler düzeltilince kaldırıldı (gerekçe yukarıda ve `testset.jsonl` `note`'unda). Sonuç dosyası yeniden adlandırılabilir (ör. `cevaplar2.json`); `tests/report.py` en yeniyi içindeki `createdAt`'e göre bulur, belirli bir dosya için yol verilir. Ham otomatik sonuç raporda her zaman ayrı duruyor.
- **API'siz test:** LLM sahte cevaplarla değiştirilerek test → JSON → rapor zinciri denendi; çalışıyor (`tests/` taşımasından sonra tekrar denendi).
- **Sonra:** ödev için Streamlit/Gradio arayüzü `Assistant.answer()`'ı çağıracak.

### LLM ve API sınırı
- Gemini `gemini-3.5-flash-lite` (`project.json › llm`, temperature 0.1). `GEMINI_API_KEY` `.env`'de olmalı (yalnızca `answer.py` ve `tests/answer_test.py` için; `--dry-run` hariç).
- **API sınırı (Gemini ücretsiz plan):** **dakikada 15 istek** (proje + model başına; hata: `429 RESOURCE_EXHAUSTED`). Yoğun saatlerde `503 UNAVAILABLE` da görüldü. Soru başına tek çağrı olduğu için ücretsiz planla **dakikada ~15 soru**. `tests/answer_test.py` 67 soruda ~60 LLM çağrısı yapar, kotaya takılıp bekleyebilir. Günlük sınır ölçülmedi (Google AI Studio → Rate limits).

## Temel ilke: çekirdek + proje paketi
Sistem iki parçadan oluşur:

| Parça | İçerik | Yeni projede |
|---|---|---|
| **Çekirdek** (`rag/`, `src/`, `public/`) | Extraction, chunking, embedding, retrieval, LLM çağrısı, guardrail motoru, API, arayüz | **Değişmez** |
| **Proje paketi** (`projects/<proje-id>/`) | Belgeler, `project.json` ayarları, prompt'lar, mesaj metinleri, guardrail kuralları, test setleri, arayüz metinleri | Yeniden yazılır |

**Kurallar**
1. Çekirdek kodda belgeye özel hiçbir şey olmaz: dosya adı, sayfa numarası, başlık kalıbı, prompt, "Teknopark" kelimesi, model adı, eşik değeri. Bunların hepsi `project.json` veya proje klasöründen okunur.
2. Aktif proje tek bir değişkenle seçilir: `.env` içinde `PROJECT=yonerge` (veya `--project yonerge` argümanı).
3. Model adları ve parametreler `project.json`'dan okunur. Embedding için ayrı bir adaptör katmanı yok (24.11.2026 kararı): kod doğrudan `sentence-transformers` kullanır, model değişirse `project.json`'da tek satır değişir.
4. **Kabul kriteri:** Yeni bir proje eklerken `rag/`, `src/` veya `public/` altında kod değişikliği gerekiyorsa bu bir tasarım hatası sayılır ve çekirdek genelleştirilir.

## Mimari
- **Python (`rag/`)**: offline işler. Belge okuma, chunking, embedding, indeks oluşturma, retrieval denemeleri, değerlendirme. Çıktısı `index/<proje-id>/index.json` + `faiss.index`.
- **Node.js + Express (`src/`, Part 2)**: çalışan web uygulaması. Aktif projenin indeksini okur, soruyu embed eder, retrieval + LLM çağrısı yapar, arayüzü sunar.
- Uygulama çalışırken **tek sunucu** (Node) var; Python yalnızca indeks üretirken çalışır.
- İki taraf arasındaki sözleşmeler:
  - **`projects/<proje-id>/project.json`**: iki taraf da aynı ayar dosyasını okur. Ek bağımlılık gerekmesin diye YAML değil JSON.
  - **`index/<proje-id>/index.json` + `faiss.index`**: embedding modeli, önekler ve vektör deposu ayarları `index.json`'da, vektörler `faiss.index`'te. Node açılışta `project.json` ile `index.json`'daki modeli karşılaştırır; uyuşmazsa **başlamaz** ve "indeksi yeniden oluştur" hatası verir.
  - Node tarafında sorgu embedding'i `@huggingface/transformers` + `Xenova/multilingual-e5-base` (ONNX) ile yapılacak. Arama için `faiss-node` veya vektörleri okuyup dot product almak Part 2'de değerlendirilecek. Python ve Node aynı soru için aynı vektörü üretmeli; Part 2'de bir kez karşılaştırılacak.

## Klasör yapısı
```
tkpark-ragagent/
├── projects/
│   ├── _template/                 # yeni proje için kopyalanacak boş şablon
│   └── yonerge/                   # ilk proje paketi
│       ├── project.json           # tüm projeye özel ayarlar
│       ├── data/yonerge.pdf       # kaynak belge(ler)
│       ├── eval/retrieval.jsonl   # ✅ retrieval soru seti (adım 7)
│       ├── eval/testset.jsonl     # ✅ cevap test seti, 67 soru (adım 9)
│       ├── prompts/               # ✅ system.md (adım 9), messages.json
│       └── guardrails/rules.json  # ⬜ (Part 4)
├── rag/                           # Python çekirdek — projeden bağımsız
│   ├── config.py                  # PROJECT seç → project.json + .env oku, doğrula
│   ├── extract.py                 # 1 → index/<id>/pages.json
│   ├── loaders/                   # pdf.py (PyMuPDF) — ileride docx.py, html.py…
│   ├── chunk.py                   # 1–2 → index/<id>/chunks.json
│   ├── embed.py                   # 3–4 → index/<id>/index.json + faiss.index
│   ├── rewrite.py                 # 5 → query rewriting (kural listesi, queryRewrite)
│   ├── search.py                  # 6–7 → retrieval (Retriever; rewriting varsa iki arama + birleştirme)
│   └── answer.py                  # 5 (girdi kontrolü) + 9 → uçtan uca cevap + kaynaklar
├── tests/                         # ölçüm — chatbot için gerekli değil (README.md'de açıklama)
│   ├── retrieval_test.py          # arama doğru bölümü buluyor mu (Hit@K, MRR), LLM yok
│   ├── answer_test.py             # cevap test seti → eval/results/*.json, LLM var
│   └── report.py                  # sonuç JSON'u → eval/reports/*.md (mentor raporu)
├── src/                           # Node çekirdek (Part 2) — server.js, config.js, retrieval.js, llm/, guardrails/
├── public/                        # arayüz (Part 3) — başlık/metinler /api/config'ten gelir
├── index/                         # üretilen dosyalar (git'e girmez)
│   └── yonerge/{pages.json, chunks.json, index.json, faiss.index}
├── .env.example
└── requirements.txt
```

## `project.json` (yonerge örneği)
```json
{
  "id": "yonerge",
  "name": "Yıldız Teknopark Yönerge Asistanı",
  "language": "tr",

  "sources": [
    {
      "path": "data/yonerge.pdf",
      "type": "pdf",
      "title": "YTÜ Yıldız Teknopark Bölge İşletme Yönergesi",
      "skipPages": [1, 2, 3, 4]
    }
  ],

  "chunking": {
    "strategy": "heading",
    "headingPatterns": [
      "^\\d+\\.\\s+(?=[A-ZÇĞİÖŞÜ]{2})",
      "^\\d+\\.\\d+\\.(?=\\s|$|[A-ZÇĞİÖŞÜ])",
      "^\\d+\\.\\d+\\.\\d+\\.(?=\\s|$|[A-ZÇĞİÖŞÜ])",
      "^[a-zçğıöşü]\\.\\s+(?=[A-ZÇĞİÖŞÜ])"
    ],
    "bullet": "•",
    "maxTokens": 300,
    "overlap": 50,
    "fallback": { "strategy": "fixed", "maxTokens": 300, "overlap": 50 }
  },

  "embedding": {
    "model": "intfloat/multilingual-e5-base",
    "passagePrefix": "passage: ",
    "queryPrefix": "query: "
  },
  "vectorStore": { "type": "flat" },
  "llm":       { "provider": "gemini", "model": "gemini-3.5-flash-lite", "temperature": 0.1 },
  "input":     { "minChars": 3, "maxChars": 1000 },
  "retrieval": { "topK": 5, "minScore": 0.0 },
  "queryRewrite": {
    "enabled": true,
    "rules": [
      { "match": ["firma"], "replace": "Girişimci" },
      { "match": ["teknopark"], "replace": "Bölge" },
      { "match": ["uymaz", "ihlal", "ceza"], "replace": "aykırı faaliyet" }
    ]
  },

  "prompts": {
    "system": "prompts/system.md",
    "messages": "prompts/messages.json",
    "vars": { "organization": "YTÜ Yıldız Teknopark", "assistantName": "Yönerge Asistanı" }
  },

  "guardrails": "guardrails/rules.json",

  "ui": {
    "title": "Yönerge Asistanı",
    "welcome": "Teknopark bölge işletme yönergesi hakkında soru sorabilirsiniz.",
    "examples": ["Firma kabul şartları nelerdir?", "Ortak alanlar nasıl kullanılır?"]
  }
}
```
- `headingPatterns` üst seviyeden alta sıralıdır (1. eleman = 1. seviye); eşleşen kısım bölüm numarası, kalan metin başlıktır. Başlığı olmayan belgede `strategy: "fixed"` kullanılır; `heading` hiç başlık bulamazsa `fallback`'e düşülür.
- `maxTokens` / `overlap` token cinsinden, embedding modelinin tokenizer'ıyla sayılır (başlık yolu dahil, önek ve özel tokenlar hariç).
- `input.minChars` / `input.maxChars`: girdi kontrolünün sınırları (26.11'e kadar `routing` altındaydı; `routing.scope` routing ile birlikte kaldırıldı).
- `minScore`: 0.0 (adım 7 kararı). Konu dışı soruları 9. adımdaki cevap prompt'u yakalar.
- `queryRewrite` (27.11, isteğe bağlı; yoksa kapalı): `match` kelime başları (ek ve büyük/küçük harf kapsanır), eşleşen kelime `replace` ile değişir. Terimler projeye özel; çekirdekte kelime yok. Bkz. 5. adım.
- Soru seti yolu isteğe bağlı olarak `eval.retrieval` ile değiştirilebilir (varsayılan `eval/retrieval.jsonl`).

## `index.json` + `faiss.index` sözleşmesi
```json
{
  "schemaVersion": 2,
  "project": "yonerge",
  "createdAt": "2026-11-24T09:05:00Z",
  "embedding": { "model": "intfloat/multilingual-e5-base", "dimensions": 768, "normalized": true,
                 "passagePrefix": "passage: ", "queryPrefix": "query: " },
  "vectorStore": { "type": "flat", "library": "faiss", "index": "IndexFlatIP",
                   "metric": "inner_product", "file": "faiss.index", "count": 186 },
  "chunking": { "…": "chunks.json'daki ayarlar" },
  "chunks": [
    {
      "id": "yonerge-7.1.5-0",
      "text": "…",
      "tokens": 227,
      "metadata": { "source": "data/yonerge.pdf", "section": "7.1.5", "title": "…", "path": ["7. …", "7.1. …", "7.1.5. …"], "pages": [13, 14] }
    }
  ]
}
```
- Vektörler `index.json`'da değil, `faiss.index`'te. FAISS vektörü `i` → `chunks[i]`, yani `chunks` sırası değiştirilmemeli.
- `dimensions` modelin döndürdüğü gerçek boyuttan yazılır. `metadata` alanları kaynak türüne göre değişebilir; yalnızca `source` zorunlu.

## İlk proje paketi: `yonerge` — belge notları
- Dosya: `projects/yonerge/data/yonerge.pdf`. YTÜ Yıldız Teknopark Bölge İşletme Yönergesi; bir "yönerge", Bakanlık yönetmeliği değil.
- 41 PDF sayfası, ~18.000 kelime, Word'den üretilmiş, metin katmanı var → OCR gerekmiyor.
- Metinde onay/yürürlük tarihi veya sürüm yok. PDF metadata oluşturulma tarihi: 2025-01-28.
- Sayfalarda basılı sayfa numarası yok. İçindekiler'deki numaralar = PDF sayfası − 1. Uygulama yalnızca PDF sayfa sırasını kullanır.
- **Yapı:** numaralı başlıklar `1.` … `21.`, `7.1.`, `7.1.5.` (en fazla 3 seviye) + `7.2.2` altında `a.` / `b.`. Resmî "madde / fıkra / bent" (`MADDE 5 – (1) a)`) yapısı **yok**; metin kendi içinde "6.4. maddesinde" diye bu numaralara atıf yapıyor.
- İçerik çoğunlukla `•` maddeli kurallar ve paragraflar. Bölüm 3 "Tanım ve Kısaltmalar" bir `Terim: tanım` listesi.
- Belgede "teknopark" yerine çoğunlukla "Bölge", "firma" yerine "Girişimci" geçiyor (ileride query rewriting için önemli).

## Yol haritası
- **Part 1 — RAG çekirdeği (Python, terminal)**: yukarıdaki 9 adım + LLM cevabı ve değerlendirme
  - [x] 1 Metin hazırlığı + metadata
  - [x] 2 Chunking
  - [x] 3 Embedding
  - [x] 4 Vector DB
  - [x] 5 Query processing: ayrı routing kaldırıldı (26.11; LLM routing denemesi 32/32 idi), yönlendirme 9'da prompt ile; girdi kontrolü `answer.py`'de
  - [x] 6 Query embedding
  - [ ] 7 Retrieval (deney tamam, Hit@5 10/10; `minScore` 0.0; commit edildi; reranking'den önce test tekrarlanacak)
  - [x] 8 Reranking: denendi, kullanılmıyor (27.11; kazanç küçük, CPU'da çok yavaş)
  - [ ] 5+ Query rewriting (kural listesi yazıldı ve ölçüldü 27.11; birleştirme yöntemi karar bekliyor) / multi-query (sonra)
  - [ ] 9 Prompt oluşturma (sohbet / konu dışı / "bilgim yok" kuralları dahil) — yazıldı, LLM testi bekliyor
  - [ ] LLM cevabı + backend'de üretilen kaynaklar — yazıldı (`answer.py`), LLM testi bekliyor
  - [x] Cevap değerlendirme seti ve scripti — `testset.jsonl` (67) + `tests/answer_test.py` + `tests/report.py`; 66/67
  - [ ] Ödev için arayüz (Streamlit/Gradio, `Assistant.answer()` üzerinden)
- **Ara iş — Docker + veritabanında vector store (mentor, 26.11.2026):**
  - **✅ Engel çözüldü (26.11, aynı gün):** motor çalışıyor (`docker info` → 29.9.3, Docker Desktop). Aşağıdaki not kayıt için duruyor.
  - **Eski engel (26.11): Docker motoru çalışmıyordu.** Docker Desktop kurulu (Docker 29.9.3, Compose v5.7.0) ve açılıyor, ama motor başlamıyor (`docker info` → 500 / `dockerDesktopLinuxEngine` bulunamadı). Sebep: Windows'un **Sanal Makine Platformu (Virtual Machine Platform)** özelliği kapalı, bu yüzden WSL2 başlamıyor (`wsl --status` bunu söylüyor). BIOS sanallaştırması açık (`VirtualizationFirmwareEnabled: True`, AMD Ryzen 7 7730U), WSL dağıtımı yok. Açmak için yönetici yetkisi gerekiyor, kullanıcıda yok → IT / mentor bekleniyor.
  - **Çözüm (yönetici PowerShell'de):** `wsl --install --no-distribution` → bilgisayarı yeniden başlat → Docker Desktop'ı aç, "Engine running" bekle → `docker info` hata vermemeli → `docker run hello-world` "Hello from Docker!" yazmalı. IT'ye iletilecek cümle: "Docker Desktop için Virtual Machine Platform özelliğinin açılması ve WSL2'nin kurulması gerekiyor (`wsl --install --no-distribution`)."
  - **Kurulunca yapılacaklar (sırayla):**
  - [x] Motoru doğrula: `docker info`, `docker run hello-world` (27.11: "Hello from Docker!", image 9.49 kB)
  - [ ] Docker temelleri (image, container, volume, port; `docker ps`, `docker images`, `docker stop`, `docker rm`). 27.11'de görülen: image/container farkı, `pull` (ilk `run`'da otomatik), `ps` / `ps -a`, `Exited (0)`, `rm`, `--rm`, `--name`. Ders 2 (27.11, `nginx:1.27-alpine`): `-d`, `-p 8080:80`, `logs`, `exec`, `stop` / `start`, `rm -f`; container içindeki değişiklik `stop`/`start`'ta kaldı, `rm` + yeni container'da kayboldu (volume gerekçesi). Ders 3 (27.11): `docker volume create`, `-v <volume>:<klasör>`, `--env-file` (= dosyadan `-e`); ilk açılış kurulumu yalnızca volume boşken yapılır. MySQL 9.7.4 ile denendi, sonra silindi (container, volume, image)
  - [x] Veritabanı seçimi (27.11): **PostgreSQL 18 + pgvector 0.8.7**, image `pgvector/pgvector:0.8.7-pg18` (indirildi). MySQL'in mesafe fonksiyonu denenmeden bırakıldı. Gerekçe karar günlüğünde (27.11)
  - [x] Ayarlar `docker/db.env` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`; git'e girmez) ve `docker/db.env.example`
  - [x] pgvector container'ı (27.11): `docker run -d --name tkpark-db --env-file docker/db.env -p 5432:5432 -v tkpark-pg-data:/var/lib/postgresql pgvector/pgvector:0.8.7-pg18`. **Dikkat:** PG 18 image'ında veri klasörü `PGDATA=/var/lib/postgresql/18/docker`, volume `/var/lib/postgresql`'e bağlanır (eski `/var/lib/postgresql/data` değil; `docker image inspect` ile bakıldı). `CREATE EXTENSION vector` (0.8.7) açıldı. Oyuncak tablo `oyuncak` (`vector(3)`, 4 satır): soru `[1, 0.2, 0]` ile `<=>` sıralaması doğru, `1 - (a <=> b)` elle hesaplanan cosine ile aynı (0.9806); yanlış boyut reddediliyor (`expected 3 dimensions, not 2`). Container silinip aynı volume'le açılınca "Skipping initialization", tablo yerinde. `rm -f` PostgreSQL'i düzgün kapatmadığı için açılışta WAL kurtarması yaptı (veri kaybı yok); doğrusu `docker stop` → `docker rm`. Bağlanmak için: `docker exec -it tkpark-db psql -U tkpark -d tkpark`
  - [x] `docker-compose.yml` (27.11): yalnızca `db` servisi. `docker run`'a göre ekler: port `127.0.0.1:5432:5432` (yalnızca bu bilgisayar), `docker/initdb/01-vector.sql` bind mount (`:ro`, yalnızca volume boşken çalışır, `CREATE EXTENSION IF NOT EXISTS vector`), `pg_isready` healthcheck (`(healthy)`), `restart: unless-stopped`, volume `name: tkpark-pg-data` (mevcut volume; ilk `up`'ta "not created by Docker Compose" uyarısı zararsız, `external: true` bilerek konmadı çünkü yeni bilgisayarda volume'ü oluşturmaz). Compose `tkpark-rag-1_default` ağını kendisi açıyor; backend eklenince DB'ye `db:5432` ile ulaşacak. Komutlar: `docker compose up -d`, `ps`, `logs db`, `down` (`down -v` volume'ü siler)
  - [x] DBeaver (27.11, kullanıcı kurdu): PostgreSQL, host **`127.0.0.1`** (`localhost` değil, aşağıdaki IPv6 notu), port 5432, DB/kullanıcı `tkpark`, şifre `docker/db.env`'den. Gerçek chunk tablosunda yalnızca görüntüleme (tabloyu `embed.py` doldurur)
  - [x] Gerçek tablolar (27.11): `rag/schema.sql` (`rag_indexes`, `rag_chunks`, boyutsuz `vector`), `oyuncak` silindi
  - [x] `embed.py` vektörleri DB'ye yazıyor, `search.py` DB'den sorguluyor (27.11); `project.json › vectorStore.type` = `"pgvector"` (yedek `"flat"`). Sonuçlar: `embed.py` 186 chunk 5.7 sn'de yazıldı, DB araması kesin aramayla 1.000 uyumlu (puan farkı ≤ 6e-7); `tests/retrieval_test.py` pgvector'le **Hit@5 10/10, MRR 0.817** (FAISS'le aynı); `tests/store_compare_test.py` 63 soruda ilk 20 sonuç 63/63 aynı, tam sıralama 62/63 (1 soruda eşit puanlı iki chunk yer değiştirmiş), puan farkı ≤ 3e-7; `answer.py --dry-run` DB'den parça getiriyor; Docker kapalıyken anlaşılır hata (çıkış 1). **Uçtan uca test pgvector'le (27.11, `eval/results/answer-20261127-153718.json`, rapor `eval/reports/answer-20261127-153718.md`):** tür 67/67, kaynak 31/32 (q21, retrieval kaynaklı, önceki gibi), uydurma yok; 67 sorunun hepsinde LLM'e giden 5 parça 26.11 FAISS çalıştırmasıyla birebir aynı. Gecikme ort 963 ms (önceki 3440 ms; fark Gemini'nin o anki yoğunluğundan, depodan değil). Karşılaştırma raporu `eval/reports/store-compare-20261127-153242.md`
  - [ ] Sonra compose'a backend ve frontend eklenecek (Part 2–3 ile birlikte).
- **Part 2 — Web API (Node/Express):** `POST /api/chat`, `GET /api/config` (arayüz metinleri); aktif projenin indeksini okur; açılışta embedding uyumu kontrolü
- **Part 3 — Arayüz:** HTML/CSS/vanilla JS; başlık, karşılama ve örnek sorular `/api/config`'ten
- **Part 4 — Guardrails:** genel kural motoru (`src/guardrails/`) + projeye özel kurallar (`rules.json`) + saldırı/sınır test seti. Odak: prompt injection, saldırı ve sınır durumları, istenirse cevabın kaynaklara dayanıp dayanmadığı. Konu dışı kararını 9. adımdaki cevap prompt'u verir; ayrı bir konu dışı kontrolü yalnızca ölçümde prompt'un kaçırdığı görülürse eklenir (her ek ret katmanı geçerli soruları yanlışlıkla reddetme riskini artırır).
- **Part 5 — Taşınabilirlik testi:** farklı türde ikinci bir belgeyle (ör. başlıksız bir SSS) yeni proje paketi oluştur, **kod değiştirmeden** uçtan uca çalıştır
- **İleride — Agentic RAG (fikir, 26.11.2026 mentor görüşmesinden):** LLM'e bir arama aracı (tool) verilir; ne zaman ve hangi sorguyla arama yapacağına LLM karar verir. Gerekirse birden fazla arama yapabilir, sohbet mesajında hiç arama yapmayabilir. Temel RAG akışı ve değerlendirme bittikten sonra ele alınacak.
- **Part 6 — Teslim:** README, mimari notu, "yeni proje nasıl eklenir" rehberi, 3 dk demo akışı (demoda proje değiştirmeyi de göster)

## Teknoloji kararları
Model ve parametreler `project.json`'dan seçildiği için değiştirmek kod değişikliği gerektirmez.

| Bileşen | Seçim |
|---|---|
| Python | 3.11+ (test: 3.13), sanal ortam `.venv` |
| PDF extraction | PyMuPDF (`pymupdf`) — `rag/loaders/pdf.py` |
| Chunking | Kendi başlık tespiti + LangChain `RecursiveCharacterTextSplitter` (`langchain-text-splitters`) |
| Embedding | Yerel `intfloat/multilingual-e5-base`, 768 boyut (`sentence-transformers`) |
| Vector store | **PostgreSQL 18 + pgvector 0.8.7** (Docker, `docker-compose.yml`; Python `psycopg` 3 + `pgvector`), kesin arama, `vectorStore.type: "pgvector"` (27.11'den beri varsayılan). Yedek: FAISS `IndexFlatIP` (`faiss-cpu`), `"flat"`; metin/metadata `index.json`'da. İkisi aynı sonucu veriyor (`tests/store_compare_test.py`). Büyürse pgvector'de HNSW indeksi |
| Reranker | Yok. `BAAI/bge-reranker-v2-m3` ve `Alibaba-NLP/gte-multilingual-reranker-base` denendi (27.11), CPU'da çok yavaş, kazanç küçük |
| LLM | Gemini `gemini-3.5-flash-lite` (Python `google-genai` 3.6, Node `@google/genai`); cevap ve yönlendirme (adım 9, soru başına tek çağrı). Ücretsiz plan: dakikada 15 istek |
| Proje ayarları | `projects/<id>/project.json` (Python ve Node ortak) |
| Web (Part 2–3) | Node.js 22+, Express 5, HTML/CSS/vanilla JS |

Not: FAISS tek dosyalık yerel bir indeks; pgvector ise Python, ileride Node backend ve DBeaver'ın aynı anda okuyabildiği bir sunucu. Node tarafında depo değişikliği yalnızca `retrieval.js`'i etkiler.

## Dosyalar
- `.env.example` — ortam değişkenleri şablonu (`PORT`, `PROJECT`, `GEMINI_API_KEY`); `.env` git'e girmez.
- `projects/yonerge/project.json` — ilk proje paketi ayarları; `projects/_template/` — yeni proje şablonu.
- `projects/yonerge/eval/retrieval.jsonl` — retrieval soru seti. Her satır `{id, question, expected: [bölüm], difficulty, note?}`. `expected` boşsa soru cevapsız/konu dışıdır ve `difficulty` etiketine göre gruplanır.
- `rag/config.py` — `--project` / `PROJECT` / `.env` ile proje seçer, `project.json`'ı okur ve doğrular. `project.get("a.b")` eksik alanda açık hata verir.
- `rag/loaders/` — `get_loader(type)` kaydı; `pdf.py` (PyMuPDF, `skipPages` uygular, PDF tarihini ISO'ya çevirir).
- `rag/extract.py` — tüm `sources` → `index/<id>/pages.json` (`pages[]` = `{source, page, text}`; `page` = PDF sayfa sırası).
- `rag/chunk.py` — `pages.json` → `index/<id>/chunks.json` (`chunks[]` = `{id, text, tokens, metadata}`; `id` = `<proje>-<bölüm>-<sıra>`). Sınırı aşan chunk varsa hata koduyla çıkar.
- `rag/embed.py` — `chunks.json` → embedding → `vectorStore.type`'a göre: `"pgvector"` → `rag_indexes` + `rag_chunks` (tek transaction, yazdıktan sonra 186 kesin arama kontrolü; hata olursa geri alınır, eski indeks kalır) ya da `"flat"` → `faiss.index` + `index.json`. Kontroller başarısızsa çıkış kodu 2 ve hiçbir şey yazılmaz; `chunks.json` eskiyse çıkış kodu 1. İsteğe bağlı `embedding.batchSize` (varsayılan 32).
- `rag/schema.sql` — pgvector tabloları (`rag_indexes`: proje başına model/boyut/ayarlar; `rag_chunks`: metin + `metadata` jsonb + `embedding vector` + `position`). `IF NOT EXISTS`, `embed.py` her çalışmada uygular.
- `rag/pgstore.py` — veritabanı işleri: `connect`, `write_index` (yaz + doğrula), `load_index`, `search` (`ORDER BY embedding <=> q`, puan `1 - mesafe`). Bağlantı bilgisi `config.db_settings()`.
- `rag/config.py › db_settings()` — `.env › DATABASE_URL` varsa onu, yoksa `docker/db.env`'deki `POSTGRES_*` değerlerini kullanır (sunucu `DB_HOST`/`DB_PORT`, varsayılan `127.0.0.1:5432`). Şifre tek yerde (`db.env`) durur. **`localhost` kullanılmaz:** Windows'ta önce IPv6'ya (`::1`) gidiyor, compose portu yalnızca `127.0.0.1`'de açtığı için bağlantı zaman aşımına kadar bekliyor (ölçüm: `localhost` 10 sn, `127.0.0.1` 27 ms; depoyu açma 5.3 sn → 0.2 sn).
- `rag/rewrite.py` — `QueryRewriter`: `project.json › queryRewrite.rules` ile soruyu belgenin diline yaklaştırır; kural uymazsa `None` (27.11).
- `rag/search.py` — `Retriever` ve tek soru araması (`"soru"`, `--top N`, `--no-rewrite`). `search_dense` yalnızca embedding araması; `search` query rewriting açıksa iki aramayı birleştirir (şu an `rrf_merge`, karar bekliyor), `last_rewrites` son aramada üretilen soruları tutar. İçinde `FaissStore` ve `PgStore`; `vectorStore.type` hangisinin kullanılacağını seçer, dışarıya verilenler (`search`, `chunks`, `section`, `title`) aynı. Açılışta model adı ve vektör boyutu depodakiyle karşılaştırılır.
- `tests/retrieval_test.py` — retrieval soru seti (`--top N`, `--no-rewrite`; yeniden yazılan soruyu da yazdırır). Rapor: Hit@1/3/5, MRR, ilk K'ya giremeyenler, grup bazında puan aralıkları ve `minScore` ile ayrım yapılıp yapılamadığı.
- `tests/store_compare_test.py` — FAISS ve pgvector aynı sonucu veriyor mu (iki depo da önceden üretilmiş olmalı): her depoda Hit@K/MRR, ilk 1/5/20 aynı mı, 186 chunk'ın tam sıralaması, puan farkı, hız (açılış, soru başına arama). Açıklamalı Markdown rapor `eval/reports/store-compare-<zaman>.md` (`--no-save` ile yazmaz).
- `docker-compose.yml`, `docker/initdb/01-vector.sql`, `docker/db.env(.example)` — veritabanı container'ı (bkz. "Ara iş").
- `projects/yonerge/eval/testset.jsonl` — cevap test seti. Her satır `{id, question, expect, sections?, note?}`; `expect` ∈ `geçersiz` / `cevap` / `bilgi_yok` / `sohbet`; `sections` yalnızca kaynak kontrolü yapılacak `cevap` sorularında. Yol `eval.testset` ile değiştirilebilir.
- `projects/yonerge/prompts/system.md` — cevap prompt'u (adım 9; `{organization}`, `{assistantName}`).
- `projects/yonerge/prompts/messages.json` — `geçersiz`, `bilgi_yok`, `hata` sabit cevapları (`{organization}` gibi değişkenler doldurulur).
- `rag/answer.py` — uçtan uca cevap (`Assistant`). Tek soru, `--dry-run`.
- `tests/answer_test.py` — cevap test seti; `--only`, `--no-save`, `--no-rewrite` (sonuçta her sorunun `rewrite` alanı). Ekran özeti: tür doğruluğu, karışıklık tablosu, kaynak doğruluğu, uydurma riski, fazla temkin, gecikme. Sonuç `eval/results/answer-<zaman>.json` (yol `eval.resultsDir`).
- `tests/report.py` — sonuç JSON'undan Markdown rapor (`eval/reports/`, yol `eval.reportsDir`). `--compare <eski.json>` (27.11'den beri retrieval satırları da: beklenen bölüm 1. sırada / LLM'e giden parçalarda, query rewriting açık mı), `--stdout`. Elle inceleme notlarını `eval/review.jsonl`'dan (yol `eval.review`) okur.
- `projects/yonerge/eval/review.jsonl` — elle inceleme notları (bkz. 9. adım).
- Eski routing (`rag/route.py`, `prompts/routing.md`, `eval/routing.jsonl`) 26.11'de silindi; `7fafda0` commit'inde duruyor.
- `requirements.txt` — `pymupdf`, `sentence-transformers` (PyTorch ile gelir), `langchain-text-splitters`, `faiss-cpu`, `google-genai`, `psycopg[binary]`, `pgvector`. Model (~1.1 GB) ilk kullanımda Hugging Face'ten bir kez indirilir. `.venv` `uv` ile kurulu (içinde `pip` yok): `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.
- `package.json` — Node tarafı (Part 2'de doldurulacak).

## Nasıl çalıştırılır
```bash
cp .env.example .env               # PROJECT=yonerge ve GEMINI_API_KEY doldur (anahtar answer.py ve tests/answer_test.py için)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # bu bilgisayarda: uv pip install --python .venv\Scripts\python.exe -r requirements.txt
cp docker/db.env.example docker/db.env   # şifreyi değiştir (yalnızca ilk kez)
docker compose up -d               # vektör veritabanı (proje klasöründen çalıştır); "docker compose ps" → (healthy)
python rag/extract.py              # 1   → pages.json  (veya --project yonerge)
python rag/chunk.py                # 1–2 → chunks.json
python rag/embed.py                # 3–4 → veritabanı (pgvector) ya da index.json + faiss.index (flat)
python tests/store_compare_test.py # iki depo da üretildiyse: FAISS = pgvector mi
python rag/search.py "Ortak alanlar nasıl kullanılır?"   # 6–7 tek soru (--no-rewrite: query rewriting kapalı)
python tests/retrieval_test.py    # 6–7 soru seti deneyi (Hit@K, MRR)
python rag/answer.py "Firma kabul şartları nelerdir?"   # 9 cevap + kaynaklar
python rag/answer.py "Merhaba" --dry-run                 # 9 prompt'u göster (anahtar gerekmez)
python tests/answer_test.py       # 9 cevap test seti (67 soru ~5–8 dk, kota beklemesi olabilir) → eval/results/*.json
python tests/report.py            # en yeni sonuçtan rapor → eval/reports/*.md
```
Beklenen: `extract.py` → 41 sayfa, 4 atlanan, 37 alınan. `chunk.py` → 96 bölüm, 186 chunk. `embed.py` → `Doğrulama: tamam`. `tests/retrieval_test.py` → Hit@5 10/10, MRR 0.817 (iki depoda da). Docker kapalıyken `"pgvector"` ile "Veritabanına bağlanılamadı … docker compose up -d" hatası çıkar; Docker'sız çalışmak için `project.json › vectorStore.type` = `"flat"`.

## Yeni proje ekleme (kontrol listesi)
1. `projects/_template/` → `projects/<yeni-id>/` olarak kopyala.
2. Belgeleri `data/` altına koy, `project.json` → `sources` listesini doldur.
3. Belgenin başlık yapısına göre `chunking` ayarlarını yaz (başlık yoksa `fixed`).
4. `prompts/system.md`, `messages.json` ve `ui` metinlerini yeni alana göre yaz. (Belge kapsamını ayrıca tanımlamak gerekmez; yönlendirmeyi system prompt yapar.)
5. `.env` → `PROJECT=<yeni-id>`.
6. `python rag/extract.py && python rag/chunk.py && python rag/embed.py`
7. `eval/retrieval.jsonl` soru setini yaz, `python tests/retrieval_test.py` ile `topK`/`minScore` ayarla. 
8. `eval/testset.jsonl` hazırla (cevap / bilgi_yok / sohbet / geçersiz örnekleri) ve `python tests/answer_test.py` çalıştır, `python tests/report.py` ile rapor al.
9. `npm start` → arayüz yeni projenin başlık ve metinleriyle açılır.

## Mevcut sınırlamalar
- Paragraf sınırı sezgisel: satır `. : ; ! ?` ile bitiyorsa ya da boş satır, `•` veya `Terim:` ile başlıyorsa yeni blok. Yanlış birleşme yalnızca bölme noktasını etkiler, metin kaybolmaz.
- e5 puanları dar bir aralıkta (cevaplı 0.80–0.86, ilgisiz 0.76–0.78). Bu yüzden sabit bir `minScore` kırılgan.
- Soru setleri küçük (retrieval 16, cevap 67 soru; her bölümde çoğunlukla tek soru); sonuçlar yön gösterir, kesin değildir.
- Gemini ücretsiz planı dakikada 15 istekle sınırlı. Soru başına tek çağrıyla dakikada ~15 soru yanıtlanabilir.
- Ayrı routing olmadığı için konu dışı ve sohbet mesajları da retrieval'a giriyor (~15 ms, ihmal edilebilir) ve LLM'e chunk'larla gidiyor; bu mesajlarda prompt token'ı boşa harcanıyor.

## Repo durumu (24.11.2026)
- Remote: `origin` → `github.com/senasagdc/tkpark-rag`. Çalışma dalı `main`.
- `feat/1.5-retrieval-test` dalı (19.11) eski, adaptörlü yapıya göre yazılmıştı. Soru seti oradan alındı, `search.py` yeni yapıya göre baştan yazıldı. Dal, yeni sürüm `main`'e girdikten sonra silinecek (karar bekliyor).
- `.gitignore`: `.env`, `index/`, `.venv/`, `__pycache__/`, `node_modules/`, `.DS_Store`. API anahtarı hiçbir dosyada yok.

## Karar günlüğü
**16.11.2026 — Mimari:** offline işler Python'da (`rag/`), çalışan uygulama Node/Express'te (`src/`). Aralarındaki sözleşme `project.json` + indeks dosyaları.

**17.11.2026 — Genelleştirme:** sistem yönergeye özel olmayacak. Kod genel, içerik proje klasöründe (`projects/<id>/`). Eski JS denemesi (`src/src/src/`, pdfjs) ve kullanılmayan `.vscode/` kaldırıldı.

**17.11.2026 — Chunking:** önce başlık, sonra `RecursiveCharacterTextSplitter`; boyut karakter yerine token (`maxTokens` 300, `overlap` 50). PDF'teki farklı başlık biçimlerine göre `headingPatterns` düzeltildi.

**17.11.2026 — İlk embedding:** yerel `multilingual-e5-small` (384 boyut) + `rag/providers/` adaptörü; vektörler `index.json` içinde. `embed.py`'ye eski `chunks.json` kontrolü eklendi. İlk denemede "Firma kabul şartları" için beklenen 10.1 bölümü ilk 3'te çıkmadı.

**24.11.2026 — Adaptör kaldırıldı, `e5-base`'e geçildi:** `rag/providers/` silindi; `embed.py` doğrudan `SentenceTransformer` kullanıyor, önekler `project.json`'da. Model `multilingual-e5-base` (768 boyut) oldu. Tokenizer aynı olduğu için 186 chunk birebir aynı kaldı. 10.1 bölümü ilk 3'e girdi.

**24.11.2026 — HNSW denendi, FAISS flat seçildi:**

| (Apple M2, 186 vektör, 20 soru) | HNSW (`hnswlib`, M=16, efC=200, efSearch=50) | FAISS `IndexFlatIP` |
|---|---|---|
| Recall@1/5/10 | 1.0 (efSearch=10'da @5 0.94) | 1.0 (tanımı gereği) |
| Latency p50 (tek soru, 1 thread) | 208 µs | **22 µs** |
| QPS (tek tek, 1 thread) | ~4.800 | **~44.700** |
| Dosya | 0.60 MB | 0.57 MB |
| Build | ~55 ms | ~0.02 ms |
| Ayar | M, efConstruction, efSearch | yok |

Bu boyutta kesin arama daha hızlı ve ayarsız. Ölçüm sırasında `hnswlib`'in çok thread'li eklemede seed'e rağmen her kurulumda farklı graf ürettiği görüldü; FAISS flat deterministik.

**24.11.2026 — Retrieval testi (adım 6–7):** `search.py` yeni yapıya göre baştan yazıldı; soru seti `feat/1.5-retrieval-test` dalından aynen alındı. İlk sonuç Hit@5 9/10 oldu (q10 21. sırada). 16.3 bölümünün de q10'u cevapladığı görülünce beklenen bölümlere eklendi → Hit@5 10/10, MRR 0.817. Proje 9 adımlık RAG akışına göre yeniden düzenlendi.

**24.11.2026 — Query processing: önce routing, rewriting ve multi-query sonra:** 5. adım şimdilik yalnızca query routing. Rotalar `geçersiz` (kural), `sohbet`, `konu_dışı` ve `belge` (LLM, `routing.scope` cümlesiyle). Embedding ile routing seçilmedi, çünkü hazır örnek cümlelere bağlı ve garip sorularda zayıf. Retrieval puanıyla eşik de seçilmedi, çünkü boşluk 0.02. Buna bağlı olarak `minScore` 0.0 kaldı (A seçeneği). Konu dışı kararını routing verir; Part 4 guardrail'i saldırı ve sınır durumlarına odaklanır. Query rewriting (eş anlamlı listesi dahil) ve multi-query, reranking'den sonra Hit@1/MRR ölçümüne göre değerlendirilecek.

**24.11.2026 — Adım 5 (query routing) tamamlandı:** `rag/route.py`. `geçersiz` kuralla, `belge` / `sohbet` / `konu_dışı` tek bir Gemini çağrısıyla (JSON şeması, enum) ayrılıyor; `sohbet` cevabı aynı çağrıda yazılıyor. LLM hata verirse soru `belge` sayılıyor (reddedilmiyor). Ücretsiz plan kotası (dakikada 15 istek) ilk eval'de 11 soruyu hataya düşürdü; 429/503 için tekrar deneme eklendi. Test seti 32 soru, sonuç 32/32 (u01 yemekhane etiketi `belge` → `konu_dışı` yapıldıktan sonra; prompt bu soruya göre ayarlanmadı). Ortalama gecikme ~870 ms.

**26.11.2026 — Ayrı routing kaldırıldı, yönlendirme cevap prompt'una taşındı (mentor önerisi):** Routing, belgenin kapsamını `routing.scope` diye tek cümleyle anlatmaya dayanıyordu; çok belgede bu cümle ya eksik kalır (geçerli sorular reddedilir) ya da sürekli elle güncellenir, yani ölçeklenmez. Yeni yaklaşımda her geçerli soru retrieval'a girer; sohbet, konu dışı ve "bilgim yok" davranışı 9. adımdaki `system.md` kurallarıyla, LLM'in kendisine verilen chunk'lara bakmasıyla belirlenir. Kazanç: soru başına tek LLM çağrısı (ücretsiz planla dakikada ~7 yerine ~15 soru), ~0.9 sn daha hızlı, bakımı gereken kapsam cümlesi ve rota listesi yok. Bedel: konu dışı mesajlar da retrieval'a ve LLM'e chunk'larla gidiyor. Girdi kontrolü (uzunluk, harfsiz mesaj) kural olarak kalıyor. `route.py` ve `routing.md` girdi kontrolü taşınana kadar referans; `routing.jsonl` 9. adımda test seti olacak. Mentorun ikinci fikri (LLM'e arama aracı verip ne zaman arayacağına onun karar vermesi, agentic RAG) yol haritasına "ileride" olarak eklendi.

**26.11.2026 — Adım 9 ve uçtan uca cevap yazıldı (`rag/answer.py`):** girdi kontrolü `route.py`'den taşındı (`project.json › input`); eski routing dosyaları ve `routing.scope` silindi. LLM tek çağrıda JSON şemasıyla `{type: cevap | bilgi_yok | sohbet, answer, sources}` döndürüyor. `bilgi_yok`'ta LLM'in metni değil `messages.json`'daki sabit metin gösteriliyor (tutarlı ret). Kaynaklar LLM'in verdiği parça numaralarından backend'de üretiliyor, LLM bölüm/sayfa yazmıyor. Konu dışı ve cevapsız sorular aynı `bilgi_yok` türünde birleşti; kullanıcı için fark küçük. Test seti `routing.jsonl`'dan `testset.jsonl`'a dönüştürüldü (u02, u03, z05 artık `bilgi_yok` bekleniyor). Bu bilgisayarda `GEMINI_API_KEY` olmadığı için yalnızca LLM'siz kısım test edildi.

**26.11.2026 — İlk LLM eval'i, etiket düzeltmesi ve test setinin genişletilmesi:** 32 soruluk ilk çalıştırma 30/32 verdi; iki "hata" belgeye karşı kontrol edilince etiket hatası çıktı. u02 (metrekare fiyatı) belgede kısmen cevaplanıyor (7.2.1, bedelleri Yönetim Kurulu belirler), yani `bilgi_yok` değil kısmi `cevap`. z02 (yabancı şirketler) etiketi routing setinden kalmıştı: routing'deki `belge` "konu belgeyle ilgili" demekti, `cevap` ise "cevap belgede var" demek; dönüştürmede bu fark kontrol edilmemişti. Etiketler sonuçlar görüldükten sonra düzeltildi, bu yüzden gerekçe her satırın `note`'unda ve burada yazılı (prompt bu sorulara göre değiştirilmedi). Ayrıca test seti belgenin 21 ana bölümünün yalnızca 6'sına bakıyordu (cevaplı 10 sorunun 5'i bölüm 7'den); her bölüme bir soru eklenerek ve diğer türler artırılarak 67 soruya çıkarıldı. Kural: etiket belgeye bakılarak konur, ilgili hüküm varsa kısmi `cevap` sayılır.

**26.11.2026 — İkinci eval (67 soru) ve u06 etiketi:** 66/67; tek "hata" u06 (ofiste sigara) yine etiket hatası çıktı: belgede "sigara" aranıp bulunamadığı için `bilgi_yok` konmuştu, oysa 7.1.6/7.1.7 tütün ürünleri kısıtlamasından söz ediyor. `cevap` yapıldı. Kalan sorunlar (q01, q21, z09) LLM'den değil retrieval'dan: doğru parça LLM'e gitmiyor. Sıradaki iyileştirme adayı reranking; çok parçalı sorular (z09) için multi-query.

**26.11.2026 — Test kodu `rag/`'dan `tests/`'e ayrıldı:** `search.py --eval` ve `answer.py --eval` ana dosyaları kalabalıklaştırıyordu (yarısına yakını ölçüm koduydu) ve neyin chatbot, neyin ölçüm olduğu karışıyordu. Kural: chatbot'un çalışması için gerekli olmayan kod `rag/`'da durmaz. `tests/retrieval_test.py`, `tests/answer_test.py`, `tests/report.py` (eski `rag/analyze.py`) ve Türkçe açıklama `tests/README.md`. Ölçüm verileri yerinde (`projects/<id>/eval/`). Klasöre `eval/` değil `tests/` dendi, çünkü `projects/<id>/eval/` zaten var. `report.py` en yeni sonucu artık dosya adına değil içindeki `createdAt`'e göre buluyor. API'siz kontrol: retrieval testi aynı sonuç (Hit@5 10/10, MRR 0.817), `--dry-run` çalışıyor, sahte LLM'le test → rapor zinciri çalışıyor.

**27.11.2026 — Vector DB: MySQL yerine PostgreSQL + pgvector:** mentor "önce MySQL, vektör araması yoksa başka DB" demişti. MySQL 9.7.4 (LTS) container'ı açıldı ama mesafe fonksiyonu denenmeden bırakıldı; yani "MySQL'de yok" sonucu ölçülmedi. Gerekçe: Community sürümünde vektör mesafe fonksiyonu belirsizdi (`VECTOR` tipi var, `DISTANCE` HeatWave'e özel biliniyordu), pgvector'de cosine mesafesi (`<=>`) ve ileride gerekirse HNSW indeksi kesin olarak var, Python desteği (`psycopg`, `pgvector`) ve RAG örnekleri yaygın. Image `pgvector/pgvector:0.8.7-pg18`: pgvector'ün en yeni sürümü, PostgreSQL 19 yerine bir yıllık 18 (kararlılık). Resmî `postgres` image'ında pgvector olmadığı için (Dockerfile gerekirdi) pgvector'ün kendi image'ı seçildi. DB ayarları `.env`'den ayrı `docker/db.env`'de, çünkü `.env`'deki Gemini anahtarı container'a girmemeli.

**27.11.2026 — Vektör deposu pgvector'e taşındı (aşama 2–5):** iki tablo: `rag_indexes` (proje başına, `index.json` üst kısmı) ve `rag_chunks` (chunk başına; metin, `metadata` jsonb, `embedding`, `position`). Tek ortak tablo + `project` sütunu, çünkü yeni proje paketi kod değişikliği olmadan aynı tablolara girmeli. `embedding` boyutsuz `vector` (A seçeneği): farklı modelli projeler aynı tabloda durabilir; boyut kontrolünü `embed.py`/`search.py` `rag_indexes.dimensions` ile yapar (bedeli: DB yanlış boyutu kendisi reddetmez; HNSW gerekirse ifade indeksi gerekir; 186 chunk'ta gerek yok). Metadata sütunlara bölünmedi (jsonb), çünkü kaynak türüne göre değişebilir. `position` FAISS'in "vektör i = chunks[i]" sözleşmesini korur; böylece `Retriever`'ın dışarıya verdikleri aynı kaldı ve `answer.py` ile `tests/` değişmedi. `embed.py` tek transaction'da siler-yazar-doğrular (yarım indeks kalmaz). Bağlantı şifresi `docker/db.env`'den okunuyor (`DATABASE_URL` ile ezilebilir); `.env`'e kopyalanmadı. FAISS silinmedi: karşılaştırma (`tests/store_compare_test.py`) ve Docker'sız yedek (`"flat"`). Sonuç FAISS'le aynı: Hit@5 10/10, MRR 0.817.

**27.11.2026 — Reranking denendi, çıkarıldı:** dense ilk 50 aday cross-encoder ile yeniden sıralandı (`project.json › rerank`, kod `rag/rerank.py`). İki çok dilli model denendi: `BAAI/bge-reranker-v2-m3` (568M) MRR 0.840, Hit@1 8/10, Hit@5 9/10 (q01 3. → 15.), soru başına ~32 sn; `Alibaba-NLP/gte-multilingual-reranker-base` (306M) MRR 0.850, Hit@1 8/10, Hit@5 10/10, soru başına ~98 sn (küçük olmasına rağmen yavaş, sebebi araştırılmadı). GPU kullanılamıyor; aday sayısını düşürmek q01'e yaramaz (doğru parçalar 28–33. sırada). Kazanç (10 soruda +1 Hit@1) bu süreye değmedi; kalan hatalar (q01, q21, z09) sıralamadan değil kelime uyuşmazlığından ve çok parçalı sorudan geliyor. Kullanıcı kararıyla reranker kaldırıldı, kod commit'lenmeden geri alındı. Model seçimi önce kısıtlar (Türkçe, lisans, boyut, CPU süresi) konuşulmadan yapılmıştı; ders: seçimden önce kısıtları belirle. Yan bulgu: gte konu dışı soruları puanla net ayırıyor (boşluk 0.31; cosine'de 0.02). Sırada query rewriting.

**27.11.2026 — Query rewriting: kural listesi, birleştirme yöntemi karar bekliyor:** LLM ile yeniden yazma yerine kural listesi seçildi (kullanıcı): ücretsiz, anında, deterministik; İngilizce ve çok parçalı sorular kapsam dışı. Kurallar belgenin kendi terimlerinden (firma → Girişimci, teknopark → Bölge, uymaz/ihlal/ceza → aykırı faaliyet); `şirket` "Yönetici Şirket" ile karışacağı için konmadı. Kod `rag/rewrite.py`, ayar `project.json › queryRewrite`, çekirdekte kelime yok. İlk uygulama orijinal + yeni soruyu RRF ile birleştiriyor; ölçümde en kötü yöntem çıktı (q01 3. → 6., testset Hit@5 31 → 30). "Yalnızca yeni soru" en iyi (testset MRR 0.808 → 0.825, q21 9. → 2.) ama q24'ü bozuyor (2. → 7.). Kazanç küçük ve kurallar başarısız sorular bilinerek seçildiği için iyimser. Kullanıcı kararı sonraya bıraktı; kodda RRF duruyor, LLM testi yapılmadı.
