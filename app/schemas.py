"""Public HTTP response contracts. Never expose ORM/password/session internals."""
from typing import Literal
from pydantic import BaseModel, Field

class FieldError(BaseModel):
    field: str = Field(examples=['body.username'])
    message: str

class ErrorDetail(BaseModel):
    code: int = Field(examples=[409])
    message: str = Field(examples=['Время уже занято.'])
    fields: list[FieldError] | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail

class HealthResponse(BaseModel):
    status: Literal['ok']

class OkResponse(BaseModel):
    ok: Literal[True]

class TopicResponse(BaseModel):
    id: int
    name: str

class SlotResponse(BaseModel):
    id: int
    starts_at: int = Field(description='Unix timestamp, UTC seconds')
    ends_at: int = Field(description='Unix timestamp, UTC seconds; duration 900 seconds')
    location: str
    is_demo: bool

class ConfigResponse(BaseModel):
    topics: list[TopicResponse]
    slots: list[SlotResponse]
    demo_enabled: bool

class PublicProfile(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"id": 1, "name": "Анна", "role": "Аналитик", "company": "", "bio": "Хочу обсудить API", "wanted": [1], "offered": [2], "availability": [1], "visible": True, "is_demo": False}]}}
    id: int
    name: str
    role: str
    company: str
    bio: str
    wanted: list[int]
    offered: list[int]
    availability: list[int]
    visible: bool
    is_demo: bool

class PrivateProfile(PublicProfile):
    model_config = {"json_schema_extra": {"examples": [{**PublicProfile.model_config["json_schema_extra"]["examples"][0], "username": "anna", "is_admin": False}]}}
    username: str
    is_admin: bool

class RecommendationResponse(BaseModel):
    user: PublicProfile
    score: int = Field(description='3 × learn matches + 2 × share matches + other common topics')
    learn_topics: list[int]
    share_topics: list[int]
    common_topics: list[int]
    slot_ids: list[int] = Field(description='Common available slots ordered chronologically')

InvitationStatus = Literal['pending','accepted','declined','cancelled','conflict','expired']

class InvitationCreated(BaseModel):
    id: int
    status: Literal['pending']

class InvitationActionResponse(BaseModel):
    status: Literal['accepted','declined','cancelled']

class FeedbackResponse(BaseModel):
    happened: bool
    useful: bool | None

class InvitationResponse(BaseModel):
    id: int
    incoming: bool
    other: PublicProfile
    slot_id: int
    topic_id: int
    message: str
    status: InvitationStatus
    feedback: FeedbackResponse | None

class SlotCreated(BaseModel):
    id: int

class TopicStats(BaseModel):
    name: str
    participants: int

class StatsResponse(BaseModel):
    profiles: int
    active_profiles: int
    participants_with_meeting: int
    invitations: int
    ever_accepted: int
    cancelled_after_accept: int
    confirmed_meetings: int
    positive_ratings: int
    ratings: int
    feedback_responses: int
    demo_excluded: Literal[True]
    topics: list[TopicStats]
