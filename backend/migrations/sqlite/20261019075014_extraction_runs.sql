-- migrate:up
CREATE TABLE extraction_runs (
    id TEXT PRIMARY KEY,
    engine TEXT NOT NULL CHECK (engine IN ('rules','hybrid')),
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed','interrupted')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    input_json TEXT NOT NULL,
    result_json TEXT,
    CHECK ((status = 'completed') = (result_json IS NOT NULL))
);
CREATE INDEX extraction_runs_recent ON extraction_runs(started_at DESC,id DESC);


-- migrate:down
DROP TABLE extraction_runs;

