# Cevap değerlendirme raporu — yonerge

- **Çalıştırma:** 2026-11-27T15:37:18 · `projects/yonerge/eval/results/answer-20261127-153718.json`
- **Test seti:** `eval/testset.jsonl`, 67 soru
- **Ayarlar:** model `gemini-3.5-flash-lite`, temperature 0.1, topK 5, embedding `intfloat/multilingual-e5-base`, system prompt `74d8d20f1669`
- **Akış:** girdi kontrolü → retrieval (PostgreSQL + pgvector, ilk topK parça) → tek LLM çağrısı (JSON şeması: `cevap` / `bilgi_yok` / `sohbet` + kullanılan parça numaraları) → kaynaklar backend'de

## Özet

| Ölçüm | Sonuç |
|---|---|
| Tür doğruluğu (otomatik) | 67/67 (100%) |
| Tür doğruluğu (elle inceleme sonrası) | 67/67 (100%) — etiket hatası: u06 |
| Kaynak doğruluğu (beklenen bölüm gösterilen kaynaklarda) | 31/32 (97%) |
| Uydurma şüphesi (bilgi_yok beklenirken cevap verdi) | otomatik: yok · incelemede doğrulanan: yok |
| Fazla temkin (cevap beklenirken bilgi_yok dedi) | otomatik: yok · incelemede doğrulanan: yok |
| Eksik / yanlış cevap (elle inceleme) | q01, q21, z09 |
| LLM hatası (cevap verilemedi) | yok |
| Geçici API hatası, tekrar deneme | 429: 4 |
| Gecikme (retrieval + LLM, bekleme hariç) | ort 963 ms · medyan 907 · p90 1136 · en fazla 1637 (60 çağrı) |

## Önceki çalıştırmayla karşılaştırma

Önceki: 2026-11-26T17:11:40, system prompt `74d8d20f1669`

| Ölçüm | Önceki | Bu |
|---|---|---|
| Tür doğruluğu (otomatik) | 66/67 (99%) | 67/67 (100%) |
| Kaynak doğruluğu | 30/31 (97%) | 31/32 (97%) |
| Ortalama gecikme | 3440 ms | 963 ms |

Türü değişen soru yok.

## Tür başına

| Beklenen tür | Soru | Doğru (otomatik) | Doğru (inceleme sonrası) |
|---|---|---|---|
| geçersiz | 7 | 7 | 7 |
| cevap | 32 | 32 | 32 |
| bilgi_yok | 21 | 21 | 21 |
| sohbet | 7 | 7 | 7 |

## Karışıklık tablosu

Satır = beklenen, sütun = çıkan.

| beklenen \ çıkan | geçersiz | cevap | bilgi_yok | sohbet |
|---|---|---|---|---|
| geçersiz | 7 | 0 | 0 | 0 |
| cevap | 0 | 32 | 0 | 0 |
| bilgi_yok | 0 | 0 | 21 | 0 |
| sohbet | 0 | 0 | 0 | 7 |

## İncelenen / dikkat gereken sorular

### q01 — Firma kabul şartları nelerdir?

- **Beklenen → çıkan:** `cevap` → `cevap` (otomatik ✓, inceleme sonrası ✓)
- **Cevap:** Yönetici Şirket tarafından talep edilmesi durumunda girişimcilerin uyması gereken koşullar şunlardır: • Bölgede yer alabilmeye ve bedelleri karşılayabilmeye dair findeks raporunun (borç ödeme kabiliyeti ve düzenliliğinin tespiti) sunulması, • Resmi kurumlardan (Maliye, SGK, Belediye vb.) borç yoktur belgesinin ilgili birime/departmana sunulması gerekmektedir. Belgeleri zamanında beyan etmeyen ya …
- **Gösterilen kaynaklar:** 10.1 (s. 27)
- **LLM'e giden parçalar:** yonerge-7.1.3-2 (0.827), yonerge-7.2.1-8 (0.826), yonerge-10.1-2 (0.825), yonerge-12-0 (0.822), yonerge-12.2-0 (0.822)
- **İnceleme:** Cevap doğru ama eksik. 10.1 bölümü 3 parçaya bölünmüş (10.1-0 online başvuru, 10.1-1 komisyon kabulü, 10.1-2 findeks/borç belgesi); LLM'e yalnızca 10.1-2 gitti (3. sırada). LLM cevabı tam liste gibi sundu ('şartlar şunlardır'). Kaynak kontrolü bunu yakalamıyor çünkü bölüm doğru. Çözüm adayları: reranking, aynı bölümün diğer parçalarını eklemek.

