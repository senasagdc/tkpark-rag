#  Yönerge RAG Asistanı

Staj birinci hafta notlarım: https://wholesale-raptorex-e7c.notion.site/STAJ-Hafta-1-41ab21c0f4d4800989ecee22ddcc9f9f

Teknopark Bölge İşletme Yönergesi için RAG tabanlı soru-cevap asistanı. Sistem yeniden kullanılabilir: kod genel, belgeye özel her şey `projects/<proje-id>/` klasöründe. Ayrıntılar için [PROJECT.md](PROJECT.md).

## Nerede kaldım

- [x] 1 PDF'ten metin çıkarma + metadata
- [x] 2 Chunking
- [x] 3 Embedding
- [x] 4 Vektör veritabanı (FAISS)
- [ ] 5 Query processing (ayrı routing kaldırıldı; girdi kontrolü var, rewriting / multi-query sonra)
- [x] 6 Query embedding
- [ ] 7 Retrieval (deney tamam, reranking'den önce test tekrarlanacak)
- [ ] 8 Reranking
- [ ] 9 Prompt oluşturma (yazıldı, LLM testi bekliyor)
- [ ] LLM ile cevap üretme + kaynak gösterme (yazıldı, LLM testi bekliyor)
- [ ] Değerlendirme

`PDF → pages.json → chunks.json → index.json + faiss.index`

## 1. Metin hazırlığı

- PDF'i PyMuPDF ile okudum. Kapak ve içindekiler sayfalarını atladım, geriye 37 sayfa kaldı.
- **Başlıklar:** regex ile 96 başlık buldum (`1.`, `7.1.`, `7.1.5.`, `a.`). Kalıplar kodda değil, `project.json`'da.
- **Sayfalar:** her parçada geldiği sayfa numarası kayıtlı.
- **Tablolar:** belgenin içeriğinde tablo yok, sadece içindekiler sayfalarında var (onları zaten atladım).
- **Normalize:** fazla boşlukları sildim ve PDF'in böldüğü satırları birleştirdim. Küçük harfe çevirmedim.
- **Label:** her parça kendi başlık yoluyla başlıyor (ör. `7. … > 7.1. … > 7.1.5. …`).
- **Metadata:** LangChain değil, kendi kodum oluşturuyor (`source`, `section`, `title`, `path`, `pages`).
- **Farklı dosya türleri:** okuma `rag/loaders/` altında. Şu an sadece PDF var; Word veya HTML gelirse yeni bir loader eklenir.

## 2. Chunking

- Önce metni başlıklara göre böldüm. Bir parça iki farklı bölümü karıştırmıyor.
- Uzun bölümleri LangChain `RecursiveCharacterTextSplitter` ile böldüm.
- Token sayımında embedding modelinin tokenizer'ını kullanıyorum. Modelin sınırı **512 token**.
- Bir parça en fazla **300 token** olabiliyor. Sonuçta 186 parça çıktı.
- **Neden token?** Model token sayıyor ve 512'yi aşan kısmı hata vermeden kesiyor. Türkçede karakter sayısı token sayısını tutmuyor, o yüzden karakterle bölseydim bazı parçaların sonu kesilebilirdi.
- **Overlap:** 50 token (~%17). Sadece bölünen bölümlerin parçaları arasında var.
- Başlığı olmayan bir belgede sabit boyutlu bölmeye (`fixed`) geçiliyor. Her proje kendi bölme ayarını `project.json`'da seçiyor.

## 3. Embedding

- İlk denemede `multilingual-e5-small` (384 boyut) kullandım. "Firma kabul şartları" sorusunda doğru bölüm ilk 3'e girmedi.
- `intfloat/multilingual-e5-base`'e geçtim (768 boyut). Aynı soruda doğru bölüm ilk 3'e girdi. Türkçe destekliyor, ücretsiz ve bilgisayarda yerel çalışıyor.
- İki model aynı tokenizer'ı kullandığı için chunk'lar değişmedi.
- E5 modelinin istediği önekleri ekledim: parçalara `passage:`, sorulara `query:`. Önekler `project.json`'da.
- Embedding adaptörünü (`rag/providers/`) kaldırdım. Tek bir uygulaması vardı; model artık `project.json`'da tek satırla değişiyor.
- Kaydetmeden önce şunları kontrol ediyorum: vektör sayısı, boyut, normalizasyon ve 512 token sınırı.

## 4. Vektör veritabanı

- FAISS `IndexFlatIP` kullanıyorum (kesin arama). Vektörler `faiss.index`'te, metin ve metadata `index.json`'da.
- HNSW'yi de denedim. 186 vektörde düz arama ~10 kat daha hızlı (22 µs ve 208 µs), ayar gerektirmiyor ve hiçbir sonucu kaçırmıyor.
- Proje on binlerce vektöre büyürse HNSW'ye geçilebilir.

## 5. Query processing

- **İlk deneme (24.11):** soruları retrieval'dan önce ayrı bir Gemini çağrısıyla `belge` / `sohbet` / `konu_dışı` diye ayıran bir routing yazdım. Konu dışı soruları retrieval puanıyla elemeyi değerlendirmiştim ama 7. adımdaki testte konu dışı ve cevaplı sorular arasındaki fark yalnızca 0.02 çıktı. Routing test setinde 32/32 aldı.
- **Değişiklik (26.11, mentor önerisi):** ayrı routing'i kaldırdım. Routing, belgenin kapsamını tek bir cümleyle anlatmaya dayanıyordu; çok belgede bu ölçeklenmez. Artık her geçerli soru retrieval'a giriyor ve sohbet / konu dışı / "bilgim yok" kararını cevabı üreten LLM, kendisine verilen parçalara bakarak veriyor (9. adım). Soru başına tek LLM çağrısı kaldı.
- Kalan tek kural **girdi kontrolü**: boş, çok kısa, çok uzun veya harfsiz mesaj LLM'e gitmiyor.
- Query rewriting ve multi-query'yi reranking'den sonra ölçerek değerlendireceğim.

## 6–7. Query embedding ve retrieval

- Soru aynı modelle, `query:` önekiyle embed ediliyor ve ilk 5 sonuç alınıyor.
- 10 cevaplı soruluk test setinde:

  | Metrik | Sonuç |
  |---|---|
  | Hit@1 | 7/10 |
  | Hit@3 | 10/10 |
  | Hit@5 | 10/10 |
  | MRR | 0.817 |

- İlk sonuçların puanları birbirine çok yakın. Sıradaki adımda reranking ile Hit@1'i artırmayı deneyeceğim.

## Çalıştırma

```bash
cp .env.example .env               # GEMINI_API_KEY cevap üretmek için gerekli
pip install -r requirements.txt
python rag/extract.py              # PDF → pages.json
python rag/chunk.py                # → chunks.json
python rag/embed.py                # → index.json + faiss.index
python rag/search.py "Ortak alanlar nasıl kullanılır?"
python rag/search.py --eval        # retrieval test seti
python rag/answer.py "Firma kabul şartları nelerdir?"   # cevap + kaynaklar
python rag/answer.py "Merhaba" --dry-run                 # LLM'e gitmeden prompt'u göster
python rag/answer.py --eval        # cevap test seti (eval/testset.jsonl)
```

Not: Gemini ücretsiz planı dakikada 15 istekle sınırlı, `answer.py --eval` bu yüzden yavaş çalışabilir.
