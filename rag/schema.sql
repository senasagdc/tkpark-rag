-- Vektör deposu şeması (PostgreSQL + pgvector). project.json › vectorStore.type = "pgvector" iken kullanılır.
-- Çekirdeğin parçası: belgeye özel hiçbir şey içermez; her proje aynı tablolara kendi `project` adıyla girer.
--
-- Tekrar çalıştırılabilir: her şey IF NOT EXISTS, var olan veriye dokunmaz.
-- Elle uygulamak:  docker cp rag/schema.sql tkpark-db:/tmp/schema.sql
--                  docker exec tkpark-db psql -U tkpark -d tkpark -v ON_ERROR_STOP=1 -f /tmp/schema.sql
--
-- Dosya karşılıkları (vectorStore.type = "flat"):
--   rag_indexes  ≈ index.json'ın üst kısmı (embedding ayarları, chunking ayarları, createdAt)
--   rag_chunks   ≈ index.json › chunks  +  faiss.index'teki vektörler (aynı satırda)

CREATE EXTENSION IF NOT EXISTS vector;

-- Proje başına 1 satır. search.py açılışta model ve boyutu buradan kontrol eder.
CREATE TABLE IF NOT EXISTS rag_indexes (
    project      text        PRIMARY KEY,
    model        text        NOT NULL,
    dimensions   int         NOT NULL CHECK (dimensions > 0),
    settings     jsonb       NOT NULL,
    chunk_count  int         NOT NULL CHECK (chunk_count >= 0),
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Chunk başına 1 satır: metin, metadata ve vektör birlikte.
-- Boyut sütunda sabit değil (vector, vector(768) değil): farklı modelle embed edilmiş projeler aynı tabloda durabilir.
-- Boyut kontrolünü kod yapar (embed.py yazarken, search.py açılışta: rag_indexes.dimensions).
CREATE TABLE IF NOT EXISTS rag_chunks (
    project    text   NOT NULL REFERENCES rag_indexes (project) ON DELETE CASCADE,
    chunk_id   text   NOT NULL,
    position   int    NOT NULL CHECK (position >= 0),
    text       text   NOT NULL,
    tokens     int    NOT NULL CHECK (tokens > 0),
    metadata   jsonb  NOT NULL,
    embedding  vector NOT NULL,
    PRIMARY KEY (project, chunk_id),
    UNIQUE (project, position)
);

COMMENT ON TABLE  rag_indexes             IS 'Proje başına indeks bilgisi (index.json üst kısmının karşılığı)';
COMMENT ON COLUMN rag_indexes.model       IS 'Embedding modeli; project.json › embedding.model ile aynı olmalı';
COMMENT ON COLUMN rag_indexes.dimensions  IS 'Vektör boyutu (modelin gerçek çıktısı); rag_chunks.embedding bu boyutta olmalı';
COMMENT ON COLUMN rag_indexes.settings    IS 'Vektörü belirleyen ayarlar: önekler, normalize, chunking';
COMMENT ON TABLE  rag_chunks              IS 'Chunk metni + metadata + embedding (embed.py yazar, elle değiştirme)';
COMMENT ON COLUMN rag_chunks.position     IS 'index.json › chunks sırası; Retriever bu numarayla chunk''a ulaşır';
COMMENT ON COLUMN rag_chunks.metadata     IS 'source, section, title, path, pages (kaynak türüne göre değişebilir)';
COMMENT ON COLUMN rag_chunks.embedding    IS 'Normalize vektör; benzerlik = 1 - (embedding <=> soru)';
