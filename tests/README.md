# tests/ — chatbot ne kadar doğru çalışıyor?

Bu klasördeki dosyalar **chatbot'un çalışması için gerekli değil.** Chatbot'un kendisi `rag/` klasöründe.
Buradakiler chatbot'u **ölçmek** için: soruları otomatik sorar, cevapları beklenenle karşılaştırır, sonucu yazar.

> **"eval" ne demek?** *evaluation* = değerlendirme. Projede "eval" geçen her şey bu ölçme işiyle ilgili.
> Kod `tests/` klasöründe, ölçmede kullanılan veriler (sorular, sonuçlar) `projects/<proje>/eval/` klasöründe.

## Hangi dosya ne yapıyor

| Dosya | Ne ölçüyor | LLM'e gidiyor mu | Ne kadar sürer |
|---|---|---|---|
| `retrieval_test.py` | Belgede **arama** doğru bölümü buluyor mu? (Hit@5, MRR) | Hayır, ücretsiz | birkaç saniye |
| `answer_test.py` | Chatbot'un **cevabı** doğru türde mi, doğru kaynağı gösteriyor mu? | Evet (Gemini) | 67 soru ≈ 5–8 dk |
| `report.py` | `answer_test.py` sonucundan **mentora gösterilecek rapor** yazar | Hayır | anında |

Sıra: önce `answer_test.py`, sonra `report.py`. `retrieval_test.py` bağımsız.

## Nasıl çalıştırılır

Proje klasöründen (`tkpark-rag-1`), PowerShell'de:

```powershell
$env:PYTHONUTF8=1
.venv\Scripts\python.exe tests\retrieval_test.py
.venv\Scripts\python.exe tests\answer_test.py
.venv\Scripts\python.exe tests\report.py
```

Birkaç soruyu denemek için: `tests\answer_test.py --only q01,s01`. Sonucu kaydetmeden denemek için: `--no-save`.

## Veriler nerede (`projects/yonerge/eval/`)

| Dosya | İçinde ne var | Kim yazar |
|---|---|---|
| `retrieval.jsonl` | Arama testi soruları + beklenen bölüm | biz (elle) |
| `testset.jsonl` | Cevap testi soruları + beklenen tür (`cevap` / `bilgi_yok` / `sohbet` / `geçersiz`) + beklenen bölüm | biz (elle) |
| `review.jsonl` | Cevapları okuyup yazdığımız notlar ("eksik", "etiket hatası" …) | biz (elle) |
| `results/*.json` | `answer_test.py`'nin her çalıştırmadaki ham sonucu | `answer_test.py` |
| `reports/*.md` | Okunabilir rapor | `report.py` |

## Sonuçları okurken

- **Tür doğruluğu:** soruya doğru türde mi cevap verdi? Örneğin belgede olmayan bir soruya "bilgi yok" dedi mi?
- **Kaynak doğruluğu:** cevabın altında gösterilen bölüm, beklediğimiz bölüm mü?
- **Uydurma şüphesi:** "bilgi yok" demesi gerekirken cevap verdi. Mutlaka elle kontrol et; bazen etiketimiz yanlış çıkıyor (u02, u06).
- **Otomatik ölçüm cevabın metnini okumaz.** Cevabın eksik ya da yanlış olduğunu ancak elle okuyunca anlarız. Bunu `review.jsonl`'a not olarak yazarız, rapor da "inceleme sonrası" sütununda gösterir.

## Etiket koyma kuralı (test setine soru eklerken)

1. Cevabı belgede **ara**. Yalnızca kelimeyi değil konuyu ara: "sigara" kelimesi yok ama "tütün ürünleri" var.
2. Belgede ilgili bir hüküm varsa ama sorulan ayrıntı yoksa soru **`cevap`** olur (kısmi cevap). Örnek: belgede kira var, TL tutarı yok.
3. **`bilgi_yok`** yalnızca belgede bununla ilgili hiçbir şey yoksa konur.
4. `cevap` sorularına `sections` (bölüm numarası) ve `note` (belgedeki cevap) yaz.