### q21 — Yönerge kurallarına uymazsam ne olur?

- **Beklenen → çıkan:** `cevap` → `cevap` (otomatik ✓, inceleme sonrası ✓)
- **Cevap:** Yönerge kurallarına uymadığınızda veya aykırı faaliyette bulunduğunuzda karşılaşılabilecek bazı durumlar ve yaptırımlar şunlardır: - Dijital güvenlik kurallarına itiraz veya muhalefet edilmesinden doğan tüm zararları karşılamakla mükellefsiniz; bu kurala aykırı faaliyetin sürdürülmesi durumunda Yönetici Şirket yaptırım hakkını saklı tutar. - Ofis alanlarında bulundurulması gereken yanıcı, yakıcı,…
- **Gösterilen kaynaklar:** 7.1.5 (s. 16), 7.1.8 (s. 18, 19)
- **LLM'e giden parçalar:** yonerge-7.1.5-3 (0.841), yonerge-7.1.6-5 (0.838), yonerge-7.1.5-16 (0.837), yonerge-7.1.5-4 (0.832), yonerge-7.1.8-3 (0.832)
- **İnceleme:** Eksik. Asıl cevap 17. bölümde (3–30 gün süre verilir, giderilmezse Aykırı Faaliyet Tespit ve Uygulama Kurulu; uyarı, maddi yaptırım, fesih, ihraç) ama 17 ve 18 LLM'e giden parçalarda yok (hepsi 7.1.x). LLM 7.1.5/7.1.6/7.1.8'deki dağınık yaptırımlardan cevap kurdu ve 'diğer sonuçlar belirtilmemiş' diye not düştü; uydurma yok. Kaynak ölçümündeki tek ✗ bu. Çözüm adayları: reranking, query rewriting.

### u06 — Ofiste sigara içmek serbest mi?

- **Beklenen → çıkan:** `cevap` → `cevap` (otomatik ✓, inceleme sonrası ✓)
- **Cevap:** Girişimci personeli, kendi alanı veya bu amaçla ayrılmış alanlar dışındaki ortak alanlarda Tütün Ürünlerinin Zararlarının Önlenmesi ve Kontrolü Hakkında Kanun ile getirilen kısıtlamalara tabidir. Uymayanlar konusunda alınacak cezalardan personel ve çalışmakta olduğu girişimci şirket sorumludur.
- **Gösterilen kaynaklar:** 7.1.6 (s. 16, 17), 7.1.7 (s. 17, 18)
- **LLM'e giden parçalar:** yonerge-17-8 (0.815), yonerge-15.4-0 (0.804), yonerge-7.1.6-4 (0.800), yonerge-7.1.7-0 (0.799), yonerge-17-4 (0.797)
- **İnceleme:** Etiket hatası (test setinde düzeltildi). Belgede 'sigara' kelimesi geçmiyor ama 7.1.6 ve 7.1.7 ortak alanlarda Tütün Ürünlerinin Zararlarının Önlenmesi Kanunu kısıtlamalarına uyulacağını söylüyor. LLM'in cevabı belgeyle birebir aynı; uydurma yok. Etiket konu değil kelime aranarak konmuştu.

### z09 — Ön kuluçka en fazla kaç ay sürer ve yönetim kurulu kaç kişidir?

