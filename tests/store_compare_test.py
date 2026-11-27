"""Vektör deposu karşılaştırması (LLM yok): FAISS ("flat") ile PostgreSQL + pgvector aynı sonucu veriyor mu?

İki depo da kesin arama yaptığı için, aynı soruda TÜM chunk'ların sırası ve puanı aynı olmalı.
Sorular: eval/retrieval.jsonl + eval/testset.jsonl (geçersiz/boş olanlar hariç).
Her iki depo da önceden embed.py ile üretilmiş olmalı (flat: index/<id>/, pgvector: veritabanı).

Kullanım:
    python tests/store_compare_test.py
    python tests/store_compare_test.py --project <id>

Rapor:
    ilk K'si aynı olan soru sayısı (K = 1, 5, 20)
    sıralamanın tamamı aynı olan soru sayısı; farklıysa ilk farkın sırası ve iki puan
    en büyük puan farkı (float32 yuvarlaması ~1e-6 beklenir)
Sıralama farkı yalnızca puanları neredeyse eşit (fark < 1e-5) chunk'lar arasındaysa zararsız sayılır.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))

from config import ConfigError, load_project  # noqa: E402
from search import FaissStore, PgStore, SentenceTransformer  # noqa: E402

TIE = 1e-5
TOP = (1, 5, 20)


def questions(project) -> list[str]:
    out = []
    for name in ("eval/retrieval.jsonl", "eval/testset.jsonl"):
        path = project.path(name)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                q = (json.loads(line).get("question") or "").strip()
                if len(q) >= 3 and q not in out:
                    out.append(q)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="FAISS ile pgvector aynı sonucu veriyor mu?")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    try:
        project = load_project(args.project)
        faiss_store, pg_store = FaissStore(project), PgStore(project)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    # Aynı chunk'lar mı? (aynı sırada, aynı id ve metin)
    same_chunks = [(a["id"], a["text"]) for a in faiss_store.chunks] == [(b["id"], b["text"]) for b in pg_store.chunks]
    print(f"Chunk'lar: FAISS {len(faiss_store.chunks)}, DB {len(pg_store.chunks)} → "
          f"{'aynı (id, metin, sıra)' if same_chunks else 'FARKLI'}")
    if not same_chunks:
        print("İki depo farklı chunk'larla üretilmiş; ikisini de embed.py ile yeniden üret.", file=sys.stderr)
        return 2

    qs = questions(project)
    model = SentenceTransformer(project.get("embedding.model"))
    q = model.encode([project.get("embedding.queryPrefix") + s for s in qs],
                     normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
    fs, fi = faiss_store.search(q)
    ps, pi = pg_store.search(q)

    n, total = len(qs), fi.shape[1]
    same_top = {k: int(sum((fi[j, :k] == pi[j, :k]).all() for j in range(n))) for k in TOP}
    full_same, harmless, real = 0, [], []
    for j in range(n):
        diff = np.nonzero(fi[j] != pi[j])[0]
        if not len(diff):
            full_same += 1
            continue
        r = int(diff[0])
        gap = abs(float(fs[j, r]) - float(ps[j, r]))
        # FAISS'in o sıradaki chunk'ının DB'deki puanı: neredeyse eşitse yer değiştirme zararsız
        db_score_of_faiss_chunk = float(ps[j][pi[j] == fi[j, r]][0])
        tie = abs(float(fs[j, r]) - db_score_of_faiss_chunk) < TIE and gap < TIE
        (harmless if tie else real).append((qs[j], r + 1, float(fs[j, r]), float(ps[j, r])))

    # puan farkı: aynı chunk'ın iki depodaki puanı
    max_diff = 0.0
    for j in range(n):
        f_by_pos = dict(zip(fi[j].tolist(), fs[j].tolist()))
        max_diff = max(max_diff, max(abs(f_by_pos[p] - s) for p, s in zip(pi[j].tolist(), ps[j].tolist())))

    print(f"Soru: {n} | her soruda sıralanan chunk: {total}")
    for k in TOP:
        print(f"  İlk {k:>2} aynı: {same_top[k]}/{n}")
    print(f"  Sıralamanın tamamı aynı: {full_same}/{n}")
    if harmless:
        print(f"  Yalnızca eşit puanlı chunk'lar yer değiştirmiş (zararsız): {len(harmless)}")
    for qtext, rank, a, b in real[:10]:
        print(f"  FARK: {rank}. sırada FAISS {a:.6f} / DB {b:.6f} — {qtext[:60]}")
    print(f"  Aynı chunk'ın puan farkı: en fazla {max_diff:.1e}")
    ok = not real and same_top[5] == n
    print("Sonuç:", "AYNI (iki depo birbirinin yerine kullanılabilir)" if ok else "FARKLI")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
