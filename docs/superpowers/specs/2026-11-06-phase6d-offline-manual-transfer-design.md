# Phase 6D — Offline manual audit transfer

Status: proposed design for operator review; implementation has not begun.
Baseline: `1759a5dc2057221bdb040379d397eeaec0606824`.
Branch: `feat/dams-offline-manual-transfer`.

## Purpose and scope

Exchange selected audits and their complete available history between the existing
Android and Windows offline applications using `.bhlitransfer` files. No server,
Internet, account login, API or MySQL is involved. Preserve seven business fields,
immutable original attribution, local profiles, online applications and public releases.
This remains fictional-data development software. Transfer is neither backup/restore
nor synchronization: edits to an existing imported identity are never merged.

## Approaches and recommendation

1. **Identity registry plus schema v2 (recommended).** Keep the singleton current
   local profile; add a registry of profile UUIDs for record/event references.
   Existing original names remain snapshots, not mutable registry attributes.
2. Remapping incoming identities to the local profile would falsify attribution.
3. Removing profile foreign keys would weaken integrity. Raw SQLite interchange
   would also couple platform metadata and bypass package validation.

The recommendation is the author's proposal, not an already approved operator decision.

## Findings from the current source

Both stores have schema version 1 and four application tables: `app_meta`,
`local_profile`, `audit_records`, `audit_events`. Audit profile IDs reference
`local_profile(id)`. Events preserve actor IDs/names and full before/after snapshots.
Windows checks exact owned table SQL, application identity and database integrity.
Android currently checks table names/columns and foreign keys less strictly and must
validate actual v1 constraints before attempting an upgrade. Android owns a separate
`android_metadata` table; Windows must continue rejecting a raw Android database.
Windows work is serialized on its database-owning thread; Android serializes admitted
operations. Existing create retries use UUIDs; revisions/history must remain intact.

## Schema v2 and safe migration

- Add `auditor_identities(id TEXT PRIMARY KEY NOT NULL)`; names remain exclusively
  in local profile and historical snapshots. A renamed profile does not conflict
  with an earlier name associated with the same identity.
- Keep `local_profile` singleton and its UUID unchanged. Register its UUID on
  creation; importing identities never changes this singleton.
- Rebuild `audit_records` with its existing columns, values, insertion sequence,
  indexes and constraints; point `profile_id` at `auditor_identities(id)`.
- Rebuild `audit_events` preserving all IDs, revisions and snapshot JSON. Add
  `actor_profile_id REFERENCES auditor_identities(id)` while retaining audit FK,
  unique `(audit_id,revision)`, action and revision constraints.
- Add `transfer_receipts(package_id TEXT PRIMARY KEY NOT NULL,
  content_sha256 TEXT NOT NULL, source_installation_id TEXT NOT NULL,
  imported_at TEXT NOT NULL, imported_count INTEGER NOT NULL CHECK(imported_count>=0))`.
- Seed registry IDs from the local profile, audit origins and historical actors
  after validating UUIDs and existing data. Never invent/reassign an origin.
- Validate v1 identity, exact table/constraint/index ownership, rows, complete
  event chains, quick-check and foreign keys before migration. Reject altered,
  foreign, corrupt or newer schemas without repairing or resetting them.
- In one transaction create replacement tables, copy records/events into them,
  verify counts and FKs, drop old events then old records, rename replacements,
  recreate indexes and update `user_version=2` last. Keep FKs enabled. Account for
  SQLite's automatic FK-reference updates on rename in expected schema checks.
- Any failure, including COMMIT, rolls back schema, metadata and rows. Never
  delete/replace the database file. Fresh installs create empty v2 directly.
- Fixtures must exercise populated v1 upgrades, renamed profiles, archived audits,
  malformed constraints, foreign metadata, FULL/locked/commit failures and restart.
  Old v1 applications refuse v2; users must upgrade both transfer-capable clients.

## Transfer version 1 wire contract

