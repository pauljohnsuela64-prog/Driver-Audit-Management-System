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
Excel/PDF export or signed production distribution is included. No direct MySQL access, Android account administration, offline synchronization,
Excel/PDF export or signed production distribution is included. Candidate metadata
is now `1.0.0+2`; Version 1.0 remains an unpublished development/demo milestone.
