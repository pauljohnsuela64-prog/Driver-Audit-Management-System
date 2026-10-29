"""Pure serialization checks: no API, database, server or production configuration."""
import json
from datetime import datetime, timezone

import pytest
from starlette.responses import JSONResponse

from backend.schemas.audit_api import AuditResponse, EventPage, EventResponse


LIMIT = 2 * 1024 * 1024


def maximum_snapshot(character, version):
    return AuditResponse(
        id=2147483647,
        version=version,
        driver_name=character * 200,
        helper_name=character * 200,
        audit_date="9999-12-31",
        station=character * 150,
        plate_number=character * 30,
        remarks=character * 10000,
        audited_by_name=character * 200,
        audited_by_user_id=2147483647,
        updated_by_user_id=2147483647,
        deleted_by_user_id=None,
        deleted_at=None,
        created_at=datetime.max.replace(tzinfo=timezone.utc),
        updated_at=datetime.max.replace(tzinfo=timezone.utc),
    ).model_dump(mode="json")


def serialized_page(character, count):
    before = maximum_snapshot(character, 2147483646)
    after = maximum_snapshot(character, 2147483647)
    page = EventPage(
        items=[
            EventResponse(
                id=2147483647 - count + index,
                audit_id=2147483647,
                actor_user_id=2147483647,
                action="UPDATE",
                before_data=before,
                after_data=after,
                created_at=datetime.max.replace(tzinfo=timezone.utc),
            )
            for index in range(count)
        ],
        page=1,
        page_size=count,
        total=count,
    )
    # Same serializer used by FastAPI responses; json.dumps defaults would
    # misrepresent Unicode escaping and the actual transport-size contract.
    return JSONResponse(page.model_dump(mode="json")).body


@pytest.mark.parametrize("character", ["\x00", "\U0001f69a"])
def test_ten_maximum_history_events_fit_without_truncation(character):
    body = serialized_page(character, 10)
    assert len(body) < LIMIT
    decoded = json.loads(body)
    assert decoded["page_size"] == 10
    assert len(decoded["items"]) == 10
    assert all(len(event[side]["remarks"]) == 10000
               for event in decoded["items"]
               for side in ("before_data", "after_data"))
    assert decoded["items"][-1]["after_data"]["remarks"] == character * 10000
    if character == "\x00":
        assert b"\\u0000" in body
        assert b"\x00" not in body


def test_twenty_five_worst_case_history_events_exceed_the_transport_limit():
    # List pages remain25, but history cannot safely share that page size.
    assert len(serialized_page("\x00", 25)) > LIMIT
