"""
Pydantic models
Structured model outputs
"""

from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str = Field(min_length=1, max_length=100)
    key_points: list[str] = Field(max_length=6)
    sufficient_evidence: bool
    evidence_ids: list[str] = Field(max_length=20)
    limitations: list[str] = Field(max_length=10)


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100)


# for intent classification
class IntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal[
        "ask_booking",
        "ask_information",
        "out_of_scope",
    ]


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question: str = Field(min_length=1, max_length=100)
    history: list[Message] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must contain text")
        return value


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    document_id: str
    title: str
    url: str
    publisher: str
    published_date: str | None
    retrieved_date: str
    content: str
    score: float


class AskResponse(BaseModel): # what the API returns
    model_config = ConfigDict(extra="forbid")
    request_id: str
    question: str
    answer: str
    citations: list[Citation]
    limitations: list[str]
    error: str | None = None

    # unsure how to handle depending on the intent - 1) booking route 2) info route


class VoiceAskResponse(AskResponse):
    transcript : str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "TrustBytes"


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    extracted_claim: str = Field(min_length=1, max_length=6000)
    explanation: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(max_length=20)
    limitations: list[str] = Field(max_length=10)


class ClarificationNeeded(ValueError):
    def __init__(self, message: str, usage: dict | None = None):
        super().__init__(message)
        self.usage = usage or {}


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(max_length=2000)
    publisher: str = Field(min_length=1, max_length=200)
    published_date: date | None = None
    retrieved_date: date
    fixture: bool = False

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Source URL must be a public HTTP(S) URL without credentials")
        if any(c.isspace() for c in value):
            raise ValueError("Source URL cannot contain whitespace")
        return value
