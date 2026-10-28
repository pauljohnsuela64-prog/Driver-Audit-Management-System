# Phase 4A Android Foundation Implementation Plan

> Execute with superpowers:subagent-driven-development and TDD; user authorized all checkpoints, independent review and draft publication. No repeated approval gate.

**Goal:** Ship a tested read-only Android client for BHLI Audit's existing authenticated REST API.
**Architecture:** Material 3 views consume immutable feature state. A bounded HTTP module, public-preference adapter and generation-scoped session isolate transport/lifecycle behavior. Android-only project, no backend coupling.
**Tech stack:** Official stable Flutter/Dart, compatible Android SDK/JDK, `http`, `shared_preferences`; exact resolved pins recorded before verification.
**Spec:** docs/superpowers/specs/2026-10-28-phase4a-android-foundation-design.md (approved b373011).

## Global constraints
- Stay in C:\BHLI-Audit on feat/dams-android-foundation; preserve approved design/history and private configuration. No production operations or unrelated tool upgrades.
- Both ADMIN/AUDITOR browse shared active records; Windows remains ADMIN-only. Preserve exactly seven fields and historical attribution. No mutations/history/account management/offline caching.
- Memory-only bearer and records; no redirects, certificate bypass or remote HTTP. Separate debug-only loopback fixture policy. No production keys/certificates.
- Android minimum API24; Material3 navy/teal, light/dark, 48dp targets and scalable accessible text.
- Meaningful tested commits; one draft PR, all applicable hosted CI, no merge.

## Review focus
- A stale login/read/401 cannot adopt or clear a newer session; scope cancellation by generation.
- Settings changes cannot redirect a live token or report a stale health result as current.
- Timeouts/body limits must close streamed requests; no secret exception/request logging.
- Android pause/resume/process death/back navigation cannot reveal another session's data.
- Dates and Unicode/leading-zero plates remain exact across API, filters and rendering.

## Task 1 — isolated toolchain and foundation
Files: `mobile/` Android-only Flutter scaffold; `docs/ANDROID_DEVELOPMENT.md`; ignored `local/android-toolchain/`; `.gitignore` mobile-generated exclusions as required.
- [ ] Resolve official Flutter archive/revision/checksum and bundled Dart; install only isolated authorized tools, compatible JDK/SDK. Do not modify unrelated PATH or Java8/Python.
- [ ] Record doctor/device/acceleration outputs; scaffold Android only and pin dependencies/lockfile.
- [ ] Verify generated application test/analyzer baseline, minSdk24 and source-only ignore rules. Commit coherent setup with the next usable contract milestone.

## Task 2 — typed transport, settings and session
Files: `mobile/lib/core/{network,settings}/`, `mobile/lib/features/auth/`, `mobile/lib/features/audits/{models,repository}.dart`; corresponding `mobile/test/`.
Interfaces: `ApiOrigin.parse(raw, allowDebugLoopback)`, `ApiFailure(status,code,message)`, `AuditRecord.fromJson`, `AuditQuery`, `AuditPage`, `ApiClient.health/login/me/logout/audits/audit`, injectable transport; `SessionController` with generation/origin lock and memory-only lease; public settings abstraction with fake/platform adapters.
- [ ] RED tests: origin validation, response bounds/redirects/errors, Unicode/calendar/nullable fields, exact queries/paging, token types/expiry and safe failures.
- [ ] Implement minimum typed interfaces; GREEN focused contracts, no speculative layers.
- [ ] RED session race tests: canceled login, old401/newlogin, logout failure, expiry, endpoint switching, role admission; implement generation transitions and bounded revocation. Verify and commit.

## Task 3 — Material screens and lifecycle
Files: `mobile/lib/app/`, `mobile/lib/features/{auth,audits,settings}/` view models/screens, `mobile/lib/ui/core/`, `mobile/android/app/src/.../MainActivity.kt`, widget tests.
Consumes Task2 typed interfaces; composition owns adapters and route/session lifetime. Android privacy adapter exposes window protection, no business logic/native database.
- [ ] RED widget/state tests for first-launch connection, test/save/write error, locked origin, login validation, show/hide, loading/error and both-role admission.
- [ ] Implement responsive connection/login/settings with semantic themes and password disposal; native privacy flags and no state restoration of credentials/data.
- [ ] RED audit tests for search/date/sort/next/previous/refresh, superseded results, empty/stale/offline, detail7fields/snapshot/404; implement list/details and safe Back/logout.
- [ ] Verify both themes, 320dp/large text, focus/targets/IME and lifecycle/session reset; commit verified UI milestone.

## Task 4 — real fictional API and Android acceptance
Files: `scripts/mobile_demo.py`, `mobile/integration_test/`, integration-contract/widget tests, docs/images/android-phase4a/, ignored artifacts.
- [ ] Test developer-only loopback fixture using normal bootstrap/auth/users/audits with fictional ADMIN/AUDITOR; no shipping bypass or production env loading.
- [ ] Verify real API parsing/filter/paging/roles/logout/401 with seeded Unicode/null/long remarks; ADB reverse for isolated debug localhost only.
- [ ] Run available emulator/physical native debug build, capture actual UI, inspect both themes/size/back/privacy/connection errors. If unavailable record actual evidence and limitation, never fake screenshots/passes.
- [ ] Independent engineering/security and UI review; reproduce/fix verified defects with focused coverage; commit verified acceptance fixes.

## Task 5 — CI, regression and publication
Files: `.github/workflows/mobile-tests.yml`, toolchain provenance/pins, `docs/ANDROID_DEVELOPMENT.md`, verification report, plan ledger.
- [ ] Separate least-privilege Android formatting/analyzer/unit/widget/build CI with pinned SDK and dependency caching; preserve existing four jobs, no secrets/release signing.
- [ ] Full Flutter format/analyze/tests; available Android acceptance; affected Python desktop/auth/API regressions, then hosted full existing matrix.
- [ ] Inspect cumulative diff/staged secrets, commit docs/evidence, clean tree, normal push, exactly one draft PR to main, verify final hosted jobs and artifact provenance; remain unmerged.

## Recovery ledger

Implementation checkpoint 2026-10-28: Tasks1–4 completed with documented native
acceptance limitations in docs/ANDROID_VERIFICATION.md. Toolchain reused after
interruption. Full Flutter60/defaultPython514/MySQL518 passed; Android16/API36
native real-API scenario passed and six screenshots independently reviewed.
Source-review corrections are preserved in 530a4ff after the client checkpoint
32953e3. Task5 local CI validation complete; draft publication and hosted results
are the remaining gate. No production modifications or Android mutations.
Persistent ignored work ledger: `local/phase4a-progress.md`. Record actual commands/results/commit SHAs and independent-review findings there as work proceeds.
Ruling: work in the explicitly requested clean feature checkout rather than create another worktree; avoids splitting existing local configuration/tools and honors C:\BHLI-Audit workflow. No main implementation commits.
Ruling: no repeated plan approval; explicit user attachment already authorizes complete implementation and draft publication.

Preflight: Tasks1/2 share SDK/pubspec only (root owns scaffold/dependencies; contract implementer owns declared Dart files/tests). Tasks2/3 share typed interfaces (documented handoff required before UI). Tasks3/4 share routes/lifecycle (native acceptance uses production UI, no test bypass). Tasks4/5 share fixture entry and CI (test-only loopback, no real credentials). Each task agrees with global constraints; no schema/backend/grant changes planned.
