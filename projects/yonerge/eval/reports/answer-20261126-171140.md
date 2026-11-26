# Cevap değerlendirme raporu — yonerge

- **Çalıştırma:** 2026-11-26T17:11:40 · `projects/yonerge/eval/results/answer-20261126-171140.json`
- **Test seti:** `eval/testset.jsonl`, 67 soru
- **Ayarlar:** model `gemini-3.5-flash-lite`, temperature 0.1, topK 5, embedding `intfloat/multilingual-e5-base`, system prompt `74d8d20f1669`
- **Akış:** girdi kontrolü → retrieval (FAISS, ilk topK parça) → tek LLM çağrısı (JSON şeması: `cevap` / `bilgi_yok` / `sohbet` + kullanılan parça numaraları) → kaynaklar backend'de

## Özet

| Ölçüm | Sonuç |
|---|---|
| Tür doğruluğu (otomatik) | 66/67 (99%) |
| Tür doğruluğu (elle inceleme sonrası) | 66/67 (99%) |
| Kaynak doğruluğu (beklenen bölüm gösterilen kaynaklarda) | 30/31 (97%) |
| Uydurma şüphesi (bilgi_yok beklenirken cevap verdi) | otomatik: u06 · incelemede doğrulanan: u06 |
| Fazla temkin (cevap beklenirken bilgi_yok dedi) | otomatik: yok · incelemede doğrulanan: yok |
| Eksik / yanlış cevap (elle inceleme) | q01 |
| LLM hatası (cevap verilemedi) | yok |
| Geçici API hatası, tekrar deneme | 429: 3, 503: 18 |
| Gecikme (retrieval + LLM, bekleme hariç) | ort 3440 ms · medyan 2668 · p90 6671 · en fazla 11660 (60 çağrı) |

## Tür başına

| Beklenen tür | Soru | Doğru (otomatik) | Doğru (inceleme sonrası) |
|---|---|---|---|
| geçersiz | 7 | 7 | 7 |
| cevap | 31 | 31 | 31 |
| bilgi_yok | 22 | 21 | 21 |
| sohbet | 7 | 7 | 7 |

## Karışıklık tablosu

Satır = beklenen, sütun = çıkan.

| beklenen \ çıkan | geçersiz | cevap | bilgi_yok | sohbet |
|---|---|---|---|---|
| geçersiz | 7 | 0 | 0 | 0 |
| cevap | 0 | 31 | 0 | 0 |
| bilgi_yok | 0 | 1 | 21 | 0 |
| sohbet | 0 | 0 | 0 | 7 |

## İncelenen / dikkat gereken sorular

### q01 — Firma kabul şartları nelerdir?

- **Beklenen → çıkan:** `cevap` → `cevap` (otomatik ✓, inceleme sonrası ✓)
- **Cevap:** Yönetici Şirket tarafından talep edilmesi durumunda girişimcilerin Bölgede yer alabilmesi ve bedelleri karşılayabilmesi için uyması gereken şartlar şunlardır: • Findeks raporunun (borç ödeme kabiliyeti ve düzenliliğinin tespiti) sunulması, • Resmi kurumlardan (Maliye, SGK, Belediye vb.) borç yoktur belgesinin sunulması. Belgeleri zamanında beyan etmeyen veya eksik evrak sunan girişimcilerin sözle…
- **Gösterilen kaynaklar:** 10.1 (s. 27)
- **LLM'e giden parçalar:** yonerge-7.1.3-2 (0.827), yonerge-7.2.1-8 (0.826), yonerge-10.1-2 (0.825), yonerge-12-0 (0.822), yonerge-12.2-0 (0.822)
- **İnceleme:** Cevap doğru ama eksik. 10.1 bölümü 3 parçaya bölünmüş (10.1-0 online başvuru, 10.1-1 komisyon kabulü, 10.1-2 findeks/borç belgesi); LLM'e yalnızca 10.1-2 gitti (3. sırada). LLM cevabı tam liste gibi sundu ('şartlar şunlardır'). Kaynak kontrolü bunu yakalamıyor çünkü bölüm doğru. Çözüm adayları: reranking, aynı bölümün diğer parçalarını eklemek.

