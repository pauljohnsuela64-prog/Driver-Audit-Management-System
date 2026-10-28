# Phase 4A: Android mobile foundation design

**Status:** approved at design checkpoint `b373011`. The subsequent operator assignment authorizes isolated toolchain setup, complete Phase 4A implementation/testing/review and one draft PR. Production changes and release distribution remain excluded.

## 1. Verified baseline, purpose and scope

PR #9 merged into `main` at `c1f7cf678d0bef6027e049a1ee696f42ad66e4a5`. Its [post-merge run](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40612289170) completed successfully with SQLite, disposable MySQL, Windows desktop and Windows package/installer jobs. A clean checkout was safely fast-forwarded to that baseline before creating local `feat/dams-android-foundation`. Prior branches, source and private configuration are preserved.

Build an independent Flutter/Dart Android client for authenticated staff to browse the same shared audits as Windows. Phase 4A includes connection setup, login, list/search/filter/pagination, details, session handling and logout. It preserves all seven fields and existing authorization. `mobile/` currently contains only a placeholder README; no mobile implementation is available to reuse.

Not included: audit mutations/history UI (4B), account administration/password-change/reset UI, dashboard analytics, Excel/PDF, offline synchronization or real-data disk caching, photos/GPS/checklists, notifications, iOS/web/desktop Flutter targets, production deployment or release distribution. Phase 4C owns distributable APK/release readiness. Internal debug builds needed to run development tests are not a distribution release.

See [domain glossary](../../../GLOSSARY.md): account identity, audit ownership and historical Audited By are distinct. The seven fields remain **Driver Name, Helper Name, Audit Date, Station, Plate Number, Remarks, Audited By**. IDs, version and lifecycle timestamps are metadata, not additional business fields.

## 2. Approaches and recommendation

The operator approved the recommended lean approach below; alternatives remain documented for context.

| Approach | Advantages | Cost / assessment |
| --- | --- | --- |
| SDK `ChangeNotifier`/`Listenable`, immutable state, constructor injection; `http` and public-settings storage | Small dependency surface; explicit lifetimes; tests exercise the same interfaces as UI | Requires disciplined cancellation/generation handling. **Recommended for four screens.** |
| Riverpod with repositories and routed providers | Convenient async dependency/lifecycle management; suitable for more features | Additional framework conventions/versioning; not necessary for read-only foundation |
| BLoC/Cubit with layered use cases | Explicit event/state workflow, useful in a larger established team | More files and ceremony than the present workflow warrants |

Use Material 3, typed immutable models and feature view models, with no speculative domain/use-case layer. Use SDK Navigator with a session-gated root and a short route stack; no external deep links in 4A. `go_router` is a reasonable future choice if external/deep-link routing becomes a real requirement, rather than a dependency needed now. Flutter's [architecture recommendations](https://docs.flutter.dev/app-architecture/recommendations) inform the separation; their recommendations are adapted to this smaller scope.

Proposed dependencies: Flutter Material SDK; Dart-team `http` for injectable networking; Flutter-team `shared_preferences` for **origin/version/theme only**; SDK `flutter_test`, `integration_test` and `flutter_lints` for tests. Use Material localization/date formatting rather than adding `intl` solely for dates. Do not add a database, token store, analytics/crash uploader, runtime font downloads, code-generation stack, service locator or connectivity plugin. Actual requests determine reachability.

Before implementation, verify publisher/license/maintenance and Flutter/Android compatibility of each selected package, pin tested direct versions and commit the application `pubspec.lock`. Record SDK revision/checksum and transitive versions. No floating `any`, automatic SDK upgrades or fabricated package-version claims in this design.

### Proposed structure and interfaces (directories are not created now)

```text
mobile/
  lib/app/                 composition, session-gated routing, theme
  lib/core/network/        validated origin, bounded transport, safe failures
  lib/core/settings/       versioned public preferences
  lib/features/auth/      session repository, login state and screen
  lib/features/audits/    immutable audit/page/query, repository, list/details state/screens
  lib/features/settings/ connection and theme screen/state
  lib/ui/core/            field, status panel, audit summary, retry/progress widgets
  test/                   model, transport, session and widget contracts
  integration_test/       real disposable API and Android flows
```

