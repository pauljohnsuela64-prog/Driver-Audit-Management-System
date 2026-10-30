# Client third-party compliance records

These records concern bundled third-party code and resources. Authorized original
source contributions use [Apache 2.0](../LICENSE), with approved attribution in
[NOTICE](../NOTICE) and explicit [asset/branding exclusions](../ASSET_RIGHTS.md).
The [third-party index](../THIRD_PARTY_NOTICES.md) does not relicense upstream work,
grant BHLI trademark/artwork rights or authorize public publication.

## Offline notice inclusion

`packaging/notices/windows/manifest.json` and
`packaging/notices/android/manifest.json` record reviewed supplemental material
and its SHA-256. The builders validate all listed bytes before packaging.
The root `LICENSE`, `NOTICE`, `ASSET_RIGHTS.md`, `THIRD_PARTY_NOTICES.md` and
this compliance document are also copied byte-for-byte into the Windows bundle
and Android `assets/application-license/`. The Android notice sidecar includes
all five texts; the original directory structure supports their relative links.
Builders check the official Apache text and reject stale/missing scope documents.
Gradle copies only these five explicitly selected documents into generated assets,
not the repository or local configuration.

Builds never download source or license material dynamically. Existing package,
CPython, Pillow and Flutter composite notices remain required; the supplemental
files do not replace them or certify every transitive component.

Windows places the supplemental texts in `THIRD_PARTY_LICENSES/SUPPLEMENTAL`
before generating the installer and full-folder ZIP. This adds Expat 2.9.0
copyright/permission text, explicit FreeType/IJG product acknowledgments,
OpenSSL 3.5.9 license/copyright attribution and Roboto font attribution.
The exact OpenSSL 3.5.9 source archive was inspected and supplies no NOTICE file;
none is invented. Complete Pillow/CPython notices continue to be preserved.

Android embeds the reviewed material under `assets/compliance/`. The ordinary
internal/debug APK includes JUnit 4.12 classes through the integration-test
native plugin even though its Dart entry point is `lib/main.dart`. This is
third-party test-framework code, not permission to ship fictional-loopback
fixture entry points or credentials. The accompanying JUnit source ZIP,
EPL-1.0 text, upstream NOTICE and recipient extraction instructions provide
local source availability without depending on a future external download.
Existing Flutter and native APK notices also appear in the candidate sidecar.
The candidate builder rejects missing, stale or altered supplemental assets.

The exact Flutter MaterialIcons font is attributed using the CC BY 4.0 text
supplied with its matching cached font asset. A generic Material Design source
repository license must not override the license of the actual bundled asset.
No font was replaced, and no system Segoe UI font files are copied.

## Review and distribution boundaries

Package-license metadata alone does not prove complete native/static-component
provenance or every applicable upstream NOTICE. The local compliance report
records remaining questions about native builds and protected artwork; do not
represent the current notices as universal legal or patent clearance. A future
dependency/toolchain change requires reviewing the inventory and notice hashes.
No source-code license is inferred from a third-party Apache text or appendix.

Public feature-branch pushes can trigger downloadable Actions candidates. A
draft PR does not make those artifacts private. Obtain separate publication
approval after rights/notice review, and verify all five hosted checks on the
exact final commit. Candidate status remains unsigned Windows/internal-debug
Android; production deployment and unresolved acceptance checks are separate.
