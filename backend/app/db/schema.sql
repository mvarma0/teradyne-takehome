CREATE TABLE IF NOT EXISTS documents (
    id                TEXT PRIMARY KEY,
    source_file       TEXT NOT NULL UNIQUE,
    source_type       TEXT NOT NULL,
    title             TEXT,
    date              TEXT,
    authors_json      TEXT NOT NULL DEFAULT '[]',
    attendees_json    TEXT NOT NULL DEFAULT '[]',
    attendees_source  TEXT,
    content_hash      TEXT NOT NULL,
    collection        TEXT NOT NULL,
    topic_domain      TEXT,
    priority          TEXT,
    products_json     TEXT NOT NULL DEFAULT '[]',
    key_topics_json   TEXT NOT NULL DEFAULT '[]',
    summary           TEXT,
    decisions_json    TEXT NOT NULL DEFAULT '[]',
    enrichment_json   TEXT,
    extra_json        TEXT NOT NULL DEFAULT '{}',
    n_chunks          INTEGER NOT NULL DEFAULT 0,
    ingested_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_topic ON documents(topic_domain);
CREATE INDEX IF NOT EXISTS idx_documents_priority ON documents(priority);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(source_type);

CREATE TABLE IF NOT EXISTS action_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    owner        TEXT,
    task         TEXT NOT NULL,
    due_date     TEXT
);

CREATE INDEX IF NOT EXISTS idx_action_items_doc ON action_items(document_id);

CREATE TABLE IF NOT EXISTS enrichment_cache (
    content_hash     TEXT NOT NULL,
    model            TEXT NOT NULL,
    enrichment_json  TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (content_hash, model)
);