ZIP contains exactly three regular entries, in this order: `manifest.json`,
`audits.ndjson`, `events.ndjson`. No directories, extra entries, links, encryption,
ZIP64, multidisk archives or executable payloads. Writers use ZIP STORE, reducing
decompression complexity and avoiding an extreme-compression compatibility trap.
Readers initially accept only STORE. ZIP metadata is not content identity.

Canonical JSON rules shared by Python and Dart:

- UTF-8 without BOM; JSON text uses ASCII escapes for non-ASCII code points,
  including surrogate pairs for supplementary characters. Reject unpaired
  surrogates, duplicate keys and invalid UTF-8 before normal decoding loses them.
- Object keys recursively sorted by ASCII code point; compact separators, no
  insignificant whitespace, no slash escaping. Escape quote/backslash and control
  characters deterministically (`\b`, `\t`, `\n`, `\f`, `\r`, otherwise lowercase
  `\u00xx`). All other ASCII remains literal. Unicode values round-trip unchanged.
- Only strings, objects, arrays, null, booleans and integers are accepted; reject
  floating point, NaN and Infinity. Integer range is 0 through 2^53-1 where used.
  A boolean never satisfies an integer field. Business field lengths count Unicode
  scalar values using existing platform normalization rules; import rejects rather
  than silently normalizes invalid or non-normalized values.
