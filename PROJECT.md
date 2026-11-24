# PROJECT.md — Yeniden Kullanılabilir RAG Chatbot (ilk proje: Teknopark Yönergesi)

## Şu an neredeyiz (sonraki oturum için)
> **Claude'a not:** bir sonraki oturumun başında, işe girişmeden önce bu bölümü kullanıcıya kısaca (birkaç cümleyle) anlat: ne bitti, sırada ne var, bekleyen kararlar neler. Sonra bu bölümü güncel tut.

- **Son biten (24.11.2026):** adım 5, query routing. `rag/route.py` her soruyu `geçersiz` / `sohbet` / `konu_dışı` / `belge` rotasına ayırıyor. Test setinde 32/32.
- **Sırada:** adım 8, reranking (cross-encoder, `BAAI/bge-reranker-v2-m3` adayı, aynı `retrieval.jsonl` ile Hit@1/MRR karşılaştırması). Ardından adım 9, prompt.
- **Bekleyenler:**
  - 7. adımın retrieval testi, routing tamamlandığı için yeniden çalıştırılacak (`e56b871` commit notu).
  - `feat/1.5-retrieval-test` dalının silinmesi karar bekliyor.
  - Routing henüz `search.py` akışına bağlı değil. Uçtan uca akış (route → retrieval → LLM) 9. adımdan sonra kurulacak.
  - Query rewriting ve multi-query reranking'den sonra ölçüme göre değerlendirilecek.
- **Dikkat:** Gemini ücretsiz planı dakikada 15 istekle sınırlı (aşağıda "API sınırı"). Eval'ler bu yüzden yavaş çalışabilir.

## Durum (24.11.2026)
Proje 9 adımlık RAG akışına göre ilerliyor. **1–6 tamam, 7 (retrieval) bitmek üzere** (commit edildi; routing'den sonra test yeniden çalıştırılacak). Retrieval deneyinde Hit@5 10/10, MRR 0.817. `minScore` 0.0'da kalıyor; konu dışı soruları 5. adımdaki routing yakalıyor (routing test seti 32/32). Sırada 8 (reranking) ve 9 (prompt) var. Query rewriting ve multi-query, reranking'den sonra ölçüme göre değerlendirilecek.

| # | Adım | Durum | Nerede | Kısaca |
|---|---|---|---|---|
| 1 | Metin hazırlığı + metadata | ✅ | `extract.py`, `loaders/pdf.py`, `chunk.py` | PyMuPDF; 37 sayfa; 96 başlık; sayfa/bölüm/başlık metadata'sı |
| 2 | Chunking | ✅ | `chunk.py` | Başlığa göre bölme + `RecursiveCharacterTextSplitter`; 300 token / 50 overlap; 186 chunk |
| 3 | Embedding | ✅ | `embed.py` | `multilingual-e5-base`, 768 boyut, `passage:` öneki, normalize |
| 4 | Vector DB | ✅ | `embed.py` → `faiss.index` | FAISS `IndexFlatIP` (kesin arama) |
| 5 | Query processing: routing | ✅ | `route.py`, `eval/routing.jsonl` | `geçersiz` kural; `belge` / `sohbet` / `konu_dışı` LLM ile; 32/32, ~0.9 sn. Rewriting ve multi-query sonra |
| 6 | Query embedding | ✅ | `search.py` | Aynı model, `query:` öneki, normalize |
| 7 | Retrieval | 🔶 | `search.py`, `eval/retrieval.jsonl` | Top-5; Hit@5 10/10, Hit@1 7/10, MRR 0.817; `minScore` 0.0; routing'den sonra test tekrarlanacak |
| 8 | Reranking | ⬜ | — | Plan: cross-encoder ile ilk ~20 sonucu yeniden sırala |
| 9 | Prompt oluşturma | ⬜ | — | Plan: `prompts/system.md` + chunk'lar + kaynak bilgisi |
| → | LLM cevabı, kaynak gösterme, değerlendirme | ⬜ | — | 9'dan sonra (Gemini) |

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

### 5. Query processing: routing ✅
- **Kullanım:** `python rag/route.py "mesaj"` (tek mesaj) veya `python rag/route.py --eval` (test seti). Kod: `rag/route.py` → `Router(project).route(soru)` → `{route, reply, source, detail, ms}`. `source` = `kural` / `llm` / `hata`.
- **Amaç:** her soru retrieval'a girmesin. Soru önce bir rotaya ayrılır:

  | Rota | Örnek | Ne olur | Nasıl tespit edilir |
  |---|---|---|---|
  | `geçersiz` | boş, tek harf, çok uzun metin | `messages.json`'daki uyarı mesajı | Kural (uzunluk sınırları `project.json`'da), LLM'e gitmez |
  | `sohbet` | "merhaba", "teşekkürler" | Kısa, normal bir cevap | LLM |
  | `konu_dışı` | hava durumu, makarna tarifi | "Bu konuda yardımcı olamam" mesajı | LLM |
  | `belge` | "Firma kabul şartları nelerdir?" | Normal RAG akışı (6 → 9) | LLM |

