CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'ios-shortcut',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Triage tags written back by the recent-clips skill. NULL means not yet
    -- triaged; status is a fixed vocabulary, topic is a growable seed set.
    status TEXT,
    topic TEXT
);

CREATE INDEX IF NOT EXISTS idx_clips_created_at
    ON clips (created_at DESC);
