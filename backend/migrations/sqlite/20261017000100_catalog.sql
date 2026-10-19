-- migrate:up
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL
);
CREATE TABLE reviews (
    id TEXT PRIMARY KEY,
    card_key TEXT NOT NULL,
    attribute TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','accepted','corrected')),
    payload TEXT NOT NULL,
    UNIQUE(card_key, attribute, evidence)
);
CREATE INDEX reviews_status ON reviews(status);
CREATE TABLE aliases (
    card_key TEXT NOT NULL,
    category_id INTEGER,
    attribute TEXT NOT NULL,
    evidence TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(card_key, attribute, evidence)
);

-- migrate:down
DROP TABLE aliases;
DROP TABLE reviews;
DROP TABLE categories;