### u06 — Ofiste sigara içmek serbest mi?

- **Beklenen → çıkan:** `bilgi_yok` → `cevap` (otomatik ✗, inceleme sonrası ✗)
- **Cevap:** Girişimci personeli, kendi alanı veya bu amaçla ayrılmış alanlar dışındaki ortak alanlarda Tütün Ürünlerinin Zararlarının Önlenmesi ve Kontrolü Hakkında Kanun ile getirilen kısıtlamalara tabi olacaktır.
- **Gösterilen kaynaklar:** 7.1.6 (s. 16, 17), 7.1.7 (s. 17, 18)
- **LLM'e giden parçalar:** yonerge-17-8 (0.815), yonerge-15.4-0 (0.804), yonerge-7.1.6-4 (0.800), yonerge-7.1.7-0 (0.799), yonerge-17-4 (0.797)

## Retrieval: beklenen bölüm LLM'e giden parçaların kaçıncısı

| Soru | Beklenen | Sıra | 1. parçanın puanı |
|---|---|---|---|
| q01 | 10.1 | 3 | 0.827 |
| q02 | 7.1.7 | 1 | 0.804 |
| q03 | 7.2.1 | 1 | 0.819 |
| q04 | 7.1.4 | 1 | 0.858 |
| q05 | 7.1.10 | 2 | 0.841 |
| q06 | 7.1.8 | 1 | 0.845 |
| q07 | 13.1 | 1 | 0.860 |
| q08 | 11.2 | 3 | 0.850 |
| q09 | 15.5 | 1 | 0.830 |
| q10 | 16.1, 16.3 | 1 | 0.848 |
| q11 | 1 | 1 | 0.821 |
| q12 | 2 | 1 | 0.848 |
| q13 | 3 | 4 | 0.836 |
| q14 | 4 | 1 | 0.821 |
| q15 | 5.4 | 1 | 0.883 |
| q16 | 6.1, 6.4 | 1 | 0.842 |
| q17 | 8.3.2 | 1 | 0.856 |
| q18 | 9 | 1 | 0.834 |
| q19 | 12.3 | 1 | 0.889 |
| q20 | 14 | 1 | 0.869 |
| q21 | 17, 18 | yok | 0.841 |
| q22 | 18 | 1 | 0.852 |
| q23 | 19 | 1 | 0.866 |
| q24 | 20 | 2 | 0.839 |
| q25 | 21 | 1 | 0.830 |
| u02 | 7.2.1 | 1 | 0.835 |
| z01 | 7.2.1 | 1 | 0.852 |
| z06 | 7.1.4 | 1 | 0.858 |
| z07 | 7.2.1 | 1 | 0.832 |
| z08 | 7.1.10 | 4 | 0.774 |
| z09 | 3, 5.4 | 4 | 0.845 |

Beklenen bölüm 1. sırada: 23/31, ilk 5 içinde: 30/31.

## Gecikme dağılımı

Bekleme (429/503 sonrası tekrar deneme) süresi hariç.

| Aralık | Çağrı |
|---|---|
| < 1 sn | 2 |
| 1–2 sn | 13 |
| 2–4 sn | 30 |
| ≥ 4 sn | 15 |

Toplam bekleme: 132 sn.

## Tüm sonuçlar