The network module hides URI construction, JSON bounds/parsing, timeouts, redirect rejection and failure sanitization. Session state hides token lifetime and revocation; audit state hides paging/request supersession. Widgets receive view models rather than raw tokens or arbitrary request methods. Real HTTP and fake transports form a test seam; public settings have real/fake storage adapters. Avoid one wrapper per endpoint with no additional responsibility, and avoid parallel API/domain models unless their meanings actually diverge. Apply Codebase Design's small-interface/deep-module principle.

## 3. Roles, attribution and browsing policy

**Recommend admitting both ADMIN and AUDITOR to mobile.** This suits HR and field-auditor browsing and uses existing server contracts; Windows admission remains ADMIN-only. There is no mobile role selector, account directory or account-management route.

The actual `GET /audits` and detail implementation permits **both roles to read all active shared audits**, not just their own. Ownership by stable user ID restricts AUDITOR mutations in the existing backend; it is not a confidentiality restriction on reading. This is a meaningful operator approval point. If field auditors should see only their own records, hold mobile implementation for a separately approved backend authorization design; a client-side Mine filter cannot enforce confidentiality.

In 4A, both roles browse active audits only; the client sends no `include_deleted=true` and has no archive toggle. Backend ADMIN archive access is documented but not exposed by this phase. Unknown roles fail admission with best-effort revocation. Current role/active status is determined by the server on each protected request; the login screen cannot confer permission.

Details display `audited_by_name` exactly as the historical snapshot returned. Never substitute `/auth/me.full_name`, fetch an account to refresh that name, infer ownership from a matching name, or treat an ADMIN-created audit as unattributed. Preserve text plate numbers, including leading zeros and duplicate values. Optional helper/remarks use a clearly labeled em dash; remarks remain plain text with line breaks, not executable HTML or auto-opened links.

## 4. Screens, navigation and visual system

Use the existing owned BHLI monogram and navy/teal identity, adapted to Android rather than copying desktop row density or sidebar. The app opens to Driver Audits after authentication; no placeholder destinations or bottom bar for four unrelated states.

```text
First launch -> Connection -> Login -> Driver Audits -> Audit Details
                    ^          |            |                |
                    +-- Settings <----------+       Back restores list state
                               |
                       Sign out -> Login
```

Authenticated Settings shows identity/role, theme, the read-only connection and Sign out. It does not expose editable endpoint fields until fully signed out. Android Back from list follows normal app exit/background behavior, not a hidden logout or return to a credential form. Back after logout/401 cannot reveal protected routes; clear that route stack.

### A. Login

```text
[BH monogram] BHLI Audit
Sign in to view driver audits
Username [________________]
Password [____________] [Show]
[           Sign in           ]
Inline safe error / progress
Connected to: approved host  [Connection settings]
```

Visible labels, password-manager/autofill hints and paste allowed; password hidden initially with an accessible Show/Hide control. Username trimmed, password preserved exactly, limits follow the login contract (1–100 username and 1–128 password characters, not the new-password minimum). Count Unicode code points consistently with the Python API, not Dart UTF-16 code units; never normalize or trim passwords. One login attempt at a time; no automatic login retry. Spinner and disabled submit while pending, keyboard submit supported, responsive scroll when IME is open. Failed submission keeps username, clears password; leaving the screen, success and disposal clear password controllers. A changed connection cannot reuse an entered password silently.

### B. Driver Audits

```text
BHLI Audit                 [Settings]
Driver Audits
[Driver name v] [Search____________] [Search]
[Dates: Any] [Newest created v] [Clear]
Driver name (two lines when needed)    >
28 Oct 2026 · Station
Plate: 000123
---------------------------------------
[Previous]      Page 1 of N      [Next]
```

Search selector offers Driver name, Plate number, Station; explicit Search/IME action avoids request-per-keystroke. Date-range picker offers inclusive From/To and Clear. Sort options map exactly to newest/oldest created ID and newest/oldest audit date; default `-id`. Applied chips summarize filters. Draft input is separate from the applied query. Applying/resetting filters resets page to 1; details/back restores applied query/page/scroll position without resurrecting another session's data.

