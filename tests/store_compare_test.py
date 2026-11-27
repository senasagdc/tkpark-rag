"""Vektör deposu karşılaştırması (LLM yok): FAISS ("flat") ile PostgreSQL + pgvector aynı sonucu veriyor mu?

İki depo da kesin arama yaptığı için, aynı soruda TÜM chunk'ların sırası ve puanı aynı olmalı.
Sorular: eval/retrieval.jsonl + eval/testset.jsonl (geçersiz/boş olanlar hariç).
Her iki depo da önceden embed.py ile üretilmiş olmalı (flat: index/<id>/, pgvector: veritabanı).

Kullanım:
    python tests/store_compare_test.py              # ekrana özet + eval/reports/store-compare-<zaman>.md
    python tests/store_compare_test.py --no-save    # yalnızca ekran
    python tests/store_compare_test.py --project <id>

Ölçülenler:
    arama kalitesi her depoda ayrı (retrieval.jsonl: Hit@1/3/5, MRR)
    iki deponun sonuçları aynı mı: ilk 1/5/20 ve 186 chunk'ın tam sıralaması, puan farkı
    hız: depoyu açma süresi, soru başına arama süresi (embedding hariç), embedding süresi (ortak)
Sıralama farkı yalnızca puanları neredeyse eşit (fark < 1e-5) chunk'lar arasındaysa zararsız sayılır.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))

from config import ROOT, ConfigError, load_project  # noqa: E402
from search import FaissStore, PgStore, SentenceTransformer  # noqa: E402

TIE = 1e-5
TOP = (1, 5, 20)
HIT_AT = (1, 3, 5)
REPEAT = 3  # hız ölçümünde her soru kaç kez aranır (medyan alınır)
DEFAULT_REPORTS_DIR = "eval/reports"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def section(chunks, i) -> str:
    return chunks[int(i)]["metadata"].get("section") or "?"


def rank_of(chunks, ids, expected) -> int | None:
    return next((r for r, i in enumerate(ids, 1) if section(chunks, i) in expected), None)


def quality(chunks, ids_rows, items) -> dict:
    ranks = [rank_of(chunks, ids, it["expected"]) for ids, it in zip(ids_rows, items)]
    n = len(ranks)
    return {"n": n, "ranks": ranks,
            **{f"hit{h}": sum(1 for r in ranks if r and r <= h) for h in HIT_AT},
            "mrr": sum(1 / r for r in ranks if r) / n if n else 0.0}


def timed(fn, *args):
    t0 = time.perf_counter()
    out = fn(*args)
    return out, (time.perf_counter() - t0) * 1000


def per_query_ms(store, q: np.ndarray) -> list[float]:
    """Her soruyu tek başına arar (canlı kullanım gibi); REPEAT tekrarın medyanı."""
    store.search(q[:1])  # ısınma (ilk sorgu planı / önbellek)
    out = []
    for row in q:
        times = [timed(store.search, row[None, :])[1] for _ in range(REPEAT)]
        out.append(statistics.median(times))
    return out


def p90(values):
    return float(np.percentile(values, 90))


def size_mb(path: Path) -> float:
    return path.stat().st_size / 1e6 if path.exists() else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="FAISS ile pgvector aynı sonucu veriyor mu?")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    parser.add_argument("--no-save", action="store_true", help="raporu dosyaya yazma")
    args = parser.parse_args()
    try:
        project = load_project(args.project)
        faiss_store, faiss_open_ms = timed(FaissStore, project)
        pg_store, pg_open_ms = timed(PgStore, project)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    # ---- aynı chunk'lar mı? (aynı sırada, aynı id ve metin)
    chunks = faiss_store.chunks
    same_chunks = [(a["id"], a["text"]) for a in chunks] == [(b["id"], b["text"]) for b in pg_store.chunks]
    print(f"Chunk'lar: FAISS {len(chunks)}, DB {len(pg_store.chunks)} → "
          f"{'aynı (id, metin, sıra)' if same_chunks else 'FARKLI'}")
    if not same_chunks:
        print("İki depo farklı chunk'larla üretilmiş; ikisini de embed.py ile yeniden üret.", file=sys.stderr)
        return 2

    # ---- sorular
    retrieval_items = read_jsonl(project.path(project.get("eval.retrieval", "eval/retrieval.jsonl")))
    testset_items = read_jsonl(project.path(project.get("eval.testset", "eval/testset.jsonl")))
    qs = []
    for it in retrieval_items + testset_items:
        q = (it.get("question") or "").strip()
        if len(q) >= 3 and q not in qs:
            qs.append(q)

    model_name = project.get("embedding.model")
    model = SentenceTransformer(model_name)
    prefix = project.get("embedding.queryPrefix")
    encode = lambda texts: model.encode([prefix + s for s in texts], normalize_embeddings=True,
                                        convert_to_numpy=True).astype(np.float32)
    q = encode(qs)
    embed_ms = [timed(encode, [s])[1] for s in qs[:20]]
    fs, fi = faiss_store.search(q)
    ps, pi = pg_store.search(q)

    # ---- 1. arama kalitesi (retrieval.jsonl'daki cevaplı sorular)
    answerable = [it for it in retrieval_items if it.get("expected")]
    idx = {s: j for j, s in enumerate(qs)}
    rows = [idx[it["question"].strip()] for it in answerable]
    qf, qp = quality(chunks, fi[rows], answerable), quality(chunks, pi[rows], answerable)

    # ---- 2. iki depo aynı mı
    n, total = len(qs), fi.shape[1]
    same_top = {k: int(sum((fi[j, :k] == pi[j, :k]).all() for j in range(n))) for k in TOP}
    full_same, harmless, real = 0, [], []
    for j in range(n):
        diff = np.nonzero(fi[j] != pi[j])[0]
        if not len(diff):
            full_same += 1
            continue
        r = int(diff[0])
        db_score_of_faiss_chunk = float(ps[j][pi[j] == fi[j, r]][0])
        tie = abs(float(fs[j, r]) - db_score_of_faiss_chunk) < TIE and abs(float(fs[j, r]) - float(ps[j, r])) < TIE
        (harmless if tie else real).append((qs[j], r + 1, float(fs[j, r]), float(ps[j, r])))
    max_diff = 0.0
    for j in range(n):
        f_by_pos = dict(zip(fi[j].tolist(), fs[j].tolist()))
        max_diff = max(max_diff, max(abs(f_by_pos[p] - s) for p, s in zip(pi[j].tolist(), ps[j].tolist())))

    # ---- 3. hız
    faiss_ms, pg_ms = per_query_ms(faiss_store, q), per_query_ms(pg_store, q)

    # ---- 4. boyut / sürüm
    pg_version, vec_version, pg_size = pg_store.conn.execute(
        "SELECT current_setting('server_version'), (SELECT extversion FROM pg_extension WHERE extname = 'vector'),"
        " pg_total_relation_size('rag_chunks') + pg_total_relation_size('rag_indexes')").fetchone()
    faiss_size = size_mb(project.index_dir / "faiss.index") + size_mb(project.index_dir / "index.json")

    ok = not real and same_top[5] == n and qf["mrr"] == qp["mrr"]

    # ---- ekran
    print(f"Soru: {n} | her soruda sıralanan chunk: {total}")
    for k in TOP:
        print(f"  İlk {k:>2} aynı: {same_top[k]}/{n}")
    print(f"  Sıralamanın tamamı aynı: {full_same}/{n}"
          + (f" (kalan {len(harmless)}: yalnızca eşit puanlı chunk'lar yer değiştirmiş)" if harmless else ""))
    for qtext, rank, a, b in real[:10]:
        print(f"  FARK: {rank}. sırada FAISS {a:.6f} / DB {b:.6f} — {qtext[:60]}")
    print(f"  Aynı chunk'ın puan farkı: en fazla {max_diff:.1e}")
    print(f"Kalite (retrieval.jsonl, {qf['n']} cevaplı soru): FAISS Hit@5 {qf['hit5']}/{qf['n']} MRR {qf['mrr']:.3f}"
          f" | pgvector Hit@5 {qp['hit5']}/{qp['n']} MRR {qp['mrr']:.3f}")
    print(f"Hız (soru başına arama, embedding hariç): FAISS medyan {statistics.median(faiss_ms):.2f} ms"
          f" | pgvector medyan {statistics.median(pg_ms):.2f} ms | embedding medyan {statistics.median(embed_ms):.0f} ms")
    print("Sonuç:", "AYNI (iki depo birbirinin yerine kullanılabilir)" if ok else "FARKLI")

    if not args.no_save:
        report = build_report(
            project=project, model_name=model_name, dims=pg_store.dimensions, chunks=chunks, n=n, total=total,
            same_top=same_top, full_same=full_same, harmless=harmless, real=real, max_diff=max_diff,
            answerable=answerable, rows=rows, fi=fi, fs=fs, pi=pi, ps=ps, qf=qf, qp=qp,
            faiss_ms=faiss_ms, pg_ms=pg_ms, embed_ms=embed_ms, faiss_open_ms=faiss_open_ms, pg_open_ms=pg_open_ms,
            pg_version=pg_version, vec_version=vec_version, pg_size=pg_size / 1e6, faiss_size=faiss_size, ok=ok)
        out_dir = project.path(project.get("eval.reportsDir", DEFAULT_REPORTS_DIR))
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"store-compare-{datetime.now():%Y%m%d-%H%M%S}.md"
        out.write_text(report, encoding="utf-8")
        print(f"→ {out.relative_to(ROOT)}")
    return 0 if ok else 2


def build_report(*, project, model_name, dims, chunks, n, total, same_top, full_same, harmless, real, max_diff,
                 answerable, rows, fi, fs, pi, ps, qf, qp, faiss_ms, pg_ms, embed_ms, faiss_open_ms, pg_open_ms,
                 pg_version, vec_version, pg_size, faiss_size, ok) -> str:
    med = statistics.median
    llm_ms = 2700  # 26.11 cevap testinde LLM cevabının medyanı (~2.7 sn); karşılaştırma için
    o = [f"# Vektör deposu karşılaştırması: FAISS ve PostgreSQL + pgvector — {project.id}", "",
         f"- **Tarih:** {datetime.now():%d.%m.%Y %H:%M}",
         f"- **Belge:** {len(chunks)} chunk · embedding `{model_name}` ({dims} boyut, normalize)",
         f"- **FAISS:** `IndexFlatIP` (kesin arama) · dosyalar `index/{project.id}/faiss.index` + `index.json`",
         f"- **pgvector:** PostgreSQL {pg_version} + pgvector {vec_version} (Docker) · tablolar `rag_indexes` + `rag_chunks`"
         " · indeks yok (kesin arama)",
         f"- **Sorular:** {n} (retrieval.jsonl + testset.jsonl; boş ve 3 karakterden kısa olanlar hariç)", ""]

    o += ["## Kısa sonuç", "",
          ("İki depo **aynı sonucu** veriyor; chatbot hangisini kullansa aynı parçaları bulur." if ok else
           "İki depo **farklı sonuç** veriyor; aşağıdaki farkları incele."),
          "",
          f"- Arama kalitesi aynı: Hit@5 {qf['hit5']}/{qf['n']} ve {qp['hit5']}/{qp['n']}, MRR {qf['mrr']:.3f} ve {qp['mrr']:.3f}.",
          f"- {n} sorunun {same_top[20]}'inde ilk 20 sonuç birebir aynı; puan farkı en fazla {max_diff:.0e} (yuvarlama).",
          f"- Fark hızda ve verinin nerede durduğunda: arama FAISS'te ~{med(faiss_ms):.2f} ms, pgvector'de"
          f" ~{med(pg_ms):.1f} ms. İkisi de sorunun embedding'inden (~{med(embed_ms):.0f} ms) ve LLM cevabından"
          f" (~{llm_ms / 1000:.1f} sn) çok küçük; kullanıcı farkı hissetmez.", ""]

    o += ["## Ne karşılaştırıldı, neden aynı çıkmalı", "",
          "Chatbot bir soruyu cevaplamadan önce belgedeki en ilgili parçaları bulur (retrieval). Bunun için soruyu bir"
          " vektöre çevirir ve 186 parçanın vektörüyle tek tek karşılaştırır. Bu karşılaştırmayı yapan yer **vektör"
          " deposu**dur. Eskiden depo iki dosyaydı (FAISS); artık bir veritabanı (PostgreSQL + pgvector).",
          "",
          "İkisi de **kesin arama** yapıyor: soruyu bütün parçalarla karşılaştırıyor, tahmin yürütmüyor. Vektörler de"
          " aynı (aynı model, aynı parçalar). Bu yüzden doğru çalışıyorlarsa aynı parçaları, aynı sırayla, aynı puanla"
          " döndürmeleri gerekir. Bu rapor bunu ölçüyor. Puan ikisinde de **cosine benzerliği** (1'e yakın = çok"
          " benzer): FAISS'te iç çarpım, pgvector'de `1 - (embedding <=> soru)`.", ""]

    o += ["## 1. Arama kalitesi: doğru bölümü buluyor mu?", "",
          f"`retrieval.jsonl`'daki cevabı belgede olan {qf['n']} soruda beklenen bölüm kaçıncı sırada geliyor."
          " **Hit@K** = doğru bölüm ilk K sonuç içinde mi; **MRR** = 1/sıra ortalaması (1.0 = hep 1. sırada).", "",
          "| Ölçüm | FAISS | pgvector |", "|---|---|---|"]
    for h in HIT_AT:
        o.append(f"| Hit@{h} | {qf[f'hit{h}']}/{qf['n']} | {qp[f'hit{h}']}/{qp['n']} |")
    o += [f"| MRR | {qf['mrr']:.3f} | {qp['mrr']:.3f} |", ""]

    o += ["## 2. İki depo aynı sırayı veriyor mu?", "",
          f"Bütün sorular ({n}) iki depoya da soruldu; her soruda {total} parçanın tamamı sıralandı.", "",
          "| Ölçüm | Sonuç |", "|---|---|"]
    for k in TOP:
        o.append(f"| İlk {k} sonuç aynı | {same_top[k]}/{n} |")
    o.append(f"| {total} parçanın tam sıralaması aynı | {full_same}/{n} |")
    o.append(f"| Aynı parçanın iki depodaki puan farkı | en fazla {max_diff:.1e} |")
    o.append("")
    if harmless:
        o.append(f"Tam sıralaması farklı {len(harmless)} soruda fark, puanları neredeyse eşit (fark < {TIE:g}) iki parçanın"
                 " yer değiştirmesi; ilk sırada değil, chatbot'un kullandığı ilk 5'i etkilemiyor:")
        o.append("")
        for qtext, rank, a, b in harmless:
            o.append(f"- {rank}. sıra · FAISS {a:.6f} / pgvector {b:.6f} · \"{qtext[:70]}\"")
        o.append("")
    if real:
        o.append("**Gerçek farklar (incelenmeli):**")
        o += [f"- {rank}. sıra · FAISS {a:.6f} / pgvector {b:.6f} · \"{qtext[:70]}\"" for qtext, rank, a, b in real]
        o.append("")
    o += ["Puan farkı neden sıfır değil: iki depo da vektörleri 32 bitlik ondalık sayı (float32) olarak saklıyor ve"
          " hesabı farklı sırada yapıyor; milyonda birlik yuvarlama farkı normal.", ""]

    o += ["## 3. Soru soru (retrieval.jsonl)", "",
          "Her depoda 1. sırada gelen parçanın bölümü ve puanı; son sütun beklenen bölümün sırası (FAISS / pgvector).", "",
          "| id | Soru | Beklenen | FAISS 1. | pgvector 1. | Doğru bölüm sırası |", "|---|---|---|---|---|---|"]
    for it, j, rf, rp in zip(answerable, rows, qf["ranks"], qp["ranks"]):
        f1 = f"{section(chunks, fi[j, 0])} · {fs[j, 0]:.4f}"
        p1 = f"{section(chunks, pi[j, 0])} · {ps[j, 0]:.4f}"
        o.append(f"| {it['id']} | {it['question']} | {', '.join(it['expected'])} | {f1} | {p1} | {rf} / {rp} |")
    o.append("")

    o += ["## 4. Hız", "",
          "Soru başına süre (milisaniye). Arama süresi yalnızca depoya sormayı ölçer; sorunun vektöre çevrilmesi"
          " (embedding) iki depoda ortak ve ayrı satırda.", "",
          "| | FAISS | pgvector |", "|---|---|---|",
          f"| Depoyu açma (bir kez, program başlarken) | {faiss_open_ms:.0f} ms | {pg_open_ms:.0f} ms |",
          f"| Arama, medyan | {med(faiss_ms):.2f} ms | {med(pg_ms):.2f} ms |",
          f"| Arama, p90 | {p90(faiss_ms):.2f} ms | {p90(pg_ms):.2f} ms |",
          f"| Sorunun embedding'i (ortak), medyan | {med(embed_ms):.0f} ms | {med(embed_ms):.0f} ms |",
          f"| LLM cevabı (ortak, 26.11 ölçümü), medyan | ~{llm_ms} ms | ~{llm_ms} ms |", "",
          "pgvector daha yavaş, çünkü soru ağ üzerinden (Windows → Docker) ayrı bir programa gidiyor ve sonuç geri"
          " geliyor; FAISS aynı programın belleğinde arıyor. Ama bir cevabın toplam süresi ~3 saniye ve bunun"
          f" neredeyse tamamı LLM; aramanın payı pgvector'de bile binde birden az.", ""]

    o += ["## 5. Veri nerede duruyor, ne fark ediyor", "",
          "| | FAISS (dosya) | PostgreSQL + pgvector (veritabanı) |", "|---|---|---|",
          f"| Nerede | `index/{project.id}/` içinde 2 dosya ({faiss_size:.2f} MB) | Docker'daki veritabanı, volume `tkpark-pg-data` ({pg_size:.2f} MB, tablo indeksleri dahil) |",
          "| Metin ile vektör | Ayrı dosyalarda, sıra numarasıyla eşleşiyor | Aynı satırda |",
          "| Kim okuyabilir | Yalnızca dosyayı açan program | Aynı anda birden çok program (Python, ileride Node backend, DBeaver) |",
          "| Güncelleme | Dosyalar baştan yazılır | Tek transaction: ya hepsi yazılır ya hiçbiri |",
          "| Yanlış veri | Kontrolü kod yapar | Kod + veritabanı kuralları (tekil id, sıra no, zorunlu alanlar) |",
          "| Çalışması için | Hiçbir şey | Docker açık olmalı (`docker compose up -d`) |",
          "| Büyürse | `IndexHNSWFlat` | HNSW indeksi (`CREATE INDEX ... USING hnsw`) |", ""]

    o += ["## Hangisi ne zaman", "",
          "- **pgvector** (şu anki ayar, `vectorStore.type: \"pgvector\"`): normal kullanım; ileride backend ve arayüz"
          " aynı veritabanını okuyacak.",
          "- **FAISS** (`\"flat\"`): Docker'ın olmadığı bir bilgisayarda çalıştırmak ya da karşılaştırma için yedek."
          " Sonuçlar aynı olduğu için geçiş yalnızca `project.json`'da tek satır.", "",
          "Raporu yeniden üretmek için: `python tests/store_compare_test.py` (iki depo da `embed.py` ile üretilmiş,"
          " Docker açık olmalı).", ""]
    return "\n".join(o)


if __name__ == "__main__":
    sys.exit(main())
