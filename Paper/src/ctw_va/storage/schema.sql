-- CTW-VA-2026 experiment data schema (SQLite)
-- Port from spec §6.2 Postgres DDL; adapted: UUID→TEXT, JSONB→TEXT(json), TIMESTAMPTZ→TEXT(iso8601)

CREATE TABLE IF NOT EXISTS experiment_run (
    experiment_id     TEXT PRIMARY KEY,
    persona_slate_id  TEXT NOT NULL,
    news_pool_id      TEXT NOT NULL,
    scenario          TEXT NOT NULL,
    replication_seed  INTEGER NOT NULL,
    started_at        TEXT,
    completed_at      TEXT,
    pipeline_version  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendor_call_log (
    call_id             TEXT PRIMARY KEY,
    experiment_id       TEXT NOT NULL REFERENCES experiment_run(experiment_id),
    persona_id          TEXT,
    sim_day             INTEGER,
    vendor              TEXT NOT NULL,
    model_id            TEXT,
    articles_shown      TEXT,   -- JSON array of article_ids
    prompt_hash         TEXT NOT NULL,
    response_raw        TEXT,
    refusal_status      TEXT,
    refusal_confidence  REAL,
    latency_ms          INTEGER,
    tokens_in           INTEGER,
    tokens_out          INTEGER,
    cost_usd            REAL,
    status              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vcl_experiment ON vendor_call_log(experiment_id);
CREATE INDEX IF NOT EXISTS idx_vcl_vendor ON vendor_call_log(vendor);
CREATE INDEX IF NOT EXISTS idx_vcl_persona ON vendor_call_log(persona_id);

CREATE TABLE IF NOT EXISTS agent_day_vendor (
    experiment_id       TEXT NOT NULL REFERENCES experiment_run(experiment_id),
    persona_id          TEXT NOT NULL,
    sim_day             INTEGER NOT NULL,
    vendor              TEXT NOT NULL,
    satisfaction        REAL,
    anxiety             REAL,
    candidate_awareness TEXT,   -- JSON object
    candidate_sentiment TEXT,
    candidate_support   TEXT,
    party_choice        TEXT,
    party_lean_5        TEXT,
    diary_text          TEXT,
    diary_tags          TEXT,   -- JSON
    PRIMARY KEY (experiment_id, persona_id, sim_day, vendor)
);