Use paged `ListView.builder`, page size 25, at most one loaded page plus the selected detail in memory. Avoid indefinite-scroll ambiguity and unbounded accumulation. Pull-to-refresh and a visible Refresh alternative refetch page 1 with current filters. Loading first page uses a labeled progress state; transitions are nonblocking. Empty state distinguishes no audits from no filter matches and offers Clear filters. Offline/timeouts show Retry, not an empty list. Previously visible data may remain in RAM only with a prominent stale/not-refreshed indicator; it is never presented as current after a failed refresh.

### C. Audit Details

```text
[Back] Audit details
Record #123
Driver Name       Fictional Driver
Helper Name       —
Audit Date        28 Oct 2026
Station           Fictional North
Plate Number      000123
Remarks
Long, wrapping plain text...
Audited By        Original recorded name
```

Fetch detail by ID instead of trusting the list summary as the final record. All seven labels remain readable in one scrollable column; optional two-column label/value layout only when width and text scale permit it. Original name remains visible, long content wraps, screen-reader order follows visual order. No edit/delete/history/export buttons or disabled future-feature placeholders. A newly archived/missing record returns 404: clear unavailable detail and offer Back/Refresh; never fabricate an empty record. Keep ETag/version metadata in the typed result for future 4B without issuing mutations now.

### D. Settings / Connection

