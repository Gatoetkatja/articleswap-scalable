-- ============================================
-- ArticleSwap: skema database
-- ============================================

CREATE TYPE pipeline_status AS ENUM ('PENDING', 'PROCESSING', 'DONE', 'FAILED');
CREATE TYPE forward_level AS ENUM ('FULL', 'PARTIAL', 'RAW');

-- Artikel mentah: immutable, tidak pernah diubah worker
CREATE TABLE articles (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_id     VARCHAR(64) NOT NULL,
    recipient_id  VARCHAR(64) NOT NULL,
    title         TEXT NOT NULL,
    content       TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- State pemrosesan: satu baris per artikel, diupdate worker
CREATE TABLE article_processing (
    article_id        UUID PRIMARY KEY REFERENCES articles(id),
    stemming_status   pipeline_status NOT NULL DEFAULT 'PENDING',
    wordcloud_status  pipeline_status NOT NULL DEFAULT 'PENDING',
    stemmed_content   TEXT,
    wordcloud_data    JSONB,
    deadline_at       TIMESTAMPTZ NOT NULL,   -- batas tunggu sebelum degradasi
    forwarded_at      TIMESTAMPTZ,            -- NULL = belum dikirim
    forwarded_level   forward_level,          -- FULL / PARTIAL / RAW
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index untuk polling Forwarding Service
CREATE INDEX idx_pending_forward
    ON article_processing (deadline_at)
    WHERE forwarded_at IS NULL;