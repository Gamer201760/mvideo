import json
import sqlite3
from pathlib import Path


def test_rejection_migration_preserves_manual_decisions_and_downgrades_safely(
    database: Path,
) -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations/sqlite/20261019144512_review_rejections.sql"
    )
    up, down = migration.read_text().split("-- migrate:down")
    up = up.removeprefix("-- migrate:up")
    with sqlite3.connect(database) as connection:
        payload = json.dumps(
            {"status": "rejected", "resolved_value": None, "resolved_at": "2026-10-19T14:00:00Z"}
        )
        accepted = json.dumps({"status": "corrected", "resolved_value": "ручное значение"})
        connection.executemany(
            "INSERT INTO reviews(id,card_key,attribute,evidence,status,payload) VALUES(?,?,?,?,?,?)",
            [
                ("rejected", "card", "Цвет", "синий", "rejected", payload),
                ("manual", "card", "Модель", "А1", "corrected", accepted),
            ],
        )
        connection.executescript(down)
        status, raw = connection.execute(
            "SELECT status,payload FROM reviews WHERE id='rejected'"
        ).fetchone()
        assert status == json.loads(raw)["status"] == "pending"
        assert json.loads(raw)["resolved_at"] is None
        assert connection.execute("SELECT payload FROM reviews WHERE id='manual'").fetchone() == (
            accepted,
        )
        connection.executescript(up)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