| Soru | Beklenen | Çıkan | ms | Kaynak | Cevap |
|---|---|---|---|---|---|
| q01 | cevap | cevap | 3277 | 10.1 | Yönetici Şirket tarafından talep edilmesi durumunda girişimcilerin Bölgede yer alabilmesi ve bedelleri karşılayabilmesi için uyması gereken… |
| q02 | cevap | cevap | 1650 | 7.1.7 | Ortak alanların kullanımına ilişkin kurallar şunlardır: - Girişimciler prototip atölyesinde ortak alanlarda herhangi bir mekanik, elektrik … |
| q03 | cevap | cevap | 2567 | 7.2.1 | Kira veya aidat ödemelerinin gecikmesi durumunda uygulanacak süreçler ve kurallar şunlardır: - Girişimcinin, Yönetici Şirket tarafından bel… |
| q04 | cevap | cevap | 2542 | 7.1.4 | Girişimci, kendisine tahsis edilen alanda gerçekleştireceği tadilat, dekorasyon ve sair her türlü çalışma için Yönetici Şirketin yazılı izn… |
| q05 | cevap | cevap | 1839 | 7.1.10 | Girişimci, kendi isteği ile Bölgeden ayrılmak ister ise bunu en geç 30 (otuz) gün önce Yönetici Şirkete bildirmelidir. |
| q06 | cevap | cevap | 3101 | 7.1.8 | Girişimcinin çalıştırdığı personelin Bölgede fiilen çalışıp çalışmadığı Yönetici Şirket tarafından kurulan dijital sistemlerle (kişiselleşt… |
| q07 | cevap | cevap | 3709 | 13.1 | Aylık muafiyet raporu, takip eden ayın ilk 20 (yirmi) günü içerisinde elektronik imza sistemi ile Yönetici Şirket onayına sunulmalıdır. |
| q08 | cevap | cevap | 1293 | 11.2 | Bölgede faaliyette bulunan girişimcilerin kazançlarının gelir ve kurumlar vergisinden istisna bulunduğu süre içinde ürettikleri sistem yöne… |
| q09 | cevap | cevap | 2131 | 15.5 | Girişimci şu durumlarda kuluçka sürecini tamamlamış (mezun olmuş) sayılır: - Şirket kuruluşundan itibaren 3 seneyi doldurmuşsa, - Proje Değ… |
| q10 | cevap | cevap | 3689 | 16.3 | Üniversite bünyesinde görevli öğretim üyeleri; Teknoloji Geliştirme Bölgeleri Kanunu’nun getirdiği avantajlardan faydalanarak kendi yürüttü… |
| q11 | cevap | cevap | 2941 | 1 | Yıldız Teknoloji Geliştirme Bölgesi Teknopark A.Ş. adına hazırlanmış olan İşletme Yönergesinin amacı; 4691 sayılı Teknoloji Geliştirme Bölg… |
| q12 | cevap | cevap | 3324 | 2 | Bu Yönerge, Bölgede yer alacak girişimciler ve Yönetici Şirketin hak, sorumluluk ve yükümlülüklerini düzenlemektedir. |
| q13 | cevap | cevap | 2033 | 3 | Ön kuluçka süresi en fazla 6 (altı) ay olarak belirlenmiştir. |
| q14 | cevap | cevap | 7636 | 4 | İş bu Yönerge; 4691 sayılı Teknoloji Geliştirme Bölgeleri Kanunu ile Teknoloji Geliştirme Bölgeleri Uygulama Yönetmeliğine göre hazırlanmış… |
| q15 | cevap | cevap | 3152 | 5.4 | Yıldız Teknoloji Geliştirme Bölgesi Teknopark A.Ş. Yönetim Kurulu, Başkan, Başkan Vekili ve üyelerden meydana gelen toplam 7 kişiden oluşur. |
| q16 | cevap | cevap | 6649 | 6.1 | YTÜ Teknoloji Geliştirme Bölgesi üç yerleşkede hizmet vermektedir: • Davutpaşa Yerleşkesi • İkitelli OSB ek alanı • Maslak1453 ek alanı |
| q17 | cevap | cevap | 5107 | 8.3.2 | Girişimci, kendisine tahsis edilen alanın temizliğinden bizzat sorumludur. |
| q18 | cevap | cevap | 1424 | 9 | Bölgedeki tüm binaların yangın ve doğal afetlere karşı sigortasını yaptırmak Yönetici Şirketin yetkisi ve sorumluluğundadır. Girişimciye ta… |
| q19 | cevap | cevap | 1836 | 12.3 | Teknolojik ürün tanımlama belgesi ve yatırım fizibilite raporunun Yönetici Şirkete teslimini takiben oluşturulan Teknolojik Ürün Değerlendi… |
| q20 | cevap | cevap | 2074 | 14 | Girişimci, personel listesini, Ar-Ge projelerindeki görev tanımlarını, nitelik ve çalışma sürelerini içeren listeyi Bölgede faaliyet göster… |
| q21 | cevap | cevap | 2777 | 7.1.6, 7.1.5, 7.1.8 | Yönerge kurallarına uyulmaması durumunda karşılaşılabilecek bazı yaptırımlar ve yükümlülükler şunlardır: • Girişimci, Bölge ve bilgi güvenl… |
| q22 | cevap | cevap | 2408 | 18 | Bölgede yer alan işletmelerde çalışan Ar-Ge ve tasarım personelinden yüksek lisans yapanlar, bir buçuk yılı geçmemek üzere Bölge dışında sü… |
| q23 | cevap | cevap | 2082 | 19 | Bakanlık portal bilgi girişlerindeki eksik ve yanlış bilgilerden ile mevcut bilgilerin kontrolünden doğrudan Girişimciler sorumludur. Herha… |
| q24 | cevap | cevap | 6869 | 20 | Bakanlık, Yönetici Şirketin ve girişimcilerin faaliyet ve uygulamalarını gerekli gördüğü durumlarda denetler ve gerektiğinde ilgili kurum v… |
| q25 | cevap | cevap | 11660 | 21 | Bu yönerge, Yıldız Teknoloji Geliştirme Bölgesi Teknopark A.Ş. tarafından gerekli görülen durumlarda güncellenecek ve Sanayi ve Teknoloji B… |
| x01 | bilgi_yok | bilgi_yok | 7180 |  |  |
| x02 | bilgi_yok | bilgi_yok | 1189 |  |  |
| x03 | bilgi_yok | bilgi_yok | 2019 |  |  |
| u01 | bilgi_yok | bilgi_yok | 1774 |  |  |
| u02 | cevap | cevap | 3454 | 7.2.1 | Ofis alanına ilişkin kira/kullanım bedelleri Yönetici Şirket Yönetim Kurulu tarafından her yıl belirlenmektedir. Ancak metrekare başına kaç… |
| u03 | bilgi_yok | bilgi_yok | 944 |  |  |
| k04 | bilgi_yok | bilgi_yok | 2553 |  |  |
| k05 | bilgi_yok | bilgi_yok | 6465 |  |  |
| k06 | bilgi_yok | bilgi_yok | 2729 |  |  |
| s01 | sohbet | sohbet | 4659 |  | Merhaba! YTÜ Yıldız Teknopark Bölge İşletme Yönergesi hakkında size nasıl yardımcı olabilirim? |
| s02 | sohbet | sohbet | 2723 |  | Rica ederim, yardımcı olabildigim için sevindim. YTÜ Yıldız Teknopark Bölge İşletme Yönergesi hakkında başka sorularınız olursa sormaktan ç… |
| s03 | sohbet | sohbet | 1976 |  | Ben Yıldız Teknopark Bölge İşletme Yönergesi hakkında sorularınızı yanıtlamak için buradayım. Yönergeyle ilgili her türlü sorunuzu bana sor… |
| s04 | sohbet | sohbet | 1780 |  | Bana YTÜ Yıldız Teknopark Bölge İşletme Yönergesi hakkında sorular sorabilirsiniz. Girişimciler, faaliyetler, tanımlar ve iş birlikleri gib… |
| g01 | geçersiz | geçersiz | 0 |  |  |
| g02 | geçersiz | geçersiz | 0 |  |  |
| g03 | geçersiz | geçersiz | 0 |  |  |
| g04 | geçersiz | geçersiz | 0 |  |  |
| z01 | cevap | cevap | 2226 | 7.2.1 | Girişimci, kullanım veya kira bedeli ile işletme gideri ödemelerini faturalarda belirtilen günde, bildirimi takip eden 10 (on) iş günü için… |
| z02 | bilgi_yok | bilgi_yok | 3578 |  |  |
| z03 | bilgi_yok | bilgi_yok | 4625 |  |  |
| z04 | bilgi_yok | bilgi_yok | 2180 |  |  |
| z05 | bilgi_yok | bilgi_yok | 4521 |  |  |
| x04 | bilgi_yok | bilgi_yok | 6244 |  |  |
| x05 | bilgi_yok | bilgi_yok | 787 |  |  |
| x06 | bilgi_yok | bilgi_yok | 1583 |  |  |
| u04 | bilgi_yok | bilgi_yok | 5667 |  |  |
| u05 | bilgi_yok | bilgi_yok | 2612 |  |  |
| u06 | bilgi_yok | cevap ✗ | 1129 | 7.1.6, 7.1.7 | Girişimci personeli, kendi alanı veya bu amaçla ayrılmış alanlar dışındaki ortak alanlarda Tütün Ürünlerinin Zararlarının Önlenmesi ve Kont… |
| k07 | bilgi_yok | bilgi_yok | 2548 |  |  |
| k08 | bilgi_yok | bilgi_yok | 3555 |  |  |
| k09 | bilgi_yok | bilgi_yok | 11075 |  |  |
| s05 | sohbet | sohbet | 1126 |  | Günaydın! YTÜ Yıldız Teknopark Bölge İşletme Yönergesi hakkında bana her zaman soru sorabilirsiniz. |
| s06 | sohbet | sohbet | 5657 |  | İyiyim, teşekkür ederim. Size Yıldız Teknopark Bölge İşletme Yönergesi hakkında nasıl yardımcı olabilirim? |
| s07 | sohbet | sohbet | 3144 |  | Görüşmek üzere! Yıldız Teknopark Bölge İşletme Yönergesi hakkında her zaman soru sorabilirsiniz. |
| g05 | geçersiz | geçersiz | 0 |  |  |
| g06 | geçersiz | geçersiz | 0 |  |  |
| g07 | geçersiz | geçersiz | 0 |  |  |
| z06 | cevap | cevap | 3257 | 7.1.4 | Evet, girişimci kendisine tahsis edilen alanda gerçekleştireceği tadilat, dekorasyon ve sair her türlü çalışma için Yönetici Şirketin yazıl… |
| z07 | cevap | cevap | 2278 | 7.2.1 | Kira ödemelerinin veya diğer ödemelerin gecikmesi durumunda uygulanacak işlemler şunlardır: - Kullanım/kira bedeli ile işletme gideri ödeme… |
| z08 | cevap | cevap | 2046 | 7.1.10 | Girişimci, kendi isteği ile Bölgeden ayrılmak ister ise bunu en geç 30 (otuz) gün önce Yönetici Şirkete bildirmelidir. |
| z09 | cevap | cevap | 8025 | 3 | Ön kuluçka, iş fikri veya projesi olan henüz şirketleşmemiş girişimci grubuna en fazla 6 (altı) ay süre ile hizmet süreçlerini içeren yapıl… |
| z10 | bilgi_yok | bilgi_yok | 1302 |  |  |

---
Rapor `rag/analyze.py` ile üretildi. Otomatik ölçümler cevap metninin doğruluğunu ölçmez; elle inceleme notları `eval/review.jsonl` dosyasından gelir.
