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
    content           TEXT,
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

-- ---- Conversations / answers (every query is an assistant message; message id = query id)
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role              TEXT NOT NULL,              -- user | assistant
    content           TEXT NOT NULL,
    query_text        TEXT,                       -- assistant: the user question answered
    standalone_query  TEXT,                       -- assistant: question rewritten with history
    filters_json      TEXT,
    payload_json      TEXT,                       -- assistant: claims, citations, documents, routing
    confidence        REAL,
    confident         INTEGER,
    status            TEXT,                       -- answered | routed | refused | blocked | rejected | corrected
    feedback          TEXT,                       -- up | down
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS routing_suggestions (
    id                    TEXT PRIMARY KEY,
    message_id            TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    person                TEXT NOT NULL,
    role                  TEXT,
    reason                TEXT NOT NULL,
    matched_sources_json  TEXT NOT NULL DEFAULT '[]',
    draft_question        TEXT NOT NULL,
    edited_question       TEXT,
    status                TEXT NOT NULL DEFAULT 'suggested',   -- suggested | sent | dismissed
    sent_by               TEXT,
    sent_at               TEXT,
    created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gaps (
    id               TEXT PRIMARY KEY,
    message_id       TEXT REFERENCES messages(id) ON DELETE SET NULL,
    type             TEXT NOT NULL,              -- low_confidence | rejected | correction
    query_text       TEXT NOT NULL,
    original_answer  TEXT,
    correction_text  TEXT,
    reason           TEXT,
    submitted_by     TEXT,
    review_status    TEXT NOT NULL DEFAULT 'pending',   -- pending | reviewed | resolved
    reviewer_note    TEXT,
    created_at       TEXT NOT NULL,
    reviewed_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_gaps_status ON gaps(review_status, created_at);

CREATE TABLE IF NOT EXISTS metrics (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id            TEXT,
    created_at            TEXT NOT NULL,
    status                TEXT NOT NULL,
    guardrail             TEXT,                  -- input category when not a knowledge question
    latency_ms            INTEGER,
    first_token_ms        INTEGER,
    n_results             INTEGER,
    top_semantic          REAL,
    top_rerank            REAL,
    n_citations           INTEGER,
    citation_valid_ratio  REAL,
    uncited_dropped       INTEGER,
    pii_redactions        INTEGER,
    confidence            REAL
);

CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(created_at);

CREATE TABLE IF NOT EXISTS eval_runs (
    id            TEXT PRIMARY KEY,
    dataset       TEXT NOT NULL,
    status        TEXT NOT NULL,                 -- running | completed | failed
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    config_json   TEXT,
    summary_json  TEXT,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS eval_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    case_id       TEXT NOT NULL,
    question      TEXT NOT NULL,
    expected_json TEXT,
    answer        TEXT,
    result_json   TEXT
);
