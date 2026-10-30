# Third-party licenses and attribution

The project's authorized original code is licensed separately under
[Apache 2.0](LICENSE), with [project attribution](NOTICE) and explicit
[asset/branding exclusions](ASSET_RIGHTS.md). Copyright 2026 Paul John Suela
does not claim third-party contributions or excluded company/artwork rights.

Third-party components retain their own copyright, licenses, notices and source
availability conditions. Do not replace them with the application's license or
assume every dependency is MIT/Apache. The following is an index, not a substitute
for the complete component texts distributed with each candidate.

| Client material | Distributed notice location / conditions |
| --- | --- |
| Windows CPython and native runtime | `THIRD_PARTY_LICENSES/CPython-LICENSE.txt` retains PSF/historical and bundled native terms, including the Microsoft Windows addendum |
| Windows CustomTkinter, darkdetect, packaging, Pillow and XlsxWriter | Complete package/license directories under `THIRD_PARTY_LICENSES/`; Pillow's composite native-code notices are preserved |
| Windows Expat, FreeType/IJG, OpenSSL, Roboto and Inno Setup | Exact license texts, copyright and required acknowledgments under `THIRD_PARTY_LICENSES/SUPPLEMENTAL/`; no invented OpenSSL NOTICE |
| PyInstaller embedded loader/runtime hooks | Upstream GPL text with bootloader exception and applicable Apache hook terms retained; build-tool use does not automatically license application code under GPL |
| Android Flutter/Dart, ICU and engine resources | Embedded Flutter `assets/flutter_assets/NOTICES.Z`, existing APK component notices and the candidate `THIRD_PARTY_NOTICES.txt` sidecar |
| Android native/Gradle components | Reviewed archive notices and native-coordinate inventory under `assets/compliance/`; includes JNI AOSP/Dart, DataStore, Hamcrest, animal-sniffer, Guava and Checker annotation attribution |
| Android MaterialIcons | `assets/compliance/NOTICE-MATERIALICONS-ATTRIBUTION.txt` and `NOTICE-MATERIALICONS-LICENSE.txt`; the matching bundled font uses CC BY 4.0 |
| Android JUnit 4.12 | EPL 1.0 license, upstream NOTICE, source-availability statement and complete source ZIP under `assets/compliance/` |

## JUnit source availability

The ordinary internal/debug APK contains JUnit 4.12 code. This distributor supplies
its complete corresponding upstream Program source inside the APK as
`assets/compliance/junit-4.12-sources.zip`, including its build files, LICENSE and
NOTICE. Open the APK with a standard ZIP reader, extract that entry and open the
source ZIP. No online download or separate request is required.

Source SHA-256: `57f446df276958abf22431c0fdbffb11c125ea99c5f973c88cc4596ce4852165`.
Upstream commit: `64155f8a9babcfcf4263cf4d08253a1556e75481` (tag `r4.12`).
The full recipient statement and EPL terms are included beside the source and in
the downloadable candidate's notice sidecar. This source delivery concerns the
JUnit Program; it does not relicense the separate application as EPL.

## Scope and verification

Windows folder/installer/ZIP candidates carry this index and the original-code
license/scope documents. Android carries those documents under
`assets/application-license/` and includes their text in its notice sidecar.
Repository-only tooling and server/test requirements are not all bundled client
runtime code. Distribution of a separate server runtime/container requires its
own dependency inventory; no production server distribution is authorized here.

For exact supplemental hashes, sources, build inclusion and remaining provenance
limits, see the source manifests in `packaging/notices/` and
[client compliance records](docs/THIRD_PARTY_COMPLIANCE.md). Retain all applicable
upstream notices when modifying or redistributing. A component's Apache text does
not cover BHLI artwork, and the project license is not universal patent clearance.
Official candidates remain unsigned Windows/internal-debug Android development
builds, not production certification or an already published release.
