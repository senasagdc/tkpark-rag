# PROJECT.md — Yeniden Kullanılabilir RAG Chatbot (ilk proje: Teknopark Yönergesi)

## Durum
**Part 1 / Adım 1.2 — Text extraction (Python + PyMuPDF) tasarlandı, ancak `rag/config.py`, `rag/extract.py` ve `requirements.txt` bu makinedeki repoya hiç gelmedi (17.11.2026'da tespit edildi). 1.2b ile birlikte, doğrudan genelleştirilmiş hâliyle yeniden yazılacak.**

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
      "^\\d+\\.\\d+\\.\\d+\\.\\s",
      "^\\d+\\.\\d+\\.\\s",
      "^\\d+\\.\\s",
      "^[a-zçğıöşü]\\.\\s"
    ],
    "bullet": "•",
    "maxChars": 1500,
    "fallback": { "strategy": "fixed", "size": 1000, "overlap": 150 }
  },

  "embedding": { "provider": "gemini", "model": "gemini-embedding-2" },
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
- `minScore` 1.5'teki retrieval testinden sonra ayarlanacak (Part 4'te konu dışı guardrail'i de bunu kullanacak).
- Başlığı olmayan bir belgede `strategy: "fixed"` kullanılır; `heading` stratejisi hiçbir başlık bulamazsa `fallback`'e düşülür.

## `index.json` sözleşmesi
```json
{
  "schemaVersion": 1,
  "project": "yonerge",
  "createdAt": "2026-11-18T10:00:00Z",
  "embedding": { "provider": "gemini", "model": "gemini-embedding-2", "dimensions": 768 },
  "chunks": [
    {
      "id": "yonerge-7.1.5-0",
      "text": "…",
      "vector": [0.012, -0.044, …],
      "metadata": { "source": "data/yonerge.pdf", "section": "7.1.5", "title": "…", "pdfPages": [18, 19] }
    }
  ]
}
```
`dimensions` değeri, 1.4'te modelin döndürdüğü gerçek boyuttan yazılır. `metadata` alanları kaynak türüne göre değişebilir; çekirdek yalnızca `source` alanını zorunlu tutar.

## Sağlayıcı adaptörleri
Her iki tarafta da çekirdek yalnızca şu küçük arayüzleri çağırır:

