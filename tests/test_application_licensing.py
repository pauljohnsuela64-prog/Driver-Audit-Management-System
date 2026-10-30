"""Approved source grant, protected-asset scope and packaged license contracts."""
from pathlib import Path
import hashlib
import re
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_official_license_and_approved_identity_are_separate():
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == APACHE_SHA256
    assert b"Copyright 2026 Paul John Suela" not in (ROOT / "LICENSE").read_bytes()
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Copyright 2026 Paul John Suela" in notice
    assert "ASSET_RIGHTS.md" in notice and "THIRD_PARTY_NOTICES.md" in notice


def test_exact_protected_asset_scope_exists_and_is_not_an_ownership_claim():
    text = (ROOT / "ASSET_RIGHTS.md").read_text(encoding="utf-8")
    paths = re.findall(r"^\| `([^`]+)` \|", text, re.MULTILINE)
    assert len(paths) == len(set(paths)) == 66
    for name in paths:
        assert (ROOT / name).is_file(), name
    assert "does not determine who owns" in text
    assert "not a downstream trademark sublicense" in text
    assert "third-party" in text and "original" in text


def test_project_license_copy_is_exact_and_limited_to_reviewed_documents(tmp_path):
    from scripts.license_notices import copy_application_notices
    records = copy_application_notices(tmp_path)
    expected = {"LICENSE", "NOTICE", "ASSET_RIGHTS.md", "THIRD_PARTY_NOTICES.md",
                "docs/THIRD_PARTY_COMPLIANCE.md"}
    assert {item["path"] for item in records} == expected
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()} == expected
    for item in records:
        assert (tmp_path / item["path"]).read_bytes() == (ROOT / item["path"]).read_bytes()
        assert item["sha256"] == hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()


def test_apk_application_license_verification_rejects_stale_or_missing_docs(tmp_path):
    from scripts.license_notices import APPLICATION_FILES, verify_apk_application_notices
    apk = tmp_path / "candidate.apk"
    with zipfile.ZipFile(apk, "w") as z:
        for name in APPLICATION_FILES:
            z.writestr("assets/application-license/" + name, (ROOT / name).read_bytes())
    assert len(verify_apk_application_notices(apk)) == 5
    for stale in (False, True):
        with zipfile.ZipFile(apk, "w") as z:
            for name in APPLICATION_FILES:
                if name == "NOTICE":
                    if stale:
                        z.writestr("assets/application-license/NOTICE", b"obsolete scope")
                else:
                    z.writestr("assets/application-license/" + name, (ROOT / name).read_bytes())
        with pytest.raises(ValueError, match="application license"):
            verify_apk_application_notices(apk)


def test_license_documents_and_tests_trigger_android_ci():
    import ast
    from fnmatch import fnmatchcase
    from scripts.license_notices import APPLICATION_FILES
    workflow = (ROOT / ".github/workflows/mobile-tests.yml").read_text()
    filters = [ast.literal_eval(line.split("paths:", 1)[1].strip())
               for line in workflow.splitlines() if "paths:" in line]
    assert len(filters) == 2
    for patterns in filters:
        for name in (*APPLICATION_FILES, "tests/test_application_licensing.py"):
            assert any(fnmatchcase(name, pattern) for pattern in patterns), name


def test_apk_application_license_directory_rejects_unreviewed_files(tmp_path):
    from scripts.license_notices import APPLICATION_FILES, verify_apk_application_notices
    apk = tmp_path / "candidate.apk"
    with zipfile.ZipFile(apk, "w") as z:
        for name in APPLICATION_FILES:
            z.writestr("assets/application-license/" + name, (ROOT / name).read_bytes())
        z.writestr("assets/application-license/unreviewed.txt", b"not an approved document")
    with pytest.raises(ValueError, match="application license"):
        verify_apk_application_notices(apk)
