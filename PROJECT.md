# PROJECT.md — Yeniden Kullanılabilir RAG Chatbot (ilk proje: Teknopark Yönergesi)

## Durum
**Part 1 / Adım 1.2 + 1.2b tamamlandı (17.11.2026).** `PROJECT=yonerge python rag/extract.py` → 41 sayfa, s. 1–4 atlandı, 37 sayfa / ~148 bin karakter → `index/yonerge/pages.json`. Türkçe karakterler ve `•` sorunsuz.

**17.11.2026 — 1.3 Chunking tamamlandı.** `python rag/chunk.py` → 96 bölüm, 186 chunk, 58–298 token (medyan 227; ~205–1426 karakter), `passage:` öneki ve özel tokenlarla en fazla 302 token (512 sınırının altında), metin kaybı yok → `index/yonerge/chunks.json`.
- Yöntem: önce numaralı başlığa göre bölme (bölüm sınırı asla aşılmaz), 300 tokenı aşan bölümler kendi içinde LangChain `RecursiveCharacterTextSplitter` ile `•` → satır → cümle sınırlarından bölünür, overlap 50 token (yalnızca aynı bölüm içinde; madde sınırında bölündüğünde örtüşme olmayabilir).
- Boyut **token** ile ölçülür: splitter'ın `length_function`'ı embedding modelinin tokenizer'ı (`embedding.model`'den okunur, kodda model adı yok). Embedding modeli değişirse chunking de yeniden çalıştırılır. Her chunk'ın başında başlık yolu var: `7. … > 7.1. … > 7.1.5. …`.
- Hukuki birim = numaralı bölüm. Bu belgede `MADDE N` yapısı yok; metin kendi içinde "6.4. maddesinde" diye bu numaralara atıf yapıyor.
- PDF'te görülen başlık biçimleri: `7.1.5. Başlık`, numara tek satırda + alt satırda BÜYÜK HARF başlık (`10.1.`), boşluksuz `8.1.BAŞLIK`, alt satıra taşan büyük harfli başlık. `headingPatterns` bunlara göre güncellendi (üstten alta sıralı).

**17.11.2026 — 1.3 / 1.4 hazırlığı:**
- Embedding kararı `project.json`'a işlendi: `yonerge` ve `_template` → `e5` / `intfloat/multilingual-e5-small`; chunking boyutu sonra token'a çevrildi (`maxTokens` 300, `overlap` 50).
- `requirements.txt`'e `sentence-transformers` eklendi ve `.venv`'e kuruldu (sentence-transformers 6.3, torch 2.15, transformers 5.23).
- Model indirildi ve yerel önbellekte; kısa test: 384 boyut, normalize (norm 1.0), `max_seq_length` 512. Önekli örnekte ilgili cümle 0.867, ilgisiz 0.775 → sıralama doğru, puanlar birbirine yakın (e5'te normal; eşik 1.5'te).
- `prompts/`, `guardrails/`, `eval/` henüz yok; ilgili adımda (1.6, 1.7, Part 4) oluşturulacak.

