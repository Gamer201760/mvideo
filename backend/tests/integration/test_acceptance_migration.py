import json
import sqlite3
from pathlib import Path


def test_acceptance_migration_preserves_existing_rows_and_safe_rollback(database: Path) -> None:
    migration = (
        Path(__file__).resolve().parents[2] / "migrations/sqlite/20261019110000_auto_acceptance.sql"
    )
    up, down = migration.read_text().split("-- migrate:down")
    up = up.removeprefix("-- migrate:up")
    with sqlite3.connect(database) as connection:
        connection.executescript(down)
        payload = json.dumps({"status": "corrected", "resolved_value": "ручное значение"})
        connection.execute(
            "INSERT INTO reviews(id,card_key,attribute,evidence,status,payload) VALUES(?,?,?,?,?,?)",
            ("human", "card", "Цвет", "синий", "corrected", payload),
        )
        connection.executescript(up)
        assert connection.execute("SELECT payload FROM reviews WHERE id='human'").fetchone() == (
            payload,
        )
        connection.execute(
            "INSERT INTO reviews(id,card_key,attribute,evidence,status,payload) VALUES(?,?,?,?,?,?)",
            (
                "auto",
                "card",
                "Размер",
                "10 см",
                "auto_accepted",
                json.dumps({"status": "auto_accepted"}),
            ),
        )
        connection.executescript(down)
        status, raw = connection.execute(
            "SELECT status,payload FROM reviews WHERE id='auto'"
        ).fetchone()
        assert status == json.loads(raw)["status"] == "pending"
        assert connection.execute("SELECT payload FROM reviews WHERE id='human'").fetchone() == (
            payload,
        )
        connection.executescript(up)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
