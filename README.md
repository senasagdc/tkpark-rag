#  Yönerge RAG Asistanı

Staj birinci hafta notlarım: https://wholesale-raptorex-e7c.notion.site/STAJ-Hafta-1-41ab21c0f4d4800989ecee22ddcc9f9f

Teknopark Bölge İşletme Yönergesi için RAG tabanlı soru-cevap asistanı. Ayrıntılar için [PROJECT.md](PROJECT.md).

## Nerede kaldım

- [x] PDF'ten metin çıkarma
- [x] Temizlik + chunking
- [x] Embedding
- [ ] Retrieval testi (sıradaki)
- [ ] LLM ile cevap üretme
- [ ] Değerlendirme

`PDF → pages.json → chunks.json → index.json`

## 1. Metin hazırlığı

- PDF'i PyMuPDF ile okudum. Kapak ve içindekiler sayfalarını atladım, geriye 37 sayfa kaldı.
- **Başlıklar:** regex ile 96 başlık buldum (`1.`, `7.1.`, `7.1.5.`, `a.`).
- **Sayfalar:** her parçada geldiği sayfa numarası kayıtlı.
- **Tablolar:** belgenin içeriğinde tablo yok, sadece içindekiler sayfalarında var (onları zaten atladım).
- **Normalize:** fazla boşlukları sildim ve PDF'in böldüğü satırları birleştirdim. Küçük harfe çevirmedim.
- **Label:** her parça kendi başlık yoluyla başlıyor (ör. `7. … > 7.1. … > 7.1.5. …`).
- **Metadata:** LangChain değil, kendi kodum oluşturuyor (`source`, `section`, `title`, `path`, `pages`).

## 2. Chunking

- Önce metni başlıklara göre böldüm. Bir parça iki farklı bölümü karıştırmıyor.
- Uzun bölümleri LangChain `RecursiveCharacterTextSplitter` ile böldüm.
- Token sayımında `multilingual-e5-small` modelinin tokenizer'ını kullandım. Modelin sınırı **512 token**.
- Bir parça en fazla **300 token** olabiliyor. Sonuçta 186 parça çıktı.
- **Neden token?** Model token sayıyor ve 512'yi aşan kısmı hata vermeden kesiyor. Türkçede karakter sayısı token sayısını tutmuyor, o yüzden karakterle bölseydim bazı parçaların sonu kesilebilirdi.
- **Overlap:** 50 token (~%17). Sadece bölünen bölümlerin parçaları arasında var.

## 3. Embedding

- Model olarak `intfloat/multilingual-e5-small` kullandım. Türkçe destekliyor, ücretsiz ve bilgisayarda yerel çalışıyor.
- Her vektör 384 boyutlu ve normalize.
- E5 modelinin istediği önekleri ekledim: parçalara `passage:`, sorulara `query:`.
- Kaydetmeden önce şunları kontrol ediyorum: vektör sayısı, boyut, normalizasyon ve 512 token sınırı.
- 3 soruyla küçük bir deneme yaptım. 2'sinde doğru bölüm geldi, 1'inde gelmedi.

## 4. Vektör veritabanı

- Henüz bir vektör veritabanı kullanmıyorum. Vektörleri `index.json` dosyasında tutuyorum.
- 186 parça için bu yeterli. Proje büyürse Chroma veya Qdrant ekleyebilirim.
- Arama kısmını (`search.py`) sıradaki adımda yazacağım.

## Çalıştırma

```bash
pip install -r requirements.txt
python rag/extract.py
python rag/chunk.py
python rag/embed.py
```