**17.11.2026 — 1.4 Embedding tamamlandı.** `python rag/embed.py` → 186 chunk, 384 boyut, hepsi normalize, önekli giriş (özel tokenlar dahil) en fazla 302 / 512 token → `index/yonerge/index.json` (1.1 MB, ~4 sn, CPU).
- `rag/providers/`: `get_provider(embedding_cfg)` kaydı + `e5.py` adaptörü (`passage:` / `query:` önekleri yalnızca adaptörde). Boyut ve token sınırı modelden okunur, kodda sabit yok.
- `embed.py` kaydetmeden önce doğrular (sayı, boyut, NaN, norm, token sınırı, chunks.json'un aynı tokenizer'la üretilmesi); hata varsa `index.json` yazılmaz.
- İlk hızlı kontrol: "Ortak alanlar nasıl kullanılır?" → 7.1.7 (ilk 3'ün hepsi), "Kira ödemesi gecikirse…" → 7.2.1. "Firma kabul şartları nelerdir?" → ilk 3'te 7.1.5 / 7.2.1 / 7.1.6; beklenen 10.1 (Aday Girişimci Başvuru…) ilk 3'te değil. Puanlar 0.84–0.86 aralığında, birbirine çok yakın → 1.5'te incelenecek.

**Sıradaki: 1.5 Retrieval testi** → `rag/search.py` + 10 soruluk deney (doğru bölüm ilk 5'te mi?), ardından `topK` / `minScore`.

**17.11.2026 — Embedding kararı:** Deneysel aşamada kapsam küçük tutulacak. Embedding için yerel **`intfloat/multilingual-e5-small`** kullanılacak (adaptör: `e5`). API anahtarı ve kota gerekmez, aynı girdi her zaman aynı vektörü verir. Gemini embedding adaptörü sonra eklenebilir; geçiş `project.json`'da tek satır değişikliktir. Bugünün hedefi: **Document Processing + Embedding Pipeline** (temizlik → yapı tespiti → chunking → embedding → kaydet ve doğrula).

**17.11.2026 — Yeni karar:** Sistem yönergeye özel olmayacak. Kod genel, içerik projeye özel olacak; yeni bir belge veya müşteri için yalnızca bir proje klasörü hazırlanacak. → **Adım 1.2b** (aşağıda) 1.3'ten önce yapılacak.

## Temel ilke: çekirdek + proje paketi
Sistem iki parçadan oluşur:

| Parça | İçerik | Yeni projede |
|---|---|---|
| **Çekirdek** (`rag/`, `src/`, `public/`) | Extraction, chunking, embedding, retrieval, LLM çağrısı, guardrail motoru, API, arayüz | **Değişmez** |
| **Proje paketi** (`projects/<proje-id>/`) | Belgeler, `project.json` ayarları, prompt'lar, mesaj metinleri, guardrail kuralları, test seti, arayüz metinleri | Yeniden yazılır |

**Kurallar**
1. Çekirdek kodda belgeye özel hiçbir şey olmaz: dosya adı, sayfa numarası, başlık kalıbı, prompt, "Teknopark" kelimesi, model adı, eşik değeri. Bunların hepsi `project.json` veya proje klasöründen okunur.
2. Aktif proje tek bir değişkenle seçilir: `.env` içinde `PROJECT=yonerge` (veya `--project yonerge` argümanı).
3. Sağlayıcılar (Gemini vb.) bir **adaptör** arkasındadır. Model ya da sağlayıcı değişirse `project.json`'da tek satır değişir.
4. **Kabul kriteri:** Yeni bir proje eklerken `rag/`, `src/` veya `public/` altında kod değişikliği gerekiyorsa bu bir tasarım hatası sayılır ve çekirdek genelleştirilir.

## Mimari kararı (16.11.2026, 17.11'de genelleştirildi)
- **Python (`rag/`)**: Offline işler: belge okuma, chunking, embedding, indeks oluşturma,
  retrieval denemeleri, değerlendirme. Çıktısı: `index/<proje-id>/index.json`.
- **Node.js + Express (`src/`, Part 2)**: Çalışan web uygulaması. Aktif projenin `index.json`'ını okur,
  soruyu embed eder, retrieval + LLM çağrısı yapar, arayüzü sunar.
- Uygulama çalışırken **tek sunucu** (Node) var; Python yalnızca indeks üretirken çalışır.
- İki taraf arasındaki sözleşmeler:
  - **`projects/<proje-id>/project.json`** → iki taraf da aynı ayar dosyasını okur. Ek bağımlılık gerekmesin diye YAML değil JSON (Python `json`, Node `JSON.parse`).
  - **`index/<proje-id>/index.json`** → embedding sağlayıcısı, modeli ve ayarları bu dosyaya da yazılır. Node açılışta `project.json` ile `index.json`'daki embedding ayarlarını karşılaştırır. Uyuşmazsa **başlamaz** ve "indeksi yeniden oluştur" hatası verir (farklı modelle embed edilmiş soru ve parçalar karşılaştırılamaz).

## Klasör yapısı (hedef)
```
tkpark-ragagent/
├── projects/
│   ├── _template/                 # yeni proje için kopyalanacak boş şablon
│   └── yonerge/                   # ilk proje paketi
│       ├── project.json           # tüm projeye özel ayarlar
│       ├── data/yonerge.pdf       # kaynak belge(ler)
│       ├── prompts/
│       │   ├── system.md          # botun kimliği ve kuralları ({değişken}'li şablon)
│       │   └── messages.json      # "bilgim yok", ret, hata mesajları
│       ├── guardrails/rules.json  # konu, PII kalıpları, şüpheli ifadeler (Part 4)
│       └── eval/testset.jsonl     # değerlendirme seti (1.7)
├── rag/                           # Python çekirdek — projeden bağımsız
│   ├── config.py                  # PROJECT seç → project.json + .env oku, doğrula
│   ├── extract.py                 # kaynak → index/<id>/pages.json
│   ├── chunk.py                   # (1.3) → index/<id>/chunks.json
│   ├── embed.py                   # (1.4) → index/<id>/index.json
│   ├── search.py                  # (1.5) retrieval testi
│   ├── loaders/                   # pdf.py (PyMuPDF) — ileride docx.py, html.py…
│   └── providers/                 # embedding adaptörleri: gemini.py …
├── src/                           # Node çekirdek — projeden bağımsız (Part 2)
│   ├── server.js
│   ├── config.js                  # aynı project.json'ı okur
│   ├── retrieval.js
│   ├── providers/                 # llm/gemini.js, embedding/gemini.js …
│   └── guardrails/                # kural motoru; kurallar proje klasöründen
├── public/                        # arayüz (Part 3) — başlık/metinler /api/config'ten gelir
├── index/                         # üretilen dosyalar (git'e girmez)
│   └── yonerge/{pages,chunks,index}.json
├── .env.example
└── requirements.txt
```
`prompts/`, `guardrails/` ve `eval/` klasörleri ilgili adımda (1.6, 1.7, Part 4) oluşturulacak.

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

  "embedding": { "provider": "e5", "model": "intfloat/multilingual-e5-small" },
  "llm":       { "provider": "gemini", "model": "gemini-3.5-flash-lite", "temperature": 0.1 },
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
- `headingPatterns` üst seviyeden alta sıralıdır (1. eleman = 1. seviye); eşleşen kısım bölüm numarasıdır, kalan metin başlıktır.
- `maxTokens: 300`, `overlap: 50`: token, embedding modelinin tokenizer'ıyla sayılır (başlık yolu dahil; `passage:` öneki ve özel tokenlar hariç). E5 en fazla 512 token alır ve fazlasını sessizce keser; 300 bu önekler ve pay için yer bırakır. 1.4'te önekli gerçek giriş yeniden doğrulanır.
- `minScore` 1.5'teki retrieval testinden sonra ayarlanacak (Part 4'te konu dışı guardrail'i de bunu kullanacak).
- Başlığı olmayan bir belgede `strategy: "fixed"` kullanılır; `heading` stratejisi hiçbir başlık bulamazsa `fallback`'e düşülür.

## `index.json` sözleşmesi
```json
{
  "schemaVersion": 1,
  "project": "yonerge",
  "createdAt": "2026-11-18T10:00:00Z",
  "embedding": { "provider": "e5", "model": "intfloat/multilingual-e5-small", "dimensions": 384, "normalized": true },
  "chunks": [
    {
      "id": "yonerge-7.1.5-0",
      "text": "…",
      "vector": [0.012, -0.044, …],
      "metadata": { "source": "data/yonerge.pdf", "section": "7.1.5", "title": "…", "path": ["7. …", "7.1. …", "7.1.5. …"], "pages": [13, 14] }
    }
  ]
}
```
`dimensions` değeri, 1.4'te modelin döndürdüğü gerçek boyuttan yazılır (`multilingual-e5-small` için 384). Vektörler normalize edildiği için cosine benzerliği dot product'a eşittir. `metadata` alanları kaynak türüne göre değişebilir; çekirdek yalnızca `source` alanını zorunlu tutar.

## Sağlayıcı adaptörleri
Her iki tarafta da çekirdek yalnızca şu küçük arayüzleri çağırır:

| Arayüz | Python (`rag/providers/`) | Node (`src/providers/`) |
|---|---|---|
| Embedding | `embed(texts: list[str], kind: "document" \| "query") -> list[list[float]]` | `embed(texts, kind) → Promise<number[][]>` |
| LLM | — (Python'da LLM yalnızca değerlendirmede) | `generate(messages, opts) → Promise<string>`, ileride `stream(...)` |

Seçim `project.json` → `"provider": "e5"` ile yapılır. Yeni bir sağlayıcı eklemek = yeni bir adaptör dosyası + kayıt satırı. `kind`, çekirdeğin sağlayıcıdan bağımsız olarak "parça mı, soru mu" bilgisini iletmesidir. Sağlayıcıya özel karşılığı yalnızca adaptörün içinde kalır.

**`e5` adaptörü (`intfloat/multilingual-e5-small`)**
- Python: `rag/providers/e5.py`, `sentence-transformers` ile yerelde, `normalize_embeddings=True`.
- Node (Part 2): `src/providers/embedding/e5.js`, `@huggingface/transformers` (transformers.js) + `Xenova/multilingual-e5-small` (ONNX). Böylece çalışma anında tek sunucu (Node) kararı korunur.
- Önekler: `kind="document"` → `"passage: "`, `kind="query"` → `"query: "`. Önekler olmadan kalite belirgin düşer.
- Model düz `e5-small` değil, **multilingual** sürüm olmalı (düz sürüm İngilizce için eğitildi).
- Giriş sınırı 512 token; aşan metin kesilir. Bu yüzden `chunking.maxTokens` 300 tutulur ve 1.4'te önekli token sayısı doğrulanır.
- Python ve Node aynı soru için aynı vektörü üretmeli; Part 2'de bir kez karşılaştırılır.
- Kalite yetmezse sırasıyla `intfloat/multilingual-e5-base` / `-large` veya `gemini` adaptörü denenir (tek satır değişiklik + indeksi yeniden oluşturma).

## Yeni proje ekleme (kontrol listesi)
1. `projects/_template/` → `projects/<yeni-id>/` olarak kopyala
2. Belgeleri `data/` altına koy, `project.json` → `sources` listesini doldur
3. Belgenin başlık yapısına göre `chunking` ayarlarını yaz (başlık yoksa `fixed`)
4. `prompts/system.md`, `messages.json`, `ui` metinlerini yeni alana göre yaz
5. `.env` → `PROJECT=<yeni-id>`
6. `python rag/extract.py && python rag/chunk.py && python rag/embed.py`
7. `python rag/search.py` ile birkaç soru dene, `minScore`/`topK` ayarla
8. `eval/testset.jsonl` hazırla ve değerlendirmeyi çalıştır
9. `npm start` → arayüz yeni projenin başlık ve metinleriyle açılır

## İlk proje paketi: `yonerge` — belge notları
- Dosya: `projects/yonerge/data/yonerge.pdf`
- Başlık: YTÜ Yıldız Teknopark Bölge İşletme Yönergesi (bir "yönerge"; Bakanlık yönetmeliği değil)
- 41 PDF sayfası, ~18.000 kelime, Word'den üretilmiş, metin katmanı var → OCR gerekmiyor
- Tarih: Metinde onay/yürürlük tarihi veya sürüm yok. PDF metadata oluşturulma tarihi: 2025-01-28.
- Sayfalarda basılı sayfa numarası yok. İçindekiler'deki numaralar = PDF sayfası − 1.
  Uygulama yalnızca PDF sayfa sırasını kullanır.

**Belge yapısı (→ `project.json` › `chunking`)**
- Numaralı başlıklar: `1.` … `21.`, `7.1.`, `7.1.5.` (en fazla 3 seviye) + `7.2.2` altında `a.` / `b.`
- Resmî yönetmelik biçimindeki "madde / fıkra / bent" (`MADDE 5 – (1) a)`) yapısı **yok**. Yapı tespiti bu başlık hiyerarşisiyle yapılır. İleride gerçek bir yönetmelik eklenirse yalnızca o projenin `headingPatterns`'ı yazılır.
- İçerik çoğunlukla `•` maddeli kurallar ve paragraflar
- Bölüm 3 "Tanım ve Kısaltmalar": `Terim: tanım` listesi
- PDF s. 1 kapak, s. 2–4 İçindekiler → indekse alınmayacak (`skipPages`)
- Tablo tespit edilmedi

## Yol haritası
- **Part 1 — RAG çekirdeği (Python, terminal)**
  - [x] 1.1 PDF incelemesi
  - [x] 1.2 Text extraction (PyMuPDF) → `index/<id>/pages.json`
  - [x] **1.2b Genelleştirme**
    - `projects/yonerge/` ve `projects/_template/` klasörlerini oluştur, PDF'i taşı, `project.json` yaz
    - `rag/config.py`: `PROJECT` → `project.json` okuma + doğrulama (eksik alan varsa açık hata)
    - `rag/extract.py`: belge yolu ve `skipPages` config'ten gelsin; PDF okuma `rag/loaders/pdf.py`'de; çıktı `index/<id>/pages.json`
    - `requirements.txt` (`pymupdf`)
    - Kontrol: kodda `grep -ri "yonerge\|teknopark" rag/` sonuç vermemeli
  - [x] 1.3 Temizlik + yapı tespiti + chunking (`heading` + `fixed` stratejileri, kalıplar config'ten) → `index/<id>/chunks.json`
    - Text cleaning: PDF satır sonlarını birleştir, boş satır ve fazla boşlukları temizle
    - Structure detection: `headingPatterns` ile başlık hiyerarşisi (`section`, `title`)
    - Chunking: bölüm bazlı, `maxTokens` aşılırsa `bullet` sınırlarından böl
  - [x] 1.4 Embeddings (`e5` adaptörü, `multilingual-e5-small`) → `index/<id>/index.json`
    - [x] Hazırlık: `project.json` e5'e geçti, `sentence-transformers` kuruldu, model indirildi ve test edildi
    - [x] Save & validate: vektör sayısı = chunk sayısı, tüm vektörler 384 boyutlu ve normalize, önekle birlikte hiçbir chunk 512 tokeni aşmıyor
    - **Deney başarı ölçütü (1.5'te):** 10 soruda doğru bölüm `search.py` ile ilk 5 sonuçta geliyor
  - [ ] 1.5 Retrieval testi (LLM yok) → `minScore`/`topK` belirlenir
  - [ ] 1.6 LLM + backend'de üretilen kaynaklar (prompt `prompts/system.md`'den)
  - [ ] 1.7 Değerlendirme seti (`projects/<id>/eval/testset.jsonl`, değerlendirme scripti genel)
- **Part 2 — Web API (Node/Express):** `POST /api/chat`, `GET /api/config` (arayüz metinleri), aktif projenin `index.json`'ını okur, açılışta embedding uyumu kontrolü
- **Part 3 — Arayüz:** HTML/CSS/vanilla JS; başlık, karşılama ve örnek sorular `/api/config`'ten
- **Part 4 — Guardrails:** genel kural motoru (`src/guardrails/`) + projeye özel kurallar (`rules.json`) + saldırı/sınır test seti
- **Part 5 — Taşınabilirlik testi:** farklı türde ikinci bir belgeyle (ör. başlıksız bir SSS veya kısa bir kılavuz) yeni proje paketi oluştur, **kod değiştirmeden** uçtan uca çalıştır
- **Part 6 — Teslim:** README, mimari notu, "yeni proje nasıl eklenir" rehberi, 3 dk demo akışı (demoda proje değiştirmeyi de göster)

## Teknoloji kararları
Bunlar varsayılanlardır. Sağlayıcı ve model `project.json`'dan seçildiği için değiştirmek kod değişikliği gerektirmez.

| Bileşen | Seçim |
|---|---|
| Python | 3.11+ (test: 3.13), sanal ortam `.venv` |
| PDF extraction | PyMuPDF (`pymupdf`) — `rag/loaders/pdf.py` |
| Embedding | Yerel `intfloat/multilingual-e5-small`, 384 boyut (adaptör: `e5`). Alternatif: Gemini `gemini-embedding-2` (adaptör: `gemini`) |
| LLM | Gemini `gemini-3.5-flash-lite` (adaptör: `gemini`) |
| SDK | Embedding: Python `sentence-transformers`, Node `@huggingface/transformers`. LLM: Python `google-genai`, Node `@google/genai` (yalnızca adaptör dosyalarında) |
| Vector store | Yerel JSON + cosine similarity (proje başına bir `index.json`) |
| Proje ayarları | `projects/<id>/project.json` (Python ve Node ortak) |
| Web (Part 2–3) | Node.js 22+, Express 5, HTML/CSS/vanilla JS |

Not: Yerel JSON birkaç bin chunk'a kadar yeterli. Daha büyük projelerde vektör DB adaptörü (Chroma, Qdrant, pgvector) eklenebilir. Sözleşme `index.json` olduğu için bu değişiklik Node tarafında yalnızca `retrieval.js`'i etkiler.

## Dosyalar
- `.env.example` — ortam değişkenleri şablonu (`PORT`, `PROJECT`, `GEMINI_API_KEY`); `.env` git'e girmez
- `projects/yonerge/project.json` — ilk proje paketi ayarları; `projects/_template/` — yeni proje şablonu
- `rag/config.py` — `--project` / `PROJECT` / `.env` ile proje seçer, `project.json`'ı okur ve doğrular
  (`id` = klasör adı, `sources[].path` ve `type` dolu ve dosya mevcut). `project.get("a.b")` eksik alanda açık hata verir.
  `.env` kendi küçük okuyucusuyla okunur (ek bağımlılık yok); tanımlı ortam değişkenleri önceliklidir.
- `rag/loaders/` — `get_loader(type)` kaydı; `pdf.py` (PyMuPDF, `skipPages` uygular, PDF tarihini ISO'ya çevirir)
- `rag/extract.py` — tüm `sources` → `index/<id>/pages.json`
  (`schemaVersion`, `project`, `createdAt`, `sources[]` meta, `pages[]` = `{source, page, text}`; `page` = PDF sayfa sırası)
- `rag/chunk.py` — `pages.json` → `index/<id>/chunks.json` (`chunks[]` = `{id, text, tokens, metadata: {source, section, title, path, pages}}`; `id` = `<proje>-<bölüm>-<sıra>`, `pages` = kaynak sayfa sırası). Satır birleştirme, başlık tespiti, bölüm içi bölme; sınırı aşan chunk varsa hata koduyla çıkar.
- `rag/providers/` — embedding adaptörleri; `get_provider(cfg)` kaydı ve `EmbeddingProvider` arayüzü (`embed`, `count_tokens`, `dimensions`, `normalized`, `token_limit`). `e5.py`: sentence-transformers, önekler, `normalize_embeddings=True`, isteğe bağlı `embedding.batchSize` (varsayılan 32).
- `rag/embed.py` — `chunks.json` → `index/<id>/index.json` (`schemaVersion`, `project`, `createdAt`, `embedding` = config + `dimensions` + `normalized`, `chunking`, `chunks[]` = `{id, text, vector, metadata}`; vektörler 7 ondalığa yuvarlanır). Doğrulama başarısızsa çıkış kodu 2, dosya yazılmaz.
- `requirements.txt` — `pymupdf`, `sentence-transformers` (PyTorch ile birlikte gelir), `langchain-text-splitters`. `multilingual-e5-small` modeli (~470 MB) ilk kullanımda Hugging Face'ten bir kez indirilir ve yerel önbellekte tutulur.
- `package.json` — Node tarafı (Part 2'de doldurulacak)

## Nasıl çalıştırılır
```bash
cp .env.example .env               # E5 yerel çalışır; GEMINI_API_KEY yalnızca LLM (1.6) için gerekir
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python rag/extract.py              # veya: python rag/extract.py --project yonerge
python rag/chunk.py
python rag/embed.py
```
Beklenen: `Sayfa sayısı: 41`, `Atlanan sayfalar: [1, 2, 3, 4]`, `Alınan sayfalar: 37`, `Az metinli sayfalar: []`, `Oluşturulma tarihi: 2025-01-28`.

## Mevcut sınırlamalar
- `pages.json` ham metindir; satır birleştirme ve boşluk temizliği `chunk.py`'de yapılır.
- Paragraf sınırı sezgiseldir: satır `. : ; ! ?` ile bitiyorsa, boş satır, `•` veya `Terim:` ile başlıyorsa yeni blok. Yanlış birleşme yalnızca bölme noktasını etkiler, metin kaybolmaz.

## Repo durumu (17.11.2026)
- Remote: `origin` → `github.com/senasagdc/tkpark-rag` (doğru adres).
- Eski JS denemesi (`src/src/src/`, pdfjs) kaldırıldı.
- `.gitignore`: `.env`, `index/`, `.venv/`, `__pycache__/`, `node_modules/`.
- `.env.example` eklendi; yerel `.env` ondan kopyalandı (anahtar boş).
- API anahtarı hiçbir dosyada yok.
- Kullanılmayan `.vscode/` klasörü silindi.

## Sonraki adım (bugünün hedefi: Document Processing + Embedding Pipeline)
1. ~~1.3 Chunking~~ ✓
2. ~~1.4 Embedding~~ ✓
3. Hızlı deney (1.5): 10 soruyla `search.py`; doğru bölüm ilk 5'te değilse önce chunking'e, sonra modele bakılır.