- **Beklenen → çıkan:** `cevap` → `cevap` (otomatik ✓, inceleme sonrası ✓)
- **Cevap:** Ön kuluçka, iş fikri ya da projesi olan henüz şirketleşmemiş Girişimci grubuna en fazla 6 (altı) ay süre ile danışmanlık, mentörlük ve proje fikri doğrulamaya yönelik hizmet süreçlerini içeren yapıları ifade eder. Yönetim kurulunun kaç kişi olduğu bilgisi belgede bulunmamaktadır.
- **Gösterilen kaynaklar:** 3 (s. 5)
- **LLM'e giden parçalar:** yonerge-15.5-0 (0.845), yonerge-15.1-0 (0.845), yonerge-15.2-0 (0.843), yonerge-3-6 (0.830), yonerge-15.5-1 (0.827)
- **İnceleme:** Yarısı yanlış. Mesajda iki soru var (ön kuluçka süresi, yönetim kurulu sayısı). Retrieval'ın getirdiği 5 parçanın hepsi kuluçka ile ilgili (15.x ve 3-6); 5.4 gelmedi. LLM ön kuluçkayı doğru cevapladı (6 ay), ama 'yönetim kurulu sayısı hakkında belgede bilgi yok' dedi; belgede var (5.4: 7 kişi). Uydurma değil, LLM yalnızca kendisine verilen parçalara göre konuştu; ancak kullanıcıya yanlış bilgi gitti. Otomatik ölçüm ✓ sayıyor çünkü tür ve bölüm 3 doğru. Çözüm adayları: çok parçalı soruyu bölme (multi-query), reranking.

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
| u06 | 7.1.6, 7.1.7 | 3 | 0.815 |
| z06 | 7.1.4 | 1 | 0.858 |
| z07 | 7.2.1 | 1 | 0.832 |
| z08 | 7.1.10 | 4 | 0.774 |
| z09 | 3, 5.4 | 4 | 0.845 |

Beklenen bölüm 1. sırada: 23/32, ilk 5 içinde: 31/32.

## Gecikme dağılımı

Bekleme (429/503 sonrası tekrar deneme) süresi hariç.

| Aralık | Çağrı |
|---|---|
| < 1 sn | 44 |
| 1–2 sn | 16 |
| 2–4 sn | 0 |
| ≥ 4 sn | 0 |

Toplam bekleme: 195 sn.

## Tüm sonuçlar

