# Phase 4B contract research and independent design review

Date: 2026-10-28. Documentation-only branch from `54c1f2e` after merged PR #10
and all five green post-merge jobs. No application, database or infrastructure
changes; no implementation test suite claimed as executed.

## Primary local sources

- `backend/api/audits.py`: UUID create header, 201/200 replay, exact quoted-version
  ETag, If-Match 428/422/412, paginated history and ADMIN include-deleted routes.
- `backend/schemas/audit_api.py`: six editable keys, strict fields, lengths,
  nullable optionals, changed-only patch semantics and history actor-ID contract.
- `backend/services/audits.py`: stable owner-ID checks, immutable original
  attribution, original-CREATE-payload replay, active-only mutation, row locks,
  atomic record/history transactions and soft deletion.
- `mobile/lib/core/network/api_client.dart` and auth/session controller:
  strict typed active-only reads, 20-second request deadline, 2 MiB body cap,
  session-generation isolation, separate read scopes and existing auth `_busy`.
- Current mobile screens/theme: bounded-width scroll layouts, Material 3
  navy/teal tokens and safe-area/touch conventions to reuse.

## Pure local contract probes

No server/database was started. Instantiated AuditCreate and serialized fictional
snapshots with the installed backend's actual Starlette JSONResponse.

| Boundary character around X | Required driver_name | Optional helper_name |
| --- | --- | --- |
| U+001C | Retained | Trimmed |
| U+0085 NEL | Trimmed | Trimmed |
| U+00A0 NBSP | Trimmed | Trimmed |
| U+FEFF BOM | Retained | Retained |

Required fields use Pydantic whitespace trimming; optional fields additionally
run Python `str.strip`. The specification and future golden-vector tests now
explicitly preserve this difference; no common Dart `trim` assumption.

JSONResponse uses `ensure_ascii=False`. For UPDATE events with before/after
snapshots at all text maxima, using six-byte JSON-escaped controls:

| Events | Serialized page bytes | Under 2 MiB |
| --- | ---: | --- |
| 10 | 1,301,016 | Yes |
| 25 | 3,252,471 | No |

Therefore the proposed history page is 10 events; list pages remain 25 records.
The implementation must test the actual serializer and keep the cap unchanged.

## Independent architecture/security review

A separate reviewer read the specification, plan, backend contracts and existing
Flutter modules. Findings incorporated:

1. History snapshots can exceed the body limit at 25 events: reduced to 10 with
   explicit worst-case encoding regression coverage.
2. Existing auth `_busy` suppresses logout/resume operations: mutation exclusivity
   must use an independent session latch and transport scope, with logout/resume
   race coverage.

Reviewer re-read the corrections and found no remaining important architecture
or security design blocker. Actual code behavior remains unimplemented/unverified.

## Independent mobile-UX review

A separate reviewer read the actual UI UX Pro Max mobile checklist and compared
existing Flutter screens. Findings incorporated:

1. Unknown saves retain one session-RAM attempt with an Audits review banner;
   explicit abandonment explains duplicate risk. Every new-create entry gets a
   generic interruption reminder because restart has no retained marker.
2. Conflicts use explicit per-field latest/proposed choices, preserve unrelated
   concurrent changes and disable Save until latest-state review succeeds.
3. Consistent Archive audit/Archived wording; Include archived explicitly means
   active plus archived, with read-only archived status.
4. Keyboard Back precedes route Back, single-line Next versus remarks newline,
   stacked/wrapped actions, scrolling dialogs and largest-text acceptance.
5. Actor IDs are labeled separately from original Audited By, with concise help.

Reviewer re-read the revised design and plan: no remaining important mobile-UX
design blocker; one minor diagram label was corrected from Delete to Archive
audit. Visual, TalkBack, keyboard and runtime acceptance are future tests, not
results of this documentation review.

## Skills and remaining decision

Applied Superpowers brainstorming/writing-plans and independent review guidance,
UI UX Pro Max mobile/accessibility checklist, and Codebase Design's small typed
interfaces and focused state ownership. Existing backend code is the primary
contract source; no new framework or dependency is proposed.

Operator approval is still required for the specification and checkpoints.
No implementation, push, PR, production changes or next-phase work is authorized
by this review report.