Signed-out first launch shows a required API-origin field, Test connection, Save, and safe status. No implicit production or emulator default. Persist only validated origin, schema version and theme in one versioned JSON preference value using `SharedPreferencesAsync`. A typed edit invalidates old health feedback; either lock editing during Test or bind the result to the exact tested origin. Await the write before switching effective connection settings; an explicit write failure leaves the previous effective origin unchanged. This is not a crash-durable/ACID storage guarantee: the [plugin documents asynchronous persistence](https://pub.dev/packages/shared_preferences). Missing/corrupt settings after a crash require connection setup again, never a fallback server or restored credential. No critical account/audit data relies on preferences.

Authenticated settings instead shows name/role and a read-only host, theme System/Light/Dark, and Sign out. During login/logout the connection is also locked. Endpoint changes recreate transport/session scope and invalidate pending work, never forwarding an existing bearer to a new origin. Health is unauthenticated and validates exactly `{"status":"ok"}`; it proves basic reachability/contract only, not database schema, account validity or production readiness.

### Styling and accessibility

Reuse semantic desktop colors, mapped to Material `ColorScheme`/theme extensions:

| Token | Light | Dark |
| --- | --- | --- |
| Background / surface | `#F1F5F9` / `#FFFFFF` | `#0B1220` / `#111C2E` |
| Primary / on-primary | `#0F766E` / `#FFFFFF` | `#2DD4BF` / `#0B1220` |
| Main / secondary text | `#0F172A` / `#475569` | `#F1F5F9` / `#B8C5D6` |
| Outline / focus | `#64748B` / `#0F766E` | `#71839B` / `#5EEAD4` |
| Error | `#B91C1C` | `#FCA5A5` |

Use Android/Material system typography (Roboto/fallbacks), not a copied Segoe UI font or network font request. Proposed sizes: 24sp screen heading, 18sp record title, 16sp body/input and 14sp supporting text; honor system text scaling without hard height limits. Use consistent Material outline icons, minimum 48dp touch targets, 16dp phone gutters and 4/8dp spacing. Audit cards start around 96dp and grow for wrapped names/text; desktop's 38-logical-pixel rows are not a mobile touch target.

Respect safe areas, edge-to-edge system bars, IME insets, rotation and reduced motion. Constrain reading width around 720dp on larger devices; no second master/detail pane required for 4A. Verify 320dp phone width through tablet/landscape and 200% text scaling; use `LayoutBuilder`, not device-name tests. Text contrast must reach 4.5:1; meaningful boundaries/focus 3:1. Verify composed Material state overlays in both themes rather than assuming hex pairs alone pass. TalkBack labels, focus traversal, selected filter semantics and announced errors/progress are acceptance requirements.

UI UX Pro Max's Flutter lazy-list/adaptive-layout and accessible-authentication guidance was applied. Its two design-system synthesis queries returned marketing-page patterns; those were rejected, not persisted or treated as mobile layout requirements. The established BHLI palette and native Material guidance control this proposal.

## 5. REST and typed data contract

Code references: `backend/api/auth.py`, `backend/api/audits.py`, `backend/api/dependencies.py`, `backend/schemas/auth.py`, `backend/schemas/audit_api.py`, `backend/services/auth.py`, `backend/services/audits.py`, `backend/main.py`.

| Operation | Contract used by 4A |
| --- | --- |
| `GET /health` | No bearer; exact status object; safe connection feedback |
| `POST /auth/login` | JSON username/password -> `access_token`, `token_type=bearer`, UTC `expires_at` |
| `GET /auth/me` | Bearer -> numeric ID, username, full_name, ADMIN/AUDITOR role; no `is_active` field. A disabled account is rejected by protected requests. |
| `POST /auth/logout` | Bearer -> 204; no body parsing |
| `GET /audits` | `items`, `total`, `page`, `page_size`; query keys `driver_name`, `plate_number`, `station`, `date_from`, `date_to`, `sort`, `page`, `page_size`; no invented generic `q` parameter |
| `GET /audits/{id}` | Seven fields plus ID/version/identity/lifecycle metadata; quoted ETag header, e.g. `"3"` |

The server permits page 1–10,000, size 1–100, search length 1–200; blank searches are omitted. Date strings are valid Gregorian `YYYY-MM-DD`, years >=1000; From cannot exceed To. Encode through URI query-parameter utilities, not concatenation. AND semantics apply if multiple backend filters are used; there is no cross-field OR search. Station matching is substring, not a separate station directory. No `/users` request is needed to render attribution or browse audits.

Use immutable `AuditRecord`, `AuditQuery`, `AuditPage`, `AuthenticatedUser`, `SessionLease` and a typed failure result. Preserve plate/name/remarks Unicode as strings; nullable optional fields are distinct from malformed required fields. Validate positive IDs/version, integer paging fields, nonnegative totals, page-size constraints, maximum returned items and essential response types. Returned page/page-size must match the request, with no more items than that size. Parse full JSON models once at the data interface; widgets do not cast maps. Unknown additive metadata can be ignored; absent required business fields, unknown roles or malformed pagination produce a safe protocol error, not silent default values.

`audit_date` is a calendar value, never converted through UTC/local midnight. Session/lifecycle timestamps require explicit offset/UTC parsing and are normalized to UTC internally. Sorting uses server ordering and its ID tie-breaker. Offset pagination is not a snapshot: concurrent inserts/archives may change totals and move records across pages. Never promise a stable total, deduplicate records to conceal inconsistencies or silently combine pages. If a page empties after a concurrent change, offer reload from page 1.

Initial request budget: page size 25, response body <=2 MiB, no more than 100 items accepted, 20-second total request deadline including body consumption, bounded error-body parsing and one current read per screen. Dart futures alone do not enforce body size/cancel sockets: implement streamed byte limits and close/abort the request/client on deadline or cancellation. Do not automatically retry login/logout; reads retry only by explicit user action in 4A. Closing a request does not prove a server-side operation was canceled.

All server errors use `{"error":{"code":"...","message":"..."}}`, not FastAPI's default `detail`. Map 401 to session invalidation; 403 to forbidden without automatic logout; 404 to unavailable; 422 to validated-input feedback; 429 to a visible wait with a bounded `Retry-After`; 500/503 to retryable service feedback. Malformed/non-JSON/HTML error bodies use fixed safe text. Do not display arbitrary response HTML, URLs, raw exception strings, credential input or request dumps.

## 6. Session, lifecycle and transport security

Tokens are opaque, not JWTs. Login obtains the bearer and server expiry, then `/auth/me` validates identity before opening protected routes. Keep both only in process memory. There is no refresh-token endpoint: expiry, revocation, password reset/change, role changes or deactivation require normal login again. Backend expiry is currently eight hours from issue; honor the response instead of hard-coding eight hours into clients. Local expiry checks improve feedback but server authorization is authoritative.

Use a session/origin generation on every request. Logout, 401, endpoint change, account switch and app teardown invalidate previous generations and clear loaded audit data and protected navigation. A late response cannot repaint a closed screen or restore an old session. An old session's 401 cannot log out a newer session. A second search/page request supersedes the first; completion handlers verify both request identity and session generation before modifying state. Dispose listeners and avoid notifying disposed view models.

Explicit logout locks login/connection transitions, captures the old origin/token for one bounded revocation attempt, clears local protected state immediately, then permits login/settings when that attempt completes or times out. Network failure still signs out locally but must say server revocation could not be confirmed; the inaccessible token may remain valid server-side until expiry. A late successful login after user cancellation must never be adopted and should be revoked best-effort using its original endpoint. Do not store a failed revocation token on disk.

On app background/inactive, conceal protected content and password fields; no background polling. On resume after a genuine pause, recheck expiry and `/auth/me` before revealing records or fetching fresh data. Temporary Android route/keyboard transitions must not cause duplicate login loops. Process death/restart returns to sign-in because no token is restored. Widgets/Android saved-state restoration must not persist passwords, tokens or business records; app-switcher previews must not expose protected data. Plan a small reviewed Android window-security adapter (`FLAG_SECURE` where supported), tested with fictional data; do not claim it guarantees privacy on every OEM or compromised device.

Only a normalized origin is configurable: HTTPS scheme, host and optional valid port; no userinfo, non-root path, query, fragment, whitespace/control characters or URL embedded credentials. Bound input to 2048 characters. Build API paths internally; no arbitrary URL from record content. Reject redirects rather than automatically forwarding credentials or following a downgrade. Never install a permissive `badCertificateCallback`, trust-all `HttpOverrides`, proxy capture CA or production certificate in a build. Keep normal chain/hostname validation enabled. No certificate pinning for 4A: use trusted server certificates and test expiry/untrusted/wrong-host failures. Private enterprise CA support needs a separately specified trust/provisioning decision and actual Android/Dart verification.

Release code denies all cleartext origins. A distinct internal debug-only fixture policy may allow **only loopback** (`127.0.0.1`/`localhost`, explicit port), using ADB reverse; no public/LAN HTTP or arbitrary `10.*` exception. Validate this in Dart as well as Android manifests: Android network-security XML alone must not be assumed to constrain Dart-owned sockets. No debug exception or test CA is packaged into a future release. `INTERNET` is the only planned network permission; camera, location, contacts and broad storage permissions are unnecessary. Origin/theme preferences are non-secret but should be excluded from Android backup/restore and validated on load; no automatic production connection after restore.

## 7. Development environment and networking

Read-only inspection on 2026-10-28 found VS Code and Java **1.8.0_401** on PATH. Flutter, Dart, `adb`, emulator and `sdkmanager` were absent from PATH; Android Studio, default Android SDK and common Flutter directories were absent; no Dart/Flutter VS Code extensions were found in the normal extension folder. This is not an exhaustive search of custom installations. The machine has an i7-13700HX and 16 GB RAM. WMI processor virtualization flags were false while `HypervisorPresent` was true; do not infer that firmware changes are required or enable features from those results. Emulator acceleration still needs its actual diagnostic. No toolchain, Python, Java or PATH change was made.

Recommended baseline: **Flutter stable 3.47.x with its bundled Dart 3.13.x**, Android Studio **Rabbit 1 / 2026.2.1** as the Android tool manager and VS Code as the main editor. Official manual/API pages identify a 3.47.5 candidate, but newest patch/bundled Dart patch could not be authoritatively pinned from the release manifest during research (manifest request returned 404). Before installation, resolve the exact current stable archive, bundled Dart revision and SHA-256 from official metadata; record a tested reproducible pin, not a floating channel or an independently installed Dart SDK. This is an implementation-readiness check, not permission to install now.

Propose **minimum Android API 24 (Android 7.0)** to match the current Flutter support floor. This compatibility minimum is not a production endorsement of unsupported/unpatched phones; the operator must confirm the actual device fleet and managed-device/security policy. Start with Android SDK platform/build tooling API 36 per Flutter setup guidance; use the selected Flutter template's supported compile/target/AGP/Gradle/NDK combination and test against API 36 plus the current supported API 37 where available. Final target SDK and Play/distribution policy are revalidated in 4C, not inferred from minSdk.

After design approval and explicit environment setup authorization: obtain official Flutter archive, Studio, SDK Platform/Build-Tools, command-line tools, Platform-Tools/ADB and an x86_64 emulator image; install NDK/CMake versions only as required by that pinned Flutter template/toolchain. Use Studio's compatible bundled JDK/JBR or an explicitly selected compatible JDK (Java 17+); the current Java 8 PATH entry is not an Android build JDK. Verify with `flutter doctor -v`, `flutter analyze --suggestions` where applicable, `flutter devices`, `adb devices` and emulator acceleration diagnostics. Do not replace Python or unrelated Java/PATH entries. Keep `local.properties`, SDK paths, local launch origins and any signing material ignored.

Flutter's documented SDK path restrictions matter because this Windows username contains spaces: choose an approved writable no-space SDK location, not an assumed `%USERPROFILE%` path. Configure only project/session-specific SDK/JDK paths. Android licenses require operator acceptance. With 16 GB RAM, keep emulator load modest; a physical test phone is a valid early route if acceleration is unavailable. SDK installation, enabling WHPX/virtualization, hardware changes and USB authorization need deliberate operator action, not this design task.

The emulator's `localhost` is the Android guest; `10.0.2.2` aliases Windows host loopback. A physical phone's localhost is that phone, not Windows; it cannot use the emulator alias. Preferred fictional setup: temporary API binds only Windows `127.0.0.1:<port>`, then `adb -s <test-device> reverse tcp:<port> tcp:<port>` and a debug origin `http://127.0.0.1:<port>`. Remove that device's reverse rule after testing. This works only with the explicit debug loopback policy; release configuration rejects it. If testing HTTPS through `10.0.2.2` or a LAN hostname, certificate identity/trust must match the actual origin; never bypass validation or expose a fixture with `0.0.0.0` just to make networking work.

Use VS Code Flutter/Dart extensions, select the Android device and debug from `mobile/`; hot reload is development-only. Physical devices require developer mode, USB debugging, a trusted USB host and possibly OEM Windows drivers. Test actual reachability/TLS in Dart, not just a Windows browser. Do not assume Android XML/debug CA configuration is consumed identically by Dart `IOClient`.

## 8. Implementation checkpoints after approval

1. **Environment and contracts:** operator-approved SDK/JDK/device setup; verified exact pins/checksums/licenses; record `doctor`/acceleration/device evidence. Scaffold Android-only Flutter under `mobile/` only after approval. RED/GREEN origin, date, audit/page/error parsing and session-generation tests; review manifest/backup/permissions defaults. No backend changes.
2. **Connection, authentication and privacy:** fake transport/storage adapters plus real bounded HTTP; first-launch settings; login/me; memory-only session; canceled-login revocation, logout, expiry/401 and stale-response handling; background privacy/resume checks; theme. Meaningful verified commit.
3. **Read-only audit UI:** list/query state, search/date/sort/paging/refresh; details and immutable attribution; accessible reusable status/error widgets. Verify both roles and late/out-of-order responses; no mutation/history/account-management calls. Meaningful verified commit.
4. **Integration and native review:** temporary fictional backend with ADMIN and AUDITOR accounts, read scenarios across desktop-created audits, emulator and physical-device evidence, light/dark/small/large text/rotation, TalkBack, TLS and lifecycle checks. Independent architecture/security/UI review; fix genuine defects with regression tests.
5. **Verification and later publication:** full relevant Flutter tests plus existing Python/Windows/SQLite/MySQL/installer safeguards before any eventual PR. Add isolated mobile CI as approved implementation work, meaningful commits and one draft 4A PR only when separately authorized; never infer publication authorization from this design checkpoint. 4B/4C remain separate assignments.

## 9. Verification and CI strategy

| Layer | Required evidence during implementation |
| --- | --- |
| Pure models/settings/transport | Strict schemas, nullable/Unicode/long remarks/text identifiers, calendar vs UTC, body/timeout limits, escaped queries, redirect rejection, corrupt preferences and failed writes |
| Session concurrency | Both roles, wrong credentials, unknown role, inactive account, expiry/revocation, logout failure, canceled login, old 401 after new login, origin change while signed out, no token/body logs or persistence |
| Audit state | All search modes/date limits/sorts, reset-to-page-one, next/previous/refresh, total changes/empty pages, duplicate plates, server ownership/attribution unchanged, missing/archived detail, superseded responses and disposal |
| Widget/accessibility | Loading/empty/offline/protocol/error states, password visibility/paste/autofill, focus/error announcement, 48dp targets, both themes, large text, safe areas/IME, Back behavior and no protected-state restoration |
| Real API | Disposable SQLite fixture plus guarded dedicated MySQL only where relevant; fictional ADMIN/AUDITOR credentials chosen in hidden local prompts or protected CI environment; no real data. Existing desktop demo seeds a legacy AUDITOR with a generated unshown password, so design an explicitly usable mobile fixture rather than assuming its credentials. Reuse normal bootstrap/user/login API and temporary fixture infrastructure; no shipping bypass. |
| Native Android | Emulator and actual phone; supported floor/current API where available; actual TLS trust/wrong-host/untrusted/expired cases; pause/resume, process death, task previews, rotation and no user data written to disk. Record unavailable devices/API levels as unverified, not passes. |

Plan `dart format --output=none --set-exit-if-changed`, `flutter analyze`, `flutter test` and targeted `integration_test` flows. Prefer behavior at repository/view-model interfaces and widget/user-visible flows over tests mirroring implementation. Focused TDD during each checkpoint, full regression before eventual publication; no repeated expensive unchanged suites for this documentation-only task.

Mobile CI should be a separate least-privilege workflow/job, pin Flutter revision/checksum and lock dependencies, use disposable fixtures and no production secrets, signed keys or privileged PR triggers. Start with formatting/analysis/unit/widget tests; add bounded emulator integration when runner acceleration is verified. Existing four backend/Windows/package jobs, triggers, runtime grants and dependency environments remain intact. No signed/public APK upload in 4A. Native-device testing is not replaced by a green unit test job or a future APK build.

## 10. Risks, approval decisions and production gates

Design approval should explicitly cover: both roles reading **all active shared records**, active-only mobile browsing, memory-only sessions/re-login after process death, the lean view-model architecture and primary Audits navigation, API-24 compatibility floor, and debug-only loopback networking with ADB reverse. If any differs from operator intent, revise before implementation.

Builder choices after approval: verified stable patch and package pins, exact file names and minor spacing, compatible generated Gradle/JDK versions, and request-cancellation mechanics meeting the limits above. They do not authorize broader roles, persistent credentials, offline data, LAN cleartext, SDK installation without setup authorization or unrelated features.

Remaining readiness gaps: no verified Android toolchain/emulator/device on this machine, exact stable patch/paired Dart pin unresolved, acceleration and physical-device availability unknown, and no native Android visual/TLS evidence yet. These block claims of implemented/tested Android behavior, not preparation of this design.

Production remains separately gated: trusted HTTPS/network restrictions, service ownership, backups/restore, account provisioning and the approved 0001-to-0002 migration/runtime activity grants/startup window. No production SQL, grants, records, credentials, certificates or server configuration were inspected/copied/changed here. Mobile packaging does not supply an API/database or fix deployment readiness. No signed/public release or Play publication is authorized.

## 11. Research and independent review

Research date: 2026-10-28, Asia/Manila. See [official-source research](../research/2026-10-28-phase4a-android-foundation.md). Additional primary references: [Flutter architecture](https://docs.flutter.dev/app-architecture/guide), [supported platforms](https://docs.flutter.dev/reference/supported-platforms), [Android setup](https://docs.flutter.dev/platform-integration/android/setup), [networking cookbook](https://docs.flutter.dev/cookbook/networking), [Dart HTTP client](https://api.dart.dev/dart-io/HttpClient-class.html), [Android security configuration](https://developer.android.com/privacy-and-security/security-config), [emulator host addressing](https://developer.android.com/studio/run/emulator-networking-address), [ADB reverse](https://developer.android.com/develop/ui/views/layout/webapps/access-local-server), [VS Code setup](https://docs.flutter.dev/install/with-vs-code).

Two fresh independent reviewers completed architecture/security and builder/mobile-UX checks. The security reviewer verified roles, sessions, pagination, errors, dates and ETags against backend code and found no design blockers. The builder reviewer found nothing important left unanswered and no material touch/accessibility/scope contradiction; the operator decisions in section 10 remain explicit approval points. Final author clarification distinguishes preference-write success from crash durability, records the active hypervisor observation and makes Unicode/pagination validation precise. Application implementation remains blocked until the operator approves this specification.