| Arayüz | Python (`rag/providers/`) | Node (`src/providers/`) |
|---|---|---|
| Embedding | `embed(texts: list[str]) -> list[list[float]]` | `embed(texts) → Promise<number[][]>` |
| LLM | — (Python'da LLM yalnızca değerlendirmede) | `generate(messages, opts) → Promise<string>`, ileride `stream(...)` |

Seçim `project.json` → `"provider": "gemini"` ile yapılır. Yeni bir sağlayıcı eklemek = yeni bir adaptör dosyası + kayıt satırı. Gemini'ye özel parametreler (task type vb.) yalnızca adaptörün içinde kalır.

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
- Dosya: `projects/yonerge/data/yonerge.pdf` (taşınmadan önce: `data/yonerge.pdf`)
- Başlık: YTÜ Yıldız Teknopark Bölge İşletme Yönergesi (bir "yönerge"; Bakanlık yönetmeliği değil)
- 41 PDF sayfası, ~18.000 kelime, Word'den üretilmiş, metin katmanı var → OCR gerekmiyor
- Tarih: Metinde onay/yürürlük tarihi veya sürüm yok. PDF metadata oluşturulma tarihi: 2025-01-28.
- Sayfalarda basılı sayfa numarası yok. İçindekiler'deki numaralar = PDF sayfası − 1.
  Uygulama yalnızca PDF sayfa sırasını kullanır.

**Belge yapısı (→ `project.json` › `chunking`)**
- Numaralı başlıklar: `1.` … `21.`, `7.1.`, `7.1.5.` (en fazla 3 seviye) + `7.2.2` altında `a.` / `b.`
- İçerik çoğunlukla `•` maddeli kurallar ve paragraflar
- Bölüm 3 "Tanım ve Kısaltmalar": `Terim: tanım` listesi
- PDF s. 1 kapak, s. 2–4 İçindekiler → indekse alınmayacak (`skipPages`)
- Tablo tespit edilmedi

## Yol haritası
- **Part 1 — RAG çekirdeği (Python, terminal)**
  - [x] 1.1 PDF incelemesi
  - [ ] 1.2 Text extraction (PyMuPDF) → `index/<id>/pages.json` — dosyalar repoda yok, 1.2b ile birlikte yazılacak
  - [ ] **1.2b Genelleştirme** (1.3'ten önce)
    - `projects/yonerge/` ve `projects/_template/` klasörlerini oluştur, PDF'i taşı, `project.json` yaz
    - `rag/config.py`: `PROJECT` → `project.json` okuma + doğrulama (eksik alan varsa açık hata)
    - `rag/extract.py`: belge yolu ve `skipPages` config'ten gelsin; PDF okuma `rag/loaders/pdf.py`'de; çıktı `index/<id>/pages.json`
    - `requirements.txt` (`pymupdf`)
    - Kontrol: kodda `grep -ri "yonerge\|teknopark" rag/` sonuç vermemeli
  - [ ] 1.3 Chunking (`heading` + `fixed` stratejileri, kalıplar config'ten) → `index/<id>/chunks.json`
  - [ ] 1.4 Embeddings (adaptör üzerinden) → `index/<id>/index.json`
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
| Embedding | Gemini `gemini-embedding-2` (adaptör: `gemini`) |
| LLM | Gemini `gemini-3.5-flash-lite` (adaptör: `gemini`) |
| SDK | Python: `google-genai`, Node: `@google/genai` (yalnızca adaptör dosyalarında) |
| Vector store | Yerel JSON + cosine similarity (proje başına bir `index.json`) |
| Proje ayarları | `projects/<id>/project.json` (Python ve Node ortak) |
| Web (Part 2–3) | Node.js 22+, Express 5, HTML/CSS/vanilla JS |

Not: Yerel JSON birkaç bin chunk'a kadar yeterli. Daha büyük projelerde vektör DB adaptörü (Chroma, Qdrant, pgvector) eklenebilir. Sözleşme `index.json` olduğu için bu değişiklik Node tarafında yalnızca `retrieval.js`'i etkiler.

## Dosyalar
- `.env.example` — ortam değişkenleri şablonu (`PORT`, `PROJECT`, `GEMINI_API_KEY`); `.env` git'e girmez
- `data/yonerge.pdf` — kaynak belge (1.2b'de `projects/yonerge/data/`'ya taşınacak)
- `package.json` — Node tarafı (Part 2'de doldurulacak)

## Nasıl çalıştırılır
```bash
cp .env.example .env               # GEMINI_API_KEY'i 1.4'te doldur
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PROJECT=yonerge python rag/extract.py
```
Beklenen: `Sayfa sayısı: 41`, `Az metinli sayfalar: [1]`, `PDF oluşturulma tarihi: 2025-01-28`.

## Mevcut sınırlamalar
- Satırlar PDF satır sonlarıyla bölünmüş; birleştirme chunking adımında yapılacak.
- Sayfa başlarında boş satırlar ve fazladan boşluklar olabiliyor (temizlik chunking'de).

## Repo durumu (17.11.2026)
- Remote: `origin` → `github.com/senasagdc/tkpark-rag` (doğru adres).
- Eski JS denemesi (`src/src/src/`, pdfjs) kaldırıldı.
- `.gitignore`: `.env`, `index/`, `.venv/`, `__pycache__/`, `node_modules/`.
- `.env.example` eklendi; yerel `.env` ondan kopyalandı (anahtar boş).
- API anahtarı hiçbir dosyada yok.

## Sonraki adım
1. **1.2 + 1.2b birlikte:** proje paketi yapısı (`projects/yonerge/`, `_template/`), `rag/config.py`, `rag/loaders/pdf.py`, `rag/extract.py`, `requirements.txt` → `PROJECT=yonerge python rag/extract.py` ile doğrula → commit.
2. 1.3 Chunking: `project.json` › `chunking` ayarlarıyla başlık bazlı bölümleme, uzun bölümleri `bullet` sınırlarından bölme,
   her chunk'a `source`, `section`, `title`, `pdfPages` metadata'sı ekleme. Kalıplar kodda değil config'te.
