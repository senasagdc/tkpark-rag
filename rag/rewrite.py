"""Query rewriting (adım 5, kural listesi): soruyu belgenin diline yaklaştırır.

Neden: kullanıcı "firma" der, belge "Girişimci" der; embedding modeli bu ikisini her zaman eşleştiremiyor.
Kural listesi soruda geçen kelimeyi belgenin terimiyle değiştirip sorunun ikinci bir halini üretir.
Arama iki soruyla da yapılır, sonuçlar RRF ile birleştirilir (rag/search.py); böylece yeniden yazma
yanlış çıksa bile orijinal sorunun bulduğu parçalar kaybolmaz.

Ayarlar project.json › queryRewrite (yoksa kapalı):
    enabled  true / false
    rules    [{"match": ["firma"], "replace": "Girişimci"}, ...]
             match: kelime başları; büyük/küçük harf fark etmez, kelimenin eki de kapsanır
             ("firma" → "Firma", "firmanın", "firmalar"). Eşleşen kelimenin tamamı replace ile değişir.
Terimler projeye özeldir; çekirdekte hiçbir kelime yazılı değildir.
"""

from __future__ import annotations

import re

from config import ConfigError


class QueryRewriter:
    def __init__(self, project):
        self.rules = []
        for n, rule in enumerate(project.get("queryRewrite.rules", []), 1):
            match, replace = rule.get("match"), rule.get("replace")
            if not match or not isinstance(match, list) or not replace:
                raise ConfigError(f"queryRewrite.rules[{n}]: 'match' (liste) ve 'replace' zorunlu.")
            stems = "|".join(re.escape(m.casefold()) for m in match)
            self.rules.append((re.compile(rf"(?<!\w)(?:{stems})\w*", re.IGNORECASE), replace))

    def rewrite(self, question: str) -> str | None:
        """Kurallardan biri uyarsa yeniden yazılmış soruyu, hiçbiri uymazsa None döndürür."""
        text = question
        for pattern, replace in self.rules:
            text = pattern.sub(replace, text)
        return text if text != question else None

    def settings(self) -> dict:
        return {"rules": len(self.rules)}
