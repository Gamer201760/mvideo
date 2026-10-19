-- migrate:up
CREATE TABLE review_cards (
    card_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);


-- migrate:down
DROP TABLE review_cards;

