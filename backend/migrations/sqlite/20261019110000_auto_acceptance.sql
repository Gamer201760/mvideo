-- migrate:up
CREATE TABLE reviews_updated (
    id TEXT PRIMARY KEY,
    card_key TEXT NOT NULL,
    attribute TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','auto_accepted','accepted','corrected')),
    payload TEXT NOT NULL,
    UNIQUE(card_key, attribute, evidence)
);
INSERT INTO reviews_updated SELECT id,card_key,attribute,evidence,status,payload FROM reviews;
DROP TABLE reviews;
ALTER TABLE reviews_updated RENAME TO reviews;
CREATE INDEX reviews_status ON reviews(status);

-- migrate:down
CREATE TABLE reviews_previous (
    id TEXT PRIMARY KEY,
    card_key TEXT NOT NULL,
    attribute TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','accepted','corrected')),
    payload TEXT NOT NULL,
    UNIQUE(card_key, attribute, evidence)
);
INSERT INTO reviews_previous
SELECT id,card_key,attribute,evidence,
    CASE WHEN status='auto_accepted' THEN 'pending' ELSE status END,
    CASE WHEN status='auto_accepted' THEN json_set(payload,'$.status','pending') ELSE payload END
FROM reviews;
DROP TABLE reviews;
ALTER TABLE reviews_previous RENAME TO reviews;
CREATE INDEX reviews_status ON reviews(status);
