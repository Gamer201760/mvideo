import hashlib
import sqlite3
import threading
from pathlib import Path


class SqliteCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value BLOB)")
        self._db.commit()

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    def get_many(self, keys: list[str]) -> dict[str, bytes]:
        found: dict[str, bytes] = {}
        with self._lock:
            for start in range(0, len(keys), 500):
                chunk = keys[start:start + 500]
                marks = ",".join("?" * len(chunk))
                rows = self._db.execute(
                    f"SELECT key, value FROM cache WHERE key IN ({marks})", chunk).fetchall()
                found.update({k: bytes(v) for k, v in rows})
        return found

    def put_many(self, items: dict[str, bytes]) -> None:
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
                                 list(items.items()))
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()
