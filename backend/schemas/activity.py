from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

Action = Literal["CREATE", "PROFILE_UPDATE", "ROLE_CHANGE", "ACTIVATED", "DEACTIVATED", "PASSWORD_RESET", "PASSWORD_CHANGE"]


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_user_id: int
    target_user_id: int
    action: Action
    changes: dict | None
    created_at: datetime


class ActivityPage(BaseModel):
    items: list[ActivityResponse]
    total: int
    page: int
    page_size: int