| Soru | Beklenen | Çıkan | ms | Kaynak | Cevap |
|---|---|---|---|---|---|
| q01 | cevap | cevap | 1637 | 10.1 | Yönetici Şirket tarafından talep edilmesi durumunda girişimcilerin uyması gereken koşullar şunlardır: • Bölgede yer alabilmeye ve bedelleri… |
| q02 | cevap | cevap | 1413 | 7.1.7 | Girişimcilerin ortak alanları kullanırken uyması gereken kurallar şunlardır: • Prototip atölyesinde herhangi bir mekanik, elektrik vb. çalı… |
| q03 | cevap | cevap | 1116 | 7.2.1 | Kira veya aidat ödemelerinin gecikmesi durumunda uygulanacak işlemler şunlardır: - Girişimci, ödemelerin gecikmesiyle ilgili bildirimlerde … |
| q04 | cevap | cevap | 891 | 7.1.4 | Girişimci, kendisine tahsis edilen alanda gerçekleştireceği tadilat, dekorasyon ve sair her türlü çalışma için Yönetici Şirketin yazılı izn… |
| q05 | cevap | cevap | 879 | 7.1.10 | Girişimci, kendi isteği ile Bölgeden ayrılmak isterse bunu en geç 30 (otuz) gün önce Yönetici Şirkete bildirmelidir. |
| q06 | cevap | cevap | 901 | 7.1.8 | Girişimcinin çalıştırdığı personelin Bölgede fiilen çalışıp çalışmadığı, kurulan dijital sistemler (kişiselleştirilmiş çipli kart, parmak i… |
| q07 | cevap | cevap | 882 | 13.1 | Aylık muafiyet raporu, takip eden ayın ilk 20 (yirmi) günü içerisinde elektronik imza sistemi ile Yönetici Şirket onayına sunulmalıdır. |
| q08 | cevap | cevap | 999 | 11.2 | Bölgede faaliyette bulunan girişimcilerin kazançlarının gelir ve kurumlar vergisinden istisna bulunduğu süre içinde münhasıran bölgelerde ü… |
| q09 | cevap | cevap | 1004 | 15.5 | Girişimci şu durumlarda kuluçka sürecini tamamlamış (mezun olmuş) sayılır: • Şirket kuruluşundan itibaren 3 seneyi doldurmuşsa, • Proje Değ… |
| q10 | cevap | cevap | 1017 | 16.3 | Üniversite bünyesinde görevli öğretim üyeleri, Teknoloji Geliştirme Bölgeleri Kanunu’nun getirdiği avantajlardan faydalanarak kendilerinin … |
| q11 | cevap | cevap | 895 | 1 | Yıldız Teknoloji Geliştirme Bölgesi Teknopark A.Ş. adına hazırlanmış olan İşletme Yönergesinin amacı; 4691 sayılı Teknoloji Geliştirme Bölg… |
| q12 | cevap | cevap | 889 | 2 | Yönerge, Bölgede yer alacak girişimciler ile Yönetici Şirketin hak, sorumluluk ve yükümlülüklerini düzenlemektedir. |
| q13 | cevap | cevap | 1006 | 3 | Ön kuluçka süresi en fazla 6 (altı) aydır. |
| q14 | cevap | cevap | 1493 | 4 | Yönergenin hazırlanmasında gözetilen temel mevzuatlar şunlardır: • 4691 sayılı Teknoloji Geliştirme Bölgeleri Kanunu • Teknoloji Geliştirme… |
| q15 | cevap | cevap | 1071 | 5.4 | Yıldız Teknoloji Geliştirme Bölgesi Teknopark A.Ş. Yönetim Kurulu, Başkan, Başkan Vekili ve üyelerden meydana gelen toplam 7 kişiden oluşur. |
| q16 | cevap | cevap | 899 | 6.1 | YTÜ Teknoloji Geliştirme Bölgesi üç yerleşkede hizmet vermektedir: • Davutpaşa Yerleşkesi • İkitelli OSB ek alanı • Maslak1453 ek alanı |
| q17 | cevap | cevap | 954 | 8.3.2 | Girişimci, kendisine tahsis edilen alanın temizliğinden bizzat sorumludur. |
| q18 | cevap | cevap | 1011 | 9 | Bölgedeki tüm binaların yangın ve doğal afetlere karşı sigortasını yaptırmak Yönetici Şirketin yetkisi ve sorumluluğundadır. Girişimciye ta… |
| q19 | cevap | cevap | 956 | 12.3 | Teknolojik ürün tanımlama belgesi ve yatırım fizibilite raporunun Yönetici Şirkete teslimini takiben oluşturulan Teknolojik Ürün Değerlendi… |
| q20 | cevap | cevap | 1620 | 14 | Girişimci, Ar-Ge ve yazılım projelerinde çalışan personel listesini Bölgede faaliyet göstermeye başladığı ilk 10 (on) gün içerisinde ve faa… |
| q21 | cevap | cevap | 1552 | 7.1.5, 7.1.8 | Yönerge kurallarına uymadığınızda veya aykırı faaliyette bulunduğunuzda karşılaşılabilecek bazı durumlar ve yaptırımlar şunlardır: - Dijita… |
| q22 | cevap | cevap | 1263 | 18 | Bölgede yer alan işletmelerde çalışan Ar-Ge ve tasarım personelinden yüksek lisans yapanlar, bir buçuk yılı geçmemek üzere Bölge dışında sü… |
| q23 | cevap | cevap | 913 | 19 | Bakanlık portal bilgi girişlerindeki eksik ve yanlış bilgilerden ve mevcut bilgilerin kontrolünden Girişimciler sorumludur. Herhangi bir ha… |
| q24 | cevap | cevap | 951 | 20 | Bakanlık, Yönetici Şirketin ve Girişimcilerin faaliyet ve uygulamalarını gerekli gördüğü durumlarda denetler. Gerektiğinde ilgili kurum ve … |
| q25 | cevap | cevap | 904 | 21 | Yıldız Teknoloji Geliştirme Bölgesi Teknopark A.Ş. tarafından gerekli görülen durumlarda güncellenecek olan bu yönerge, Sanayi ve Teknoloji… |
| x01 | bilgi_yok | bilgi_yok | 737 |  |  |
| x02 | bilgi_yok | bilgi_yok | 929 |  |  |
| x03 | bilgi_yok | bilgi_yok | 1122 |  |  |
| u01 | bilgi_yok | bilgi_yok | 901 |  |  |
| u02 | cevap | cevap | 960 | 7.2.1 | Ofis alanına ilişkin kira/kullanım bedelleri Yönetici Şirket Yönetim Kurulu tarafından her yıl belirlenmektedir. Belgede metrekare başına d… |
| u03 | bilgi_yok | bilgi_yok | 652 |  |  |
| k04 | bilgi_yok | bilgi_yok | 714 |  |  |
| k05 | bilgi_yok | bilgi_yok | 846 |  |  |
| k06 | bilgi_yok | bilgi_yok | 716 |  |  |
| s01 | sohbet | sohbet | 899 |  | Merhaba! Yıldız Teknopark Bölge İşletme Yönergesi hakkında size nasıl yardımcı olabilirim? |
| s02 | sohbet | sohbet | 952 |  | Rica ederim! YTÜ Yıldız Teknopark Bölge İşletme Yönergesi hakkında başka bir sorunuz olursa yardımcı olmaktan memnuniyet duyarım. |
| s03 | sohbet | sohbet | 820 |  | Ben Yıldız Teknopark Bölge İşletme Yönergesi hakkında soruları yanıtlayan bir asistansım. Yönergeyle ilgili her türlü sorunuzu bana yönelte… |
| s04 | sohbet | sohbet | 837 |  | YTÜ Yıldız Teknopark Bölge İşletme Yönergesi hakkındaki kurallar, süreçler ve tanımlar hakkında bana sorular sorabilirsiniz. Size bu belgel… |
| g01 | geçersiz | geçersiz | 0 |  |  |
| g02 | geçersiz | geçersiz | 0 |  |  |
| g03 | geçersiz | geçersiz | 0 |  |  |
| g04 | geçersiz | geçersiz | 0 |  |  |
| z01 | cevap | cevap | 1105 | 7.2.1 | Girişimci, kullanım ve kira bedeli ile işletme gideri ödemelerini faturalarda belirtilen günde, bildirimi takip eden 10 (on) iş günü içinde… |
| z02 | bilgi_yok | bilgi_yok | 970 |  |  |
| z03 | bilgi_yok | bilgi_yok | 1019 |  |  |
| z04 | bilgi_yok | bilgi_yok | 776 |  |  |
| z05 | bilgi_yok | bilgi_yok | 892 |  |  |
| x04 | bilgi_yok | bilgi_yok | 823 |  |  |
| x05 | bilgi_yok | bilgi_yok | 911 |  |  |
| x06 | bilgi_yok | bilgi_yok | 831 |  |  |
| u04 | bilgi_yok | bilgi_yok | 897 |  |  |
| u05 | bilgi_yok | bilgi_yok | 773 |  |  |
| u06 | cevap | cevap | 896 | 7.1.6, 7.1.7 | Girişimci personeli, kendi alanı veya bu amaçla ayrılmış alanlar dışındaki ortak alanlarda Tütün Ürünlerinin Zararlarının Önlenmesi ve Kont… |
| k07 | bilgi_yok | bilgi_yok | 776 |  |  |
| k08 | bilgi_yok | bilgi_yok | 707 |  |  |
| k09 | bilgi_yok | bilgi_yok | 830 |  |  |
| s05 | sohbet | sohbet | 956 |  | Günaydın! YTÜ Yıldız Teknopark yönergesi ile ilgili sorularınızı yanıtlamaktan memnuniyet duyarım. |
| s06 | sohbet | sohbet | 958 |  | Teşekkür ederim, iyiyim. Size Yıldız Teknopark Bölge İşletme Yönergesi hakkında nasıl yardımcı olabilirim? |
| s07 | sohbet | sohbet | 895 |  | Görüşmek üzere! Yıldız Teknopark Bölge İşletme Yönergesi hakkında her zaman soru sorabilirsiniz. |
| g05 | geçersiz | geçersiz | 0 |  |  |
| g06 | geçersiz | geçersiz | 0 |  |  |
| g07 | geçersiz | geçersiz | 0 |  |  |
| z06 | cevap | cevap | 843 | 7.1.4 | Evet, girişimci kendisine tahsis edilen alanda gerçekleştireceği tadilat, dekorasyon ve sair her türlü çalışma için Yönetici Şirketin yazıl… |
| z07 | cevap | cevap | 953 | 7.2.1 | Girişimcinin kullanım/kira bedeli ile işletme gideri ödemelerini bildirim tarihini takip eden 10 (on) iş günü içinde ödememesi halinde, vad… |
| z08 | cevap | cevap | 773 | 7.1.10 | Girişimci, kendi isteği ile Bölgeden ayrılmak ister ise bunu en geç 30 (otuz) gün önce Yönetici Şirkete bildirmelidir. |
| z09 | cevap | cevap | 1027 | 3 | Ön kuluçka, iş fikri ya da projesi olan henüz şirketleşmemiş Girişimci grubuna en fazla 6 (altı) ay süre ile danışmanlık, mentörlük ve proj… |
| z10 | bilgi_yok | bilgi_yok | 946 |  |  |

---
Rapor `tests/report.py` ile üretildi. Otomatik ölçümler cevap metninin doğruluğunu ölçmez; elle inceleme notları `eval/review.jsonl` dosyasından gelir.