- **Yöntem:** tek bir LLM çağrısı (Gemini, `project.json › llm.model`, `routing.temperature` 0.0). Prompt şablonu `prompts/routing.md`; içine belgenin kapsamı (`routing.scope`) ve `prompts.vars` giriyor. LLM, JSON şemasıyla `{route, reply}` döndürüyor; `route` bir enum olduğu için serbest metin gelemiyor. `sohbet` rotasında kısa cevabı (`reply`) aynı çağrı yazıyor, ikinci bir çağrı yok. `konu_dışı` ve `geçersiz` için sabit metinler `prompts/messages.json`'da. Router hiçbir örnek listesi veya veri seti kullanmaz; yeni projede yalnızca `scope` cümlesi, prompt ve mesaj metinleri değişir.
- **Kurallar (`geçersiz`):** boşluklar kırpıldıktan sonra `minChars` (3) altı, `maxChars` (1000) üstü ya da hiç harf içermeyen mesaj.
- **Hata davranışı:** LLM hata verirse (ağ, zaman aşımı 20 sn, bozuk cevap) soru `belge` sayılır, reddedilmez. Cevabı belgede yoksa 9. adımdaki "bilgim yok" kuralı yakalar. Geçici hatalarda (429, 503) tekrar deneniyor: canlı kullanımda en fazla ~2 sn bekleyip vazgeçiyor, `--eval`'de Google'ın önerdiği süre kadar (≤ 90 sn) bekliyor. Bekleme süresi gecikme ölçümüne dahil değil.
- **API sınırı (Gemini ücretsiz plan):** `gemini-3.5-flash-lite` için **dakikada 15 istek** (proje + model başına; hata: `429 RESOURCE_EXHAUSTED`, `GenerateRequestsPerMinutePerProjectPerModel-FreeTier`). Ayrıca yoğun saatlerde `503 UNAVAILABLE` görüldü. Sonuçları:
  - `--eval` (28 LLM çağrısı) kotaya takılıp ~35 sn bekleyebilir.
  - Canlı sistemde her belge sorusu en az 2 çağrı (routing + cevap) olacak, yani ücretsiz planla **dakikada ~7 soru**. Demo için yeterli, gerçek kullanım için ücretli plan gerekir.
  - Günlük istek sınırı da var, değeri ölçülmedi (Google AI Studio → Rate limits sayfasından kontrol edilmeli).
- **Neden embedding ile değil:** embedding ile routing hazır örnek cümlelere bağlı ve örneklerin arasına düşen garip sorularda yanlış karar verebilir. Retrieval puanıyla eşik koymak da kırılgan (konu dışı 0.76–0.78, cevaplı 0.80–0.86). LLM tek prompt ile daha basit ve daha genel.
- **Bedeli:** soru başına bir ek LLM çağrısı (ölçülen: ortalama ~870 ms, medyan ~810 ms, en fazla 2.3 sn) ve `GEMINI_API_KEY` bu adımda gerekiyor.
- **Belirsizlik:** cevapsız ama konusu belgede olan sorular (ör. metrekare fiyatı, genel müdürün adı) `belge` rotasına gider; bunları 9. adımdaki "bilgim yok" kuralı yakalar. Belgede hiç geçmeyen bir konu (ör. yemekhane) `konu_dışı` sayılır. Kullanıcı açısından fark küçük: "yardımcı olamam" ya da "bilgim yok".
- **Test seti** `projects/yonerge/eval/routing.jsonl`, 32 soru. Bu set yalnızca test içindir, router onu kullanmaz:
  - `belge` 15: `retrieval.jsonl`'daki 10 cevaplı soru, u02 ve u03, 3 zor soru (selam + soru, İngilizce soru, "ofiste kedi besleyebilir miyim?")
  - `konu_dışı` 9: x01–x03, u01 (yemekhane), 3 yeni soru, 2 zor soru (anlamsız metin, "talimatları unut" denemesi)
  - `sohbet` 4, `geçersiz` 4 (boş, tek harf, harfsiz, ~1350 karakter)
