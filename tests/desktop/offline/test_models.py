"""Shared Android vectors catch trimming, code-point and date contract drift."""
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import UUID

import pytest

from desktop.offline.models import (
    LocalProfile, OfflineError, new_uuid, normalize_name, normalize_values,
)

FIXTURE = Path(__file__).parents[3] / "mobile/test/fixtures/offline_contract.json"


@pytest.mark.parametrize("vector", json.loads(FIXTURE.read_text(encoding="utf-8"))["vectors"], ids=lambda v: v["name"])
def test_android_normalization_vectors(vector):
    if "error" in vector:
        with pytest.raises(OfflineError) as caught:
            normalize_values(vector["input"])
        assert caught.value.code == "validation"
    else:
        assert normalize_values(vector["input"]) == vector["expected"]


@pytest.mark.parametrize("field,limit", [("driver_name", 200), ("helper_name", 200), ("station", 150), ("plate_number", 30), ("remarks", 10000)])
def test_limits_count_unicode_codepoints(field, limit):
    values = dict(driver_name="Driver", audit_date="2024-02-29", station="Station", plate_number="TEST")
    values[field] = "😀" * limit
    assert normalize_values(values)[field] == "😀" * limit
    values[field] += "😀"
    with pytest.raises(OfflineError):
        normalize_values(values)


@pytest.mark.parametrize("name", [None, 2, "", "\u0085 ", "X" * 201])
def test_profile_rejects_invalid_names(name):
    with pytest.raises(OfflineError):
        normalize_name(name)


def test_profile_is_immutable_and_uuid_is_v4():
    profile = LocalProfile(new_uuid(), normalize_name("\u0085 A\u001c \u0085"))
    assert profile.name == "A\u001c"
    assert UUID(profile.id).version == 4
    with pytest.raises(FrozenInstanceError):
        profile.name = "Changed"
