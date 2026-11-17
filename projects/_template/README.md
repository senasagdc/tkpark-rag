# Proje şablonu

1. Bu klasörü `projects/<yeni-id>/` olarak kopyala.
2. `project.json` içinde `id` alanını klasör adıyla aynı yap.
3. Belgeleri `data/` altına koy ve `sources` listesini doldur.
   - `skipPages`: indekse alınmayacak PDF sayfaları (kapak, içindekiler), 1'den başlar.
4. Belgede numaralı başlıklar varsa `chunking.strategy` değerini `"heading"` yap ve `headingPatterns` yaz
   (bkz. `projects/yonerge/project.json`). Başlık yoksa `"fixed"` olarak bırak.
5. `.env` → `PROJECT=<yeni-id>` ve `python rag/extract.py`.
