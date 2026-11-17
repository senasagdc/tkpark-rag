# Proje şablonu

1. Bu klasörü `projects/<yeni-id>/` olarak kopyala.
2. `project.json` içinde `id` alanını klasör adıyla aynı yap.
3. Belgeleri `data/` altına koy ve `sources` listesini doldur.
   - `skipPages`: indekse alınmayacak PDF sayfaları (kapak, içindekiler), 1'den başlar.
4. Belgede numaralı başlıklar varsa `chunking.strategy` değerini `"heading"` yap ve `headingPatterns` yaz
   (bkz. `projects/yonerge/project.json`). Başlık yoksa `"fixed"` olarak bırak.
   - `headingPatterns` üst seviyeden alta sıralanır (1. eleman = 1. seviye). Eşleşen kısım bölüm numarasıdır.
   - `maxTokens`: chunk başına en fazla token (başlık yolu dahil), `overlap`: aynı bölümün parçaları arası örtüşme (token).
     Tokenlar embedding modelinin tokenizer'ıyla sayılır (`embedding.model`, istenirse `chunking.tokenizer`).
   - Çalıştır: `python rag/chunk.py` → `index/<id>/chunks.json`
5. `.env` → `PROJECT=<yeni-id>` ve `python rag/extract.py`.
