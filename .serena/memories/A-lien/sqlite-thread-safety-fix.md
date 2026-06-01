# SQLite Thread-Safety Fix for Concurrent IMAP Sync

## Symptom
`retposto preni` with multiple accounts showed errors:
```
[✗] Sync error: SQLite objects created in a thread can only be used in that same thread.
The object was created in thread id X and this is thread id Y.
```

## Root Cause
`A.data.base.SQLiteDB` caches a single `sqlite3.Connection` (via `self._conn`).
When `sync_accounts_concurrent()` runs in a `ThreadPoolExecutor`, all worker threads
received the same `RetpostoService` singleton as `db_store` — meaning they all
shared the same `sqlite3.Connection`. Python's sqlite3 module enforces
`check_same_thread=True` by default and raises `ProgrammingError`.

## Fix (A-core commit 339ac7c, A-lien commit 1092b80)

### A-core: `SQLiteDB` thread safety via `threading.local`
**File:** `src/A/data/base.py`

Replaced the single cached `self._conn` with `threading.local()` storage.
Each thread now gets its own `sqlite3.Connection` to the same database file.
SQLite WAL mode handles concurrent reads + single writer correctly.

### A-lien: no workaround needed
`imap/sync.py` restored to original — the single shared `db_store` (the
`RetpostoService` singleton) is passed to all threads safely because the
underlying `SQLiteDB` creates per-thread connections.

`service/retposto_sync.py` keeps the module-level `get_known_uids()` and
`store_message()` helpers as a clean separation of SQL logic, but they are
not essential for the thread safety fix.

### Verification
- All 122 A-lien tests pass
- All 310 A-core tests pass
- No other `ThreadPoolExecutor` usage in A-lien or sister A-modules
