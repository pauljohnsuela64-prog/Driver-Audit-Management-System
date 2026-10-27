# BHLI Audit disposable Windows demonstration

From a local PowerShell console in `C:\BHLI-Audit`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m scripts.desktop_demo
```

Choose two separate nonblank passwords of 15?128 characters in the hidden prompts.
Do not redirect or pipe input: the launcher fails closed if hidden input is unavailable.
The application opens automatically against a temporary loopback API and SQLite database.
No production configuration, MySQL database, grants or migration execution is used.

| Login | Access | Password |
|---|---|---|
| `demo_admin` | First HR administrator | First password you chose |
| `demo_admin2` | Second HR administrator | Second password you chose |

There is no default password or authentication bypass. Both accounts authenticate
normally and have distinct stable IDs. A separate legacy AUDITOR fixture has a
random memory-only password available only to the automated acceptance helper;
its account is never promoted or deleted. The generic backend still supports AUDITOR,
while the Windows desktop rejects that role and revokes newly issued tokens.

## Manual acceptance

1. Sign in as either ADMIN. Check the three destinations: Dashboard, Driver Audits,
   My Account. New Audit is available immediately on Dashboard, including offline/empty states.
2. Inspect both tables: 38 logical px rows instead of 44, reduced heading padding,
   balanced widths and subtle alternating rows. Try arrows, Home/End, Enter, scrollbars,
   compact/maximized windows and both themes. Advanced audit filters start collapsed.
3. Create an audit with required fields and optional helper/remarks. Audited By is
   server supplied. Edit, compare stale versions when another client saves, soft-delete
   after confirming identity, and inspect chronological history. Duplicate plates are valid.
4. Sign in as the other ADMIN and create another record: its original attribution
   belongs to that distinct account. Of the 60 active seed records, 20 belong to the
   first ADMIN and 40 to the second. Second-admin seed snapshots retain
   **Fictional HR Two (original)** despite the current name **Demo Administrator Two**.
5. In My Account expand Manage Admin Accounts. Add a third administrator if desired:
   the interface is optimized for one or two people, with no artificial account cap.
6. Reset another admin using your current password plus the replacement/confirmation.
   Their existing sessions stop working; resetting a disabled account leaves it disabled.
7. Disable another admin after the explicit identity confirmation. Self-deactivation
   and losing the last active ADMIN are blocked by the backend. Audits and history remain.
   This desktop intentionally has no role editor, activation control or account deletion.
8. Change My Password: success revokes all your sessions and returns to normal login.
   Password fields clear on submission, navigation, appearance changes and sign-out.
9. As ADMIN, enable Include deleted in audit filters. One archived fictional example
   already contains CREATE/UPDATE/DELETE history. Close the app to remove all demo data.

Account actions have no idempotency-key contract. After an ambiguous response, do not
assume rollback or automatically replay: refresh account/status information and make
an explicit decision. A password may already have changed. Audit creation retains
its existing UUID/payload retry safeguard; leaving the application loses memory-only
retry state. No real records are used by this demonstration.

## Repeatable native acceptance

```powershell
.\.venv\Scripts\python.exe -m tests.desktop.admin_acceptance_capture
```

This generates credentials in memory, uses the real disposable HTTP API, and checks
legacy denial, two ADMIN identities, adding/resetting/disabling a third admin, own
password change, audit CRUD/history, themes, compact/maximized windows and scaling.
Screenshots contain fictional data and empty password forms only; reports are saved
under ignored `artifacts/desktop-phase3c/`. Earlier phase capture helpers remain
available with updated administrator logins. Actual other OS DPI settings, mixed-monitor
transitions and assistive technology require separate manual acceptance.
