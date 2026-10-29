# BHLI Audit Android client

Flutter / Material 3 client for authenticated ADMIN and AUDITOR accounts. Browse
shared active audits, search/filter/sort and paginate; create audits, edit under
stable-ID ownership rules and review conflicts explicitly. ADMIN may archive and
browse archived audits. Both roles can view authorized active audit history.
The server supplies and preserves the original Audited By identity.

Tokens, protected data, drafts and uncertain creation attempts remain in memory;
process death requires login again. Remote APIs require trusted HTTPS.

See [development and disposable demo instructions](../docs/ANDROID_DEVELOPMENT.md),
[pinned toolchain setup](../docs/ANDROID_TOOLCHAIN.md) and
[Phase 4B acceptance/demo](../docs/ANDROID_PHASE4B_ACCEPTANCE.md),
[Phase 4B verification](../docs/ANDROID_PHASE4B_VERIFICATION.md) and
[current release readiness](../docs/RELEASE_READINESS.md).

No direct MySQL access, Android account administration, offline synchronization,
Excel/PDF export or signed production distribution is included. Current metadata
remains `0.4.0+1`; Version 1.0 is a proposed development/demo milestone, not a
released build. The legacy read-only description in `pubspec.yaml` is scheduled
for Checkpoint B; behavior already includes the Phase 4B mutations described here.
