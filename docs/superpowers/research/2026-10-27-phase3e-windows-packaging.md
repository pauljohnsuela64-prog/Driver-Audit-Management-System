# Phase 3E Windows packaging research

Checked 2026-10-27 against primary sources. Design only: no installation, build, signing, deployment or production access. Versions below are dated observations, not dependency pins.

## Recommendation

Use ordinary GIL-enabled CPython 3.14 x64, Windows-native PyInstaller one-directory output, and a signed per-user Inno Setup installer as the leading design candidate. This is an engineering recommendation contingent on a later clean-Windows packaging spike. Retain WiX if managed MSI deployment/repair becomes an actual requirement. Documentation does not prove a functioning artifact.

## Current release observations

| Tool | Official observation | Source |
| --- | --- | --- |
| PyInstaller | Stable 6.22.3, released 2026-09-12; Python 3.14 supported since 6.15.0. | [Changelog](https://pyinstaller.org/en/latest/CHANGES.html) |
| Inno Setup | 7.1.0 (2026-08-12); 6-series download remains 6.7.3. | [Downloads](https://jrsoftware.org/isdl.php) |
| WiX | 7.0.1, announced 2026-10-26. | [Official news](https://www.firegiant.com/wixtoolset/), [release notes](https://docs.firegiant.com/wix/whatsnew/releasenotes/) |
| Nuitka | Current release page identifies 4.3 series; 4.2 formally added Python 3.14 support. Resolve newest patch before future pinning. | [Current release](https://nuitka.net/changelog/Changelog.html), [4.2](https://ftp.nuitka.net/posts/nuitka-release-42.html) |
| Briefcase | Stable Windows docs identify 0.4.7. | [Windows docs](https://briefcase.beeware.org/en/stable/reference/platforms/windows/index.html) |

## Freezer and runtime constraints

Python 3.14 is supported by PyInstaller; it is incorrect to call it categorically blocked. Build on the target OS and for the intended architecture: PyInstaller is not a cross-compiler. CPython 3.14 supports Windows 10 and newer, despite PyInstaller itself listing Windows 8; the interpreter minimum governs this proposed application. [PyInstaller manual](https://pyinstaller.org/en/stable/), [requirements](https://pyinstaller.org/en/stable/requirements.html), [Python Windows](https://docs.python.org/3.14/using/windows.html#supported-windows-versions).

CustomTkinter explicitly recommends onedir and manually including its directory for JSON themes and OTF fonts. Its page says onefile cannot pack those assets, but PyInstaller itself documents packing/extracting non-Python support files. Therefore interpret the CustomTkinter page as its recommended workflow, not a universal technical impossibility. Explicit asset collection and frozen theme/font/image checks remain necessary. [CustomTkinter packaging](https://customtkinter.tomschimansky.com/documentation/packaging/), [PyInstaller operation](https://pyinstaller.org/en/stable/operating-mode.html).

Onefile adds extraction/startup work and can leave temporary directories after forced termination. PyInstaller specifically warns against elevated Windows onefile executables due to possible modification of temporary extracted libraries. Onedir is easier to diagnose and fits an installer. [PyInstaller operation](https://pyinstaller.org/en/stable/operating-mode.html).

Use the ordinary interpreter baseline. Free-threaded Python is a separate configuration with native-extension compatibility implications; general 3.14 support does not prove all variants work. This research establishes no blanket claim that current PyInstaller lacks free-threading support. [Python free threading](https://docs.python.org/3.14/howto/free-threading-python.html).

Tcl/Tk runtime and data must survive packaging. `python -m tkinter` identifies the development Tcl/Tk runtime. PyInstaller 6.22 changed tkinter hooks to report missing Tcl/Tk data directories at build time and added Tcl/Tk 9 embedded-data support. A later artifact must exercise GUI startup/dialogs/fonts. [Python tkinter](https://docs.python.org/3.14/library/tkinter.html), [PyInstaller changes](https://pyinstaller.org/en/latest/CHANGES.html).

Pillow's table supports Python 3.14 in Pillow 12 and 13, but not 11. Check existing pins and suitable Windows wheels; frozen imaging extensions/codecs require actual image-load validation. [Pillow support](https://pillow.readthedocs.io/en/stable/installation/python-support.html).

XlsxWriter writes XLSX files, cannot read/modify existing ones, and uses BSD 2-Clause licensing. Proposed smoke test: generate and close a representative workbook in a user-writable output location. This test is a design inference from its behavior. [Introduction](https://xlsxwriter.readthedocs.io/introduction.html), [getting started](https://xlsxwriter.readthedocs.io/getting_started.html).

TLS trust follows the actual HTTP client: Python SSL can load Windows certificate stores; Requests uses certifi by default and accepts an explicit CA bundle. Modern pip adds system certificates through truststore, so successful pip access does not prove the shipped app trusts an enterprise proxy. Preserve verification and document any approved organization CA provisioning. [Python SSL](https://docs.python.org/3.14/library/ssl.html#ssl.SSLContext.load_default_certs), [Requests](https://requests.readthedocs.io/en/stable/user/advanced/#ssl-cert-verification), [pip trust](https://pip.pypa.io/en/stable/topics/https-certificates/).

## Alternatives and installers

Nuitka supports Python 3.14/Windows, but adds C compilation and associated compiler/toolchain maintenance. Its current manual lists Visual Studio 2022 or newer as a Windows compiler option. Consider it if measured requirements justify the extra toolchain. [Manual](https://nuitka.net/user-documentation/user-manual.html).

Briefcase is a poor fit for the existing Tk GUI: official Windows docs explicitly say tkinter is unavailable because the Python embeddable support package omits it. Runtime customization is additional scope. [Briefcase quirks](https://briefcase.beeware.org/en/stable/reference/platforms/windows/index.html#tkinter-is-not-available).

Inno supports unelevated installation through `PrivilegesRequired=lowest`; default is admin, so per-user scope must be intentional. User-local paths, stable application identity, upgrade behavior and preservation of user outputs during uninstall need explicit design. Inno can sign setup, uninstaller and selected source binaries; its downloads page recommends updates for security/reliability. [Privileges](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm), [signing](https://jrsoftware.org/ishelp/topic_setup_signtool.htm), [downloads](https://jrsoftware.org/isdl.php).

WiX supports explicit per-user/per-machine package scope, defaulting to per-machine. Its declarative MSI component/upgrade authoring and .NET build tooling are maintenance costs to weigh against managed deployment needs (engineering assessment). Current 7.0.1 removes a vulnerable bundled .NET assembly, demonstrating that installer build tooling also needs updates. [Package scope](https://docs.firegiant.com/wix/schema/wxs/package/), [release notes](https://docs.firegiant.com/wix/whatsnew/releasenotes/).

Inno's current LICENSE permits commercial use subject to its conditions; the official site requests commercial licenses. Purchased terms include two years of updates and continuing use of covered releases. Do not call that request a mandatory prohibition absent purchase. WiX v6+ introduces the Open Source Maintenance Fee: official terms require sponsorship for organizations over $10,000 annual revenue; v7 enforces EULA acceptance. Resolve applicability before selecting WiX binaries. [Inno license](https://jrsoftware.org/files/is/license.txt), [purchase](https://jrsoftware.org/ishelp/topic_purchase.htm), [terms](https://jrsoftware.org/isorder-terms.php), [WiX OSMF](https://docs.firegiant.com/wix/osmf/).

Authenticode signing and HTTPS trust are separate. Plan protected signing credentials, timestamping, and verification of final immutable files. Signing does not guarantee SmartScreen acceptance: Microsoft says EV certificates no longer grant automatic reputation bypass. [Microsoft guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation), [Inno signing](https://jrsoftware.org/ishelp/topic_setup_signtool.htm).

## Proposed later acceptance gates

Not performed: clean supported Windows VM without Python; ordinary-user install/launch/uninstall; themes/fonts/images/dialogs; representative XLSX export; configured HTTPS trust including approved proxy; Unicode/space-containing paths; reinstall/upgrade and locked files; user-file preservation; signatures/timestamps; bundled dependency inventory/licenses. This note alone authorizes no dependency upgrades or installer implementation.
