# Retposto SMTP Port 465 SSL Fix + Related Improvements

## Problem
`retposto sendi` said "Mesaĝo sendita" but message not received. Two root causes:

### 1. Missing implicit SSL (SMTPS) for port 465
SMTPClient always used `smtplib.SMTP()` (plain). Account `ron@ronzz.org` used port 465 with `smtp_tls=0`, requiring `smtplib.SMTP_SSL()`. The code had no `use_ssl` parameter.

**Fix**: Added `use_ssl: bool` parameter to `SMTPClient.__init__()`. When `use_ssl=True`, `connect()` uses `smtplib.SMTP_SSL()` instead of `smtplib.SMTP()`. Caller in `retposto_sync.py` passes `use_ssl=True` when port == 465.

### 2. Wrong default account when --konto omitted
Default account selection picked `accounts[0]` (first by `ordo`) regardless of recipient domain.

**Fix**: Added recipient-domain matching: if recipient's email domain matches an account's domain, that account is preferred. Success message now shows sender email.

### 3. sendmail() return value unchecked
`smtplib.SMTP.sendmail()` returns a dict of failed recipients, which was ignored.

**Fix**: Now checks `sendmail()` return value and raises `ConnectionError` with failed recipients listed if any.

### 4. retposto vidi --html does nothing (initial)
`preview_html()` in A-core has `open_browser` parameter that is intentionally ignored (API compatibility, avoids opening browser in wrong workspace). Caller was passing `open_browser=True` expecting browser to open, but nothing happened.

**Fix**: A-lien now prints the `file://` path after `preview_html()` returns, matching A-encik behavior. No browser auto-open.

### 5. Double .db.db suffix in storage.py
`_path()` returned `str` instead of `Path`, causing `SQLiteDB.__init__` to append `.db` again (lien.db → lien.db.db).

**Fix**: `_path()` now returns `Path`. `get_db()` handles legacy `lien.db.db`→`lien.db` rename.

## Files Changed

**A-lien** (commits on `feat/sendi-signature-konton-subskribo`):
- `src/A_lien/smtp.py` — `use_ssl` param, `SMTP_SSL` branch, `sendmail()` check
- `src/A_lien/service/retposto_sync.py` — `use_ssl=True` when port==465
- `src/A_lien/cli/retposto.py` — domain-based default account selection, sender in success msg
- `src/A_lien/cli/retposto_vidi.py` — show `file://` path, no auto-open
- `src/A_lien/data/storage.py` — `_path()` returns `Path`, legacy rename

**A-vorto** (commit on `main`):
- `src/A_vorto/display_helpers.py` — show `file://` path, no auto-open

**A-papero** (commit on `main`):
- `src/A_papero/service.py` — show `file://` path, no auto-open

**A-encik** (commit on `main`):
- `src/A_encik/_display_entry.py` — removed dead `open_browser` param

## Policy Decision
All modules now follow the same pattern:
1. Generate temp HTML via `preview_html()` / `preview_markdown()`
2. Print `file://` path via `info(tr_multi(...))`
3. Do NOT call `webbrowser.open()`
Rationale: auto-opening browser in the last accessed window is confusing with multiple workspaces.

## Issues
- A-lien #63, #64, #65 — closed
- A-vorto #42 — closed

## Problem
`retposto sendi` said "Mesaĝo sendita" but message not received. Two root causes:

### 1. Missing implicit SSL (SMTPS) for port 465
SMTPClient always used `smtplib.SMTP()` (plain). Account `ron@ronzz.org` used port 465 with `smtp_tls=0`, requiring `smtplib.SMTP_SSL()`. The code had no `use_ssl` parameter.

**Fix**: Added `use_ssl: bool` parameter to `SMTPClient.__init__()`. When `use_ssl=True`, `connect()` uses `smtplib.SMTP_SSL()` instead of `smtplib.SMTP()`. Caller in `retposto_sync.py` passes `use_ssl=True` when port == 465.

### 2. Wrong default account when --konto omitted
Default account selection picked `accounts[0]` (first by `ordo`) regardless of recipient domain.

**Fix**: Added recipient-domain matching: if recipient's email domain matches an account's domain, that account is preferred. Success message now shows sender email.

### 3. sendmail() return value unchecked
`smtplib.SMTP.sendmail()` returns a dict of failed recipients, which was ignored.

**Fix**: Now checks `sendmail()` return value and raises `ConnectionError` with failed recipients listed if any.

### 4. retposto vidi --html does nothing
`preview_html()` in A-core has `open_browser` parameter that is intentionally ignored (API compatibility). Caller was passing `open_browser=True` expecting browser to open, but nothing happened.

**Fix**: A-lien now calls `webbrowser.open(str(path))` explicitly after `preview_html()` returns the path (the recommended pattern per A-core's API docs).

### 5. Double .db.db suffix in storage.py
`_path()` returned `str` instead of `Path`, causing `SQLiteDB.__init__` to append `.db` again (lien.db → lien.db.db).

**Fix**: `_path()` now returns `Path`. `get_db()` handles legacy `lien.db.db`→`lien.db` rename.

## Files Changed

**A-lien** (commit `a451c7a` on `feat/sendi-signature-konton-subskribo`):
- `src/A_lien/smtp.py` — `use_ssl` param, `SMTP_SSL` branch, `sendmail()` check
- `src/A_lien/service/retposto_sync.py` — `use_ssl=True` when port==465
- `src/A_lien/cli/retposto.py` — domain-based default account selection, sender in success msg
- `src/A_lien/cli/retposto_vidi.py` — explicit webbrowser.open()
- `src/A_lien/data/storage.py` — `_path()` returns `Path`, legacy rename

**A-vorto** (commit `ef27704` on `main`):
- `src/A_vorto/display_helpers.py` — `webbrowser.open()` after `preview_markdown()`

## Still Needs Fixing (same `open_browser=True` pattern)
- A-papero `service.py` — `preview_html(html, open_browser=True)` 
- A-encik `_display_entry.py` — `preview_html(html, open_browser=open_browser)`

## Issues
- A-lien #63, #64, #65 — closed
- A-vorto #42 — closed