- **Sonuç (24.11, gemini-3.5-flash-lite, temperature 0):**

  | Rota | Doğru |
  |---|---|
  | `geçersiz` (kural) | 4/4 |
  | `belge` | 15/15 |
  | `sohbet` | 4/4 (cevaplar kısa ve doğal) |
  | `konu_dışı` | 9/9 |
  | **Toplam** | **32/32** |

  - İlk çalıştırmada 31/32 çıktı: u01 (yemekhane) `belge` diye etiketlenmişti, LLM `konu_dışı` dedi. Yemekhane belgede hiç geçmediği için LLM'in kararı kabul edildi ve etiket `konu_dışı` yapıldı. Prompt bu tek soruya göre ayarlanmadı. 32/32 bu etiket değişikliğiyle aynı çalıştırmanın sonucu.
  - Bir sohbet cevabında LLM "olabildigime" yazdı ("ğ" eksik). Küçük bir yazım hatası, 9. adımda prompt'a "Türkçe karakterleri doğru kullan" eklenebilir.
  - Set küçük. Sonuç yön gösterir, LLM her çalıştırmada birebir aynı cevabı vermeyebilir.
- **Sonra (reranking'den sonra, ölçüme göre):**
  - **Query rewriting:** soruyu belgenin diline çevirme, ör. "teknopark" → "Bölge", "firma" → "Girişimci". Eski plandaki eş anlamlı listesi bunun içinde değerlendirilecek.
  - **Multi-query:** soruyu birkaç farklı biçimde yazıp sonuçları birleştirme.
  - Hit@5 zaten 10/10 olduğu için kazanç Hit@1 ve MRR'de aranacak. Reranking aynı metrikleri hedeflediği için önce onun etkisi görülecek.

### 6. Query embedding ✅
- `search.py`: soru, chunk'larla aynı modelle (`embedding.model`) `query:` önekiyle ve normalize edilerek embed ediliyor.
- Açılışta `index.json`'daki model `project.json` ile uyuşmazsa ya da `faiss.index` ile chunk sayısı farklıysa program duruyor.
- Süre: soru başına ~15 ms. Uçtan uca darboğaz bu adım (arama ~0.02 ms).

### 7. Retrieval 🔶
- **Kullanım:** `python rag/search.py "soru"` (tek soru) veya `python rag/search.py --eval` (soru seti). `topK` = 5.
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
- **`minScore` kararı (24.11): 0.0.** Boşluk çok dar olduğu için puan eşiği kullanılmıyor. Konu dışı soruları 5. adımdaki routing, cevapsız soruları 9. adımdaki "bilgim yok" kuralı yakalar. (Elenen seçenek: ~0.79 eşikle konu dışı soruları baştan elemek.)

### 8. Reranking ⬜
- **Neden:** Hit@1 %70 ve ilk sonuçların puanları birbirine çok yakın (ör. q01'de 0.827 / 0.826 / 0.825).
- **Plan:** FAISS'ten ilk ~20 sonucu al, soru ile metni birlikte okuyan bir cross-encoder ile yeniden sırala, ilk 5'i kullan. Türkçe destekleyen aday: `BAAI/bge-reranker-v2-m3` (henüz denenmedi).
- **Ölçüm:** aynı `retrieval.jsonl` ile Hit@1 ve MRR'nin önceki ve sonraki değerleri karşılaştırılacak. Cevapsız soruları ayırmaya katkısı da ayrıca ölçülecek.

### 9. Prompt oluşturma ⬜
- **Plan:** `projects/<id>/prompts/system.md` şablonu (`{organization}`, `{assistantName}` değişkenleriyle) + seçilen chunk'lar (bölüm, başlık ve sayfa bilgisiyle) + soru.
- **Kurallar:** yalnızca verilen metinden cevap ver; kaynak bölümü ve sayfayı göster; cevap metinde yoksa `messages.json`'daki "bilgim yok" mesajını kullan.

### Sonrası: LLM cevabı, kaynak gösterme, değerlendirme ⬜
- Gemini `gemini-3.5-flash-lite` (`project.json › llm`, temperature 0.1). `GEMINI_API_KEY` 5. adımdaki routing'den itibaren gerekiyor.
- Kaynaklar backend'de, LLM'in seçtiği değil retrieval'ın getirdiği chunk'lardan üretiliyor.
- Değerlendirme seti (`eval/testset.jsonl`) cevap kalitesini ölçecek (doğruluk, kaynak, "bilgim yok" davranışı). Değerlendirme scripti genel olacak.

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
│       ├── eval/routing.jsonl     # ✅ routing test seti (adım 5)
│       ├── eval/testset.jsonl     # ⬜ cevap değerlendirme seti
│       ├── prompts/               # ✅ routing.md, messages.json (adım 5) · ⬜ system.md (adım 9)
│       └── guardrails/rules.json  # ⬜ (Part 4)
├── rag/                           # Python çekirdek — projeden bağımsız
│   ├── config.py                  # PROJECT seç → project.json + .env oku, doğrula
│   ├── extract.py                 # 1 → index/<id>/pages.json
│   ├── loaders/                   # pdf.py (PyMuPDF) — ileride docx.py, html.py…
│   ├── chunk.py                   # 1–2 → index/<id>/chunks.json
│   ├── embed.py                   # 3–4 → index/<id>/index.json + faiss.index
│   ├── route.py                   # 5 → soru rotası (geçersiz / sohbet / konu_dışı / belge)
│   └── search.py                  # 6–7 → retrieval ve soru seti deneyi
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
  "routing":   {
    "scope": "YTÜ Yıldız Teknopark Bölge İşletme Yönergesi: firma kabulü, kira ve aidat, ortak alanlar, personel, tadilat, kuluçka, vergi muafiyetleri",
    "minChars": 3,
    "maxChars": 1000
  },
  "retrieval": { "topK": 5, "minScore": 0.0 },

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
- `routing.scope`: belgenin kapsamını anlatan tek cümle; routing prompt'una girer. `minChars` / `maxChars`: `geçersiz` rotasının kural sınırları (değerler örnek, adım 5'te test setiyle ayarlanacak).
- `minScore`: 0.0 (adım 7 kararı). Konu dışı kontrolünü routing yapar.
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
  - [x] 5 Query routing (geçersiz: kural; belge / sohbet / konu dışı: LLM; `routing.jsonl` 32/32)
  - [x] 6 Query embedding
  - [ ] 7 Retrieval (deney tamam, Hit@5 10/10; `minScore` 0.0; commit edildi; routing'den sonra test tekrarlanacak)
  - [ ] 8 Reranking (cross-encoder, aynı soru setiyle ölç)
  - [ ] 5+ Query rewriting / multi-query (reranking'den sonra, ölçüme göre)
  - [ ] 9 Prompt oluşturma
  - [ ] LLM cevabı + backend'de üretilen kaynaklar
  - [ ] Cevap değerlendirme seti ve scripti
- **Part 2 — Web API (Node/Express):** `POST /api/chat`, `GET /api/config` (arayüz metinleri); aktif projenin indeksini okur; açılışta embedding uyumu kontrolü
- **Part 3 — Arayüz:** HTML/CSS/vanilla JS; başlık, karşılama ve örnek sorular `/api/config`'ten
- **Part 4 — Guardrails:** genel kural motoru (`src/guardrails/`) + projeye özel kurallar (`rules.json`) + saldırı/sınır test seti. Odak: prompt injection, saldırı ve sınır durumları, istenirse cevabın kaynaklara dayanıp dayanmadığı. Konu dışı kararını 5. adımdaki routing verir; ikinci bir konu dışı kontrolü yalnızca ölçümde routing'in kaçırdığı görülürse eklenir (her ek ret katmanı geçerli soruları yanlışlıkla reddetme riskini artırır).
- **Part 5 — Taşınabilirlik testi:** farklı türde ikinci bir belgeyle (ör. başlıksız bir SSS) yeni proje paketi oluştur, **kod değiştirmeden** uçtan uca çalıştır
- **Part 6 — Teslim:** README, mimari notu, "yeni proje nasıl eklenir" rehberi, 3 dk demo akışı (demoda proje değiştirmeyi de göster)

## Teknoloji kararları
Model ve parametreler `project.json`'dan seçildiği için değiştirmek kod değişikliği gerektirmez.

| Bileşen | Seçim |
|---|---|
| Python | 3.11+ (test: 3.13), sanal ortam `.venv` |
| PDF extraction | PyMuPDF (`pymupdf`) — `rag/loaders/pdf.py` |
| Chunking | Kendi başlık tespiti + LangChain `RecursiveCharacterTextSplitter` (`langchain-text-splitters`) |
| Embedding | Yerel `intfloat/multilingual-e5-base`, 768 boyut (`sentence-transformers`) |
| Vector store | FAISS `IndexFlatIP` (`faiss-cpu`, kesin arama); metin/metadata `index.json`'da. Büyürse `IndexHNSWFlat` |
| Reranker | Aday: `BAAI/bge-reranker-v2-m3` (adım 8, denenmedi) |
| LLM | Gemini `gemini-3.5-flash-lite` (Python `google-genai` 3.6, Node `@google/genai`); routing (adım 5) ve cevap. Ücretsiz plan: dakikada 15 istek |
| Proje ayarları | `projects/<id>/project.json` (Python ve Node ortak) |
| Web (Part 2–3) | Node.js 22+, Express 5, HTML/CSS/vanilla JS |

Not: FAISS tek dosyalık yerel bir indeks. Çok büyük veya sık güncellenen projelerde Qdrant, Chroma ya da pgvector gibi sunucu tabanlı bir veritabanına geçilebilir; bu değişiklik Node tarafında yalnızca `retrieval.js`'i etkiler.

## Dosyalar
- `.env.example` — ortam değişkenleri şablonu (`PORT`, `PROJECT`, `GEMINI_API_KEY`); `.env` git'e girmez.
- `projects/yonerge/project.json` — ilk proje paketi ayarları; `projects/_template/` — yeni proje şablonu.
- `projects/yonerge/eval/retrieval.jsonl` — retrieval soru seti. Her satır `{id, question, expected: [bölüm], difficulty, note?}`. `expected` boşsa soru cevapsız/konu dışıdır ve `difficulty` etiketine göre gruplanır.
- `rag/config.py` — `--project` / `PROJECT` / `.env` ile proje seçer, `project.json`'ı okur ve doğrular. `project.get("a.b")` eksik alanda açık hata verir.
- `rag/loaders/` — `get_loader(type)` kaydı; `pdf.py` (PyMuPDF, `skipPages` uygular, PDF tarihini ISO'ya çevirir).
- `rag/extract.py` — tüm `sources` → `index/<id>/pages.json` (`pages[]` = `{source, page, text}`; `page` = PDF sayfa sırası).
- `rag/chunk.py` — `pages.json` → `index/<id>/chunks.json` (`chunks[]` = `{id, text, tokens, metadata}`; `id` = `<proje>-<bölüm>-<sıra>`). Sınırı aşan chunk varsa hata koduyla çıkar.
- `rag/embed.py` — `chunks.json` → embedding → FAISS → `faiss.index` + `index.json`. Kontroller başarısızsa çıkış kodu 2 ve hiçbir dosya yazılmaz; `chunks.json` eskiyse çıkış kodu 1. İsteğe bağlı `embedding.batchSize` (varsayılan 32).
- `rag/search.py` — tek soru (`"soru"`) veya soru seti (`--eval`, `--top N`). Rapor: Hit@1/3/5, MRR, ilk K'ya giremeyenler, grup bazında puan aralıkları ve `minScore` ile ayrım yapılıp yapılamadığı.
- `projects/yonerge/eval/routing.jsonl` — routing test seti. Her satır `{id, question, route, note?}`; `route` ∈ `geçersiz` / `sohbet` / `konu_dışı` / `belge`. Yol `eval.routing` ile değiştirilebilir.
- `projects/yonerge/prompts/routing.md` — routing prompt şablonu (`{scope}` + `prompts.vars`); `prompts/messages.json` — `geçersiz` ve `konu_dışı` sabit cevapları (`{organization}` gibi değişkenler doldurulur).
- `rag/route.py` — tek mesaj (`"mesaj"`) veya test seti (`--eval`). Rapor: toplam ve rota başına doğruluk, karışıklık tablosu, yanlış reddedilen `belge` soruları, LLM hataları (varsa "sonuçlar güvenilir değil" uyarısı), gecikme.
- `requirements.txt` — `pymupdf`, `sentence-transformers` (PyTorch ile gelir), `langchain-text-splitters`, `faiss-cpu`, `google-genai`. Model (~1.1 GB) ilk kullanımda Hugging Face'ten bir kez indirilir.
- `package.json` — Node tarafı (Part 2'de doldurulacak).

## Nasıl çalıştırılır
```bash
cp .env.example .env               # GEMINI_API_KEY routing (adım 5) ve LLM adımında gerekir
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python rag/extract.py              # 1   → pages.json  (veya --project yonerge)
python rag/chunk.py                # 1–2 → chunks.json
python rag/embed.py                # 3–4 → index.json + faiss.index
python rag/search.py "Ortak alanlar nasıl kullanılır?"   # 6–7 tek soru
python rag/search.py --eval        # 6–7 soru seti deneyi
python rag/route.py "Merhaba"      # 5   tek mesaj (GEMINI_API_KEY gerekir)
python rag/route.py --eval         # 5   routing test seti (~1–2 dk, kota beklemesi olabilir)
```
Beklenen: `extract.py` → 41 sayfa, 4 atlanan, 37 alınan. `chunk.py` → 96 bölüm, 186 chunk. `embed.py` → `Doğrulama: tamam`. `search.py --eval` → Hit@5 10/10. `route.py --eval` → 32/32 (LLM olduğu için küçük oynamalar olabilir).

## Yeni proje ekleme (kontrol listesi)
1. `projects/_template/` → `projects/<yeni-id>/` olarak kopyala.
2. Belgeleri `data/` altına koy, `project.json` → `sources` listesini doldur.
3. Belgenin başlık yapısına göre `chunking` ayarlarını yaz (başlık yoksa `fixed`).
4. `prompts/routing.md`, `prompts/system.md`, `messages.json`, `routing.scope` ve `ui` metinlerini yeni alana göre yaz.
5. `.env` → `PROJECT=<yeni-id>`.
6. `python rag/extract.py && python rag/chunk.py && python rag/embed.py`
7. `eval/retrieval.jsonl` soru setini yaz, `python rag/search.py --eval` ile `topK`/`minScore` ayarla. `eval/routing.jsonl` yaz, `python rag/route.py --eval` ile routing'i kontrol et.
8. `eval/testset.jsonl` hazırla ve cevap değerlendirmesini çalıştır.
9. `npm start` → arayüz yeni projenin başlık ve metinleriyle açılır.

## Mevcut sınırlamalar
- Paragraf sınırı sezgisel: satır `. : ; ! ?` ile bitiyorsa ya da boş satır, `•` veya `Terim:` ile başlıyorsa yeni blok. Yanlış birleşme yalnızca bölme noktasını etkiler, metin kaybolmaz.
- e5 puanları dar bir aralıkta (cevaplı 0.80–0.86, ilgisiz 0.76–0.78). Bu yüzden sabit bir `minScore` kırılgan.
- Soru setleri küçük (retrieval 16, routing 32 soru); sonuçlar yön gösterir, kesin değildir.
- Gemini ücretsiz planı dakikada 15 istekle sınırlı. Routing + cevap ile dakikada ~7 soru yanıtlanabilir.
- Routing her belge sorusuna ~0.9 sn ekliyor.

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
