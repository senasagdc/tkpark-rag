-- İlk kurulumda (volume boşken) PostgreSQL bu klasördeki .sql dosyalarını ada göre sırayla çalıştırır.
-- Volume doluysa hiç çalışmaz; bu yüzden içindekiler tekrar çalışsa da zarar vermeyecek biçimde yazılır.
CREATE EXTENSION IF NOT EXISTS vector;