- UUIDs are existing canonical lowercase UUIDv4. Dates are `YYYY-MM-DD`.
  Timestamps are UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`, year 1000–9999.
  Convert existing UTC/offset database timestamps to this wire representation;
  do not require rewriting historical database JSON.
- Each NDJSON line is one canonical object followed by LF; zero rows means zero
  bytes. Manifest is one canonical object followed by LF.
- Audits sort by UUID ascending; events sort by audit UUID then revision ascending.
  Local `seq` values never cross devices.
- Audit keys: existing six editable field keys plus `id`, `profile_id`,
  `audited_by_name`, `created_at`, `updated_at`, `revision`, `archived_at`.
  Optional helper/remarks and unarchived timestamp are JSON null, never missing.
- Event keys: `id`, `audit_id`, `revision`, `action`, `actor_name`,
  `actor_profile_id`, `created_at`, `before`, `after`. Snapshots use the audit shape.
- Manifest keys: `format`=`bhli-audit-transfer`, `format_version`=1, `package_id`,
  `source_installation_id`, `exported_at`, `record_count`, `event_count`,
  `filters` (`date_from`, `date_to`, `include_archived`=true), `audits_sha256`,
  `events_sha256`. Unknown or missing keys are errors in v1.
- Hashes are lowercase SHA-256 over exact NDJSON bytes. Receipt content identity
  is SHA-256 of the concatenated exact canonical manifest, audit and event bytes,
  in that order; canonical objects and LF boundaries make this unambiguous.
  Receipt includes all manifest metadata, so same package UUID with different
  timestamp/filters also conflicts. Checksums detect corruption, not authorship.
- Shared golden fixture includes the three exact byte streams, hashes, ZIP and
  expected semantic values; cross-language tests must consume actual opposite-
  platform generated packages, not just compare two hand-written expectations.

## Untrusted-input validation and resource budgets

Proposed initial ceilings (must be measured before final acceptance): 32 MiB
archive, 32 MiB total uncompressed data, 64 KiB manifest, 256 KiB per NDJSON line,
2,000 audits, 10,000 events, JSON nesting depth 6. Check limits while reading,
not after allocation. Exceeding a limit fails the whole operation with guidance
to narrow the date range; never silently drop rows/history. A single oversized
history fails even if its audit alone would fit. Export and import share limits.

Inspect central and local ZIP headers, flags, entry names, file types, sizes,
offsets, CRC and actual streamed bytes. Reject traversal, alternate separators,
duplicates, symlinks, overlapping/ambiguous entries, trailing payloads and size
lies. Never extract supplied paths or run supplied SQL. Stage only in private
app-owned temporary files with generated names and bounded disk quota.

Validate exact record/event shapes and unique UUIDs; every event belongs to an
included audit. Require revisions 1..N, one CREATE first, before=null initially,
after revision 1, each subsequent before equal to prior after, and final after
equal to the exported record. CREATE requires `archived_at=null` and
`created_at=updated_at=event.created_at`; its actor UUID/name equals original
auditor snapshot. IDs, origin identity/name and creation timestamp remain immutable.
UPDATE changes only editable fields plus revision/update timestamp and must
actually change an editable value; ARCHIVE changes archive/update timestamp
and revision only, is terminal and preserves editable fields. Event timestamp
equals after.updated_at; archive timestamp equals archive event timestamp.
Revision order, not wall-clock order, determines the chain. Existing devices can
have clock corrections; do not reject otherwise valid historical data solely
because a later revision has an earlier timestamp. All before/after snapshots
receive the same field/type validation. Do not normalize away meaningful differences.

## Export workflow

Driver Audits gains **Export Audits** and **Import Audits**, with no new primary
navigation. Export offers All records or inclusive audit-date range, explicitly
including archived records, a count, and an explanation that complete history
travels with the records. Validate range before dispatch; empty exports are valid.

Create one consistent read transaction to select records and all their histories;
do not paginate through separate snapshots. Stream bounded sorted rows into
private staging files, validate history, finalize hashes and package, then ask
for destination. Count and final file describe this same snapshot. Report any
changes after staging only as outside that snapshot.

Windows uses the existing database worker and a native save dialog on the UI
thread. File generation stays off Tk. Publish staged bytes with an exclusive
no-replace file operation; even a race after selection cannot replace an existing
file. Flush/close successfully before completion feedback; clean owned temporary
files on cancel/failure. Do not promise arbitrary network filesystem guarantees.

Android uses a dedicated document MethodChannel and native background executor:
`ACTION_CREATE_DOCUMENT` for a new file, `ACTION_OPEN_DOCUMENT` for import, no
broad storage permissions and no filesystem-path assumptions about content URIs.
Complete private staging before creating a destination. Request local-only
providers and require no cloud login/network. Copy with cancellation checks;
flush/close and read-back hash verification must succeed before reporting saved.
On failure delete only the newly created document where supported. If cleanup
fails, explicitly warn that an incomplete file may remain; never report success.
Process death/provider behavior cannot be promised atomic across arbitrary SAF
providers. Invalid partial files will fail import validation. External provider
acceptance is separately recorded, not assumed from emulator local storage.

## Import preview, conflicts and receipts

Copy selected input into private bounded immutable staging, validate completely,
then show New / Already here / Different version counts. Invalid packages fail
as a whole. Preview shows no raw UUIDs, SQL or executable content. Main copy:
“Only new audits will be added. Existing audits and their history stay unchanged.
Later edits to audits already imported are not synchronized.”

Buttons: **Import new records only**, **Cancel**. Conflicts require an explicit
acknowledgment that they will be skipped. Zero-new packages may be confirmed to
record their receipt; no audit/event is inserted. No silent automatic import.

- New record UUID with a valid complete chain: eligible.
- Existing UUID with identical canonical record and complete history: duplicate.
- Any content/history difference: conflict, regardless of revision/timestamp.
- Event UUID found anywhere with different canonical content: reject whole import.
  An event UUID cannot migrate to another audit. Incoming duplicate event IDs
  within the package are invalid, even if their content matches.
- Accepted receipt package UUID with different content hash: reject whole import.
  Same package UUID/hash may be safely rechecked and reimported without duplicates.
- Revalidate package hash, all global event collisions, receipts and the displayed
  classification under the final write transaction. If classification changed
  since preview, abort and require a fresh preview; never silently alter consent.
- In one write transaction register required identities, insert only independently
  eligible audits and their complete events, insert receipt, check FKs, and COMMIT.
  No edits/events are manufactured for the importer. Imported history is data,
  not an authenticated assertion about the sender. Local edits afterwards use
  current local actor snapshots without changing original attribution.
- Any insert, storage or commit failure rolls back identities, audits, events
  and receipt together. Do not report success until commit is confirmed.

## Lifecycle, accessibility and progress

Phases: Reading → Checking → Preview → Importing → Complete; export uses
Preparing → Choose destination → Saving → Complete. Screen-reader status,
visible counts, keyboard focus, 48dp Android controls, 200% text, compact layouts
and both themes follow existing design. Retain list filters; refresh after success.
No fake percentage if total work is unknown. Errors offer a useful next action.

One transfer per app; prevent duplicate dispatch. Pre-commit cancellation rolls
back. An admitted Windows import remains a durable write: shutdown drains it and
retains existing failure acknowledgments. During final COMMIT show finishing
instead of promising cancellation; a late cancel must not misreport a committed
import. Android retains operation coordination while SAF temporarily backgrounds
the app; process death leaves either committed data or SQLite rollback. On an
uncertain result advise checking/reimporting the same file, which is safe. Never
claim that canceled transport or lost UI means a server/local write was undone.

## Modules and dependencies

Per platform, keep codec/history validation independent of widgets and repositories.
Repository methods own snapshot export, preview classification and transactional
apply. Desktop worker and Android admitted-operation queue own their connections.
UI owns dialogs and display only. Native Android bridge owns content-URI I/O.
Do not transport full package bytes over MethodChannel or load ZIPs wholesale.

Python uses standard-library ZIP/JSON/SHA-256. Dart package choice is deferred to
plan research: prefer a small pinned ZIP/hash implementation with bounded reading
and license review; existing transitive packages must become explicit direct
dependencies if used. Do not implement a general archive library. No dependency
installation or upgrade is authorized by this design document alone.

## Implementation checkpoints after design approval

1. Shared exact wire fixtures, threat model, codec feasibility/resource measurement.
2. Both v1→v2 migrations and regression fixtures; identity-preserving local CRUD.
3. Python codec/export/preview/import with real SQLite rollback/collision tests.
4. Dart codec/export/preview/import; consume each other's generated packages.
5. Windows transfer screens and lifecycle; Android SAF/screens and cancellation.
6. Independent engineering/security/UX review; full regression, native acceptance,
   ordinary online/offline Android builds and offline Windows packaging.

Write failing tests for each contract before code; commit coherent verified
milestones locally. No push, PR, release, signing, production data or Phase 6E work.

## Acceptance evidence required

Both directions using real temporary SQLite stores and different local profiles;
same-file reimport; conflicts/UUID collisions; archived/multirevision histories;
Unicode/emoji/leading-zero plates; local rename after import; invalid chains;
malformed ZIP/JSON; bounded hostile input; empty export; cancellation; storage,
receipt, final-commit and migration failures; restart persistence. Prove originals
and current profile remain unchanged on rejection. Measure peak memory, staging
disk and operation time near ceilings on emulator/device before accepting limits.

Native Windows and Android acceptance: picker, counts, preview, narrow screens,
large text, themes, keyboard, background/close/process restart and network-disabled
operation. Exchange actual generated packages, not raw DB files. Serialize heavy
build/test/emulator operations. Record physical-device/provider gaps honestly.
Run full Python/default, isolated MySQL, Flutter, native desktop, packaging and
licensing suites; preserve original online launch and release/tag/asset identity.
No bundled records, databases, credentials or signing secrets. Start empty.

## Known limitations and review gate

Packages are plaintext, unauthenticated and contain employee-like historical data.
Use fictional data only until security and backup approval. No encryption,
signature verification, edit reconciliation, backup/restore, offline Excel,
production signing or employee release in this phase. A package is a selected
snapshot and not a disaster-recovery image. Provider copy failure/process death
may leave an invalid file; failures and cleanup limitations must remain visible.

The installed Superpowers brainstorming workflow requires operator design approval
before product code, scaffolding or dependency changes. This document records the
concrete proposal for that approval; a detailed implementation plan follows it.

Research: Android's official [Storage Access Framework guide](https://developer.android.com/training/data-storage/shared/documents-files)
documents create/open document flows and create-without-overwrite behavior. UI UX
Pro Max's focused progress guidance supports explicit multi-step status; preserve
the existing navy/teal interfaces rather than generating a new visual system.
