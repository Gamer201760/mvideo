import sqlite3

from app.domain.errors import StorageBusy, StorageFailure, StorageUnavailable


def storage_failure(error: sqlite3.Error) -> StorageFailure:
    code = getattr(error, "sqlite_errorcode", 0) & 255
    if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
        return StorageBusy()
    if code in {
        sqlite3.SQLITE_CANTOPEN,
        sqlite3.SQLITE_IOERR,
        sqlite3.SQLITE_FULL,
        sqlite3.SQLITE_READONLY,
        sqlite3.SQLITE_CORRUPT,
        sqlite3.SQLITE_NOTADB,
    }:
        return StorageUnavailable()
    return StorageFailure()
