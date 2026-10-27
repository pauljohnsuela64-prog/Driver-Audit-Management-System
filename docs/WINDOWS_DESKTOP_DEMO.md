# Disposable Windows desktop demonstration

Run the actual desktop against the actual FastAPI backend using a fresh temporary
SQLite database. No MySQL service, production credentials, migration or grant changes
are needed. The normal application at `python -m desktop` is unchanged.

## Launch from a local PowerShell console

From `C:\BHLI-Audit`, install dependencies if this environment is not already prepared:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-desktop.txt
```

Then launch the complete demonstration with one command:

```powershell
.\.venv\Scripts\python.exe -m scripts.desktop_demo
```

Choose **two different, nonblank passwords of 15–128 characters** at the hidden local
prompts. Use disposable passwords, not real employee passwords. Passwords are not
accepted in command arguments, printed, logged or saved as plaintext. If the console
cannot hide input, the launcher refuses to start; do not pipe/redirect its input.

The desktop opens automatically after fictional data is prepared. Sign in normally:

| Account | Role | Password |
| --- | --- | --- |
| `demo_admin` | ADMIN | The ADMIN password you just chose |
| `demo_auditor` | AUDITOR | The AUDITOR password you just chose |

There is no default password or authentication bypass. Backend password hashing,
sessions, role enforcement, transactions and history use their existing code.

## Suggested manual acceptance path

1. Sign in as ADMIN. The dashboard shows **60 active fictional audits**. Expand and
   collapse navigation; switch Light/Dark; inspect the account menu and My Account.
2. Open Driver Audits. At 25 rows/page, inspect all three pages. Search by driver,
   plate or station, try station/date filters, clear them, and sort both ways.
3. Select a row with the keyboard and press Enter. Inspect all seven fields and
   wrapped/scrollable remarks. Press Escape to return; arrows/Enter should immediately
   operate the restored row. Resize to a compact window and maximize it.
4. Sign out and sign in as AUDITOR. Administration navigation is absent. The dashboard
   still shows all **60** active records; applying **My audits** returns **40** records.
5. AUDITOR-created records retain **Fictional Auditor (original)** as Audited By while
   the current account name is **Demo Auditor**. This demonstrates historical attribution
   without changing any of the seven audit business fields.
6. An incorrect password gives safe feedback. Repeated login attempts use the real
   backend throttling; wait for Retry-After if rate limited. Placeholder modules are
   labeled for a later phase; no desktop audit/account editing is implemented.
7. Close the application. Its demo API stops and the temporary database is removed.
   Re-running creates a new isolated demonstration; previous records/passwords are gone.

Optional helper/remarks, duplicate plate numbers, multiple stations, varied dates,
and a long remarks record are included. Every record is fictional.

## Isolation and verification

The launcher creates its own temporary directory and a literal-loopback server on
an OS-assigned port. It accepts no database path/URL and injects its SQLite engine
explicitly; server `.env` and production connection settings are never consulted.
Data setup uses normal authenticated backend API operations. HTTP calls ignore
environment proxies and refuse redirects, so demo credentials stay on loopback.
All seed sessions are revoked before manual sign-in. SQLite stores password hashes,
not plaintext passwords; Python memory cannot be guaranteed securely zeroed.

Temporary cleanup runs after normal exit and startup/caller failures. No production
configuration files, records or MySQL accounts are read or changed. Model metadata
creates this SQLite schema; this is not a production Alembic/MySQL verification.

For repeatable automated native acceptance with passwords generated only in memory:

```powershell
.\.venv\Scripts\python.exe -m tests.desktop.acceptance_capture
```

This opens the actual UI, uses the same real disposable HTTP API, and captures only
its application window. It verifies role totals, pagination/sort, original attribution,
keyboard return focus, compact/maximized layouts, loading, offline and empty states.
Screenshots and callback diagnostics are saved under ignored
`artifacts/desktop-acceptance/`. The helper closes its window/API after completion.
The existing fictional-transport visual harness remains available for unit-level states.

See [independent acceptance evidence](WINDOWS_DESKTOP_ACCEPTANCE.md) and
[normal desktop configuration](WINDOWS_DESKTOP.md).
