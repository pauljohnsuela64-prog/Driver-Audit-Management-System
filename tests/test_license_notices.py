"""Offline, byte-exact notice inclusion contracts; no network or database access."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest


def notice_fixture(tmp_path, monkeypatch, platform="windows"):
    from scripts import license_notices
    root = tmp_path / platform
    root.mkdir()
    name = "assets/compliance/NOTICES-UPSTREAM.txt" if platform == "android" else "NOTICES-UPSTREAM.txt"
    data = b"Copyright upstream\nPermission and disclaimer\n"
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    manifest = {"files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                            "source": "https://example.invalid/upstream/LICENSE", "version": "fixture"}]}
    (root / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(license_notices, "NOTICE_ROOT", tmp_path)
    return license_notices, root, name, data, manifest


def test_notices_are_copied_verbatim_with_provenance(tmp_path, monkeypatch):
    notices, root, name, data, manifest = notice_fixture(tmp_path, monkeypatch)
    target = tmp_path / "bundle"
    records = notices.copy_verified_notices("windows", target)
    assert (target / name).read_bytes() == data
    assert records == manifest["files"]
    assert json.loads((target / "NOTICE-PROVENANCE.json").read_text()) == manifest


@pytest.mark.parametrize("damage", ["missing", "modified", "escape", "duplicate"])
def test_bad_notice_inventory_fails_before_writing(tmp_path, monkeypatch, damage):
    notices, root, name, data, manifest = notice_fixture(tmp_path, monkeypatch)
    if damage == "missing":
        (root / name).unlink()
    elif damage == "modified":
        (root / name).write_bytes(b"truncated notice")
    elif damage == "escape":
        manifest["files"][0]["path"] = "../outside.txt"
    else:
        manifest["files"].append(dict(manifest["files"][0]))
    (root / "manifest.json").write_text(json.dumps(manifest))
    target = tmp_path / "bundle"
    with pytest.raises(ValueError, match="notice|Notice"):
        notices.copy_verified_notices("windows", target)
    assert not target.exists()


def test_android_requires_exact_embedded_notice_bytes(tmp_path, monkeypatch):
    notices, root, name, data, manifest = notice_fixture(tmp_path, monkeypatch, "android")
    apk = tmp_path / "app.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr(name, data)
    assert notices.verify_apk_notices(apk) == manifest["files"]
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr(name, b"old version")
    with pytest.raises(ValueError, match="notice|Notice"):
        notices.verify_apk_notices(apk)
    with zipfile.ZipFile(apk, "w"):
        pass
    with pytest.raises(ValueError, match="notice|Notice"):
        notices.verify_apk_notices(apk)


def test_notice_changes_trigger_android_ci():
    import ast
    from fnmatch import fnmatchcase
    root = Path(__file__).resolve().parents[1]
    lines = (root / ".github/workflows/mobile-tests.yml").read_text().splitlines()
    filters = [ast.literal_eval(line.split("paths:", 1)[1].strip())
               for line in lines if "paths:" in line]
    assert len(filters) == 2  # pull_request and push
    for patterns in filters:
        for path in ("packaging/notices/android/assets/compliance/NOTICES-NATIVE.txt",
                     "scripts/license_notices.py", "tests/test_license_notices.py"):
            assert any(fnmatchcase(path, pattern) for pattern in patterns), path


def test_unreviewed_android_asset_is_rejected(tmp_path, monkeypatch):
    notices, root, name, data, manifest = notice_fixture(tmp_path, monkeypatch, "android")
    (root / "assets/compliance/unreviewed.txt").write_text("not reviewed")
    with pytest.raises(ValueError, match="Unreviewed Android notice asset"):
        notices.verified_notices("android")


def test_notice_bytes_survive_git_line_ending_filters():
    import subprocess
    root = Path(__file__).resolve().parents[1]
    data = b"Upstream license\r\nCopyright and conditions\r\n"
    expected = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    actual = subprocess.check_output([
        "git", "-c", "safe.directory=" + root.as_posix(), "-c", "core.autocrlf=true",
        "hash-object", "--path=packaging/notices/windows/example.txt", "--stdin"
    ], input=data, cwd=root).decode().strip()
    assert actual == expected


def test_reviewed_notice_inventory_preserves_required_component_material():
    from scripts.license_notices import verified_notices
    root = Path(__file__).resolve().parents[1]
    windows, files = verified_notices("windows")
    text = b"\n".join(data for _, data in files).decode("utf-8")
    assert "Expat" in text and "Permission is hereby granted" in text
    assert "This software is based in part on the work of the FreeType Team." in text
    assert "This software is based in part on the work of the Independent JPEG Group." in text
    assert "The OpenSSL Project Authors" in text
    android, files = verified_notices("android")
    assets = dict(files)
    source = assets["assets/compliance/junit-4.12-sources.zip"]
    assert hashlib.sha256(source).hexdigest() == android["junit"]["source_sha256"]
    import io
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        assert archive.testzip() is None
        prefix = "junit4-" + android["junit"]["source_commit"] + "/"
        assert archive.read(prefix + "LICENSE-junit.txt") == assets["assets/compliance/NOTICE-JUNIT-LICENSE.txt"]
        assert archive.read(prefix + "NOTICE.txt") == assets["assets/compliance/NOTICE-JUNIT-UPSTREAM.txt"]
        assert archive.read(prefix + "src/main/java/org/junit/Test.java")
        assert archive.read(prefix + "pom.xml")
    statement = assets["assets/compliance/NOTICE-JUNIT-SOURCE.txt"].decode()
    assert "assets/compliance/junit-4.12-sources.zip" in statement
    assert android["junit"]["source_sha256"] in statement
    assert "Attribution 4.0 International" in assets["assets/compliance/NOTICE-MATERIALICONS-LICENSE.txt"].decode()
    assert "Copyright (c) 2008" in assets["assets/compliance/NOTICE-ANIMAL-SNIFFER-ANNOTATIONS.txt"].decode()
