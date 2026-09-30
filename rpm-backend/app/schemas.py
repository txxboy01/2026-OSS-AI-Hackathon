from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import (
    ACTION_LABELS,
    FALLBACK_NOTICE,
    GUIDANCE_NOTICE,
    LIMITATION,
    NO_ACTION_NOTICE,
    VERIFIED_NOTICE,
    ActionType,
    FallbackReason,
    SensitiveType,
    UserAction,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_default=True, hide_input_in_errors=True)


class AnalyzeRequest(StrictModel):
    messageText: str = Field(min_length=1, max_length=5000)
    consentToExternalAi: bool


class Span(StrictModel):
    start: int = Field(ge=0, le=9999)
    end: int = Field(ge=1, le=10000)

    @model_validator(mode="after")
    def ordered(self):
        if self.start >= self.end:
            raise ValueError("invalid span")
        return self


class RawEvidence(StrictModel):
    type: ActionType
    quote: str = Field(min_length=1, max_length=500)

    @field_validator("quote")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("invalid quote")
        return value


class RawExtraction(StrictModel):
    evidence: list[RawEvidence] = Field(max_length=12)


class Evidence(StrictModel):
    id: str = Field(pattern=r"^e([1-9]|1[0-2])$")
    type: ActionType
    label: str
    quote: str = Field(min_length=1, max_length=500)
    spans: list[Span] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def consistent(self):
        if self.label != ACTION_LABELS[self.type]:
            raise ValueError("invalid label")
        if [(s.start, s.end) for s in self.spans] != sorted({(s.start, s.end) for s in self.spans}):
            raise ValueError("invalid span order")
        return self


class AnalysisBase(StrictModel):
    requestId: str
    apiVersion: Literal["1.0"] = "1.0"
    limitation: Literal[LIMITATION] = LIMITATION
    offsetUnit: Literal["utf16"] = "utf16"


class VerifiedResponse(AnalysisBase):
    mode: Literal["ai"] = "ai"
    status: Literal["VERIFIED"] = "VERIFIED"
    evidence: list[Evidence] = Field(min_length=1, max_length=12)
    reasonCode: None = None
    notice: Literal[VERIFIED_NOTICE] = VERIFIED_NOTICE


class NoActionResponse(AnalysisBase):
    mode: Literal["ai"] = "ai"
    status: Literal["NO_ACTION_FOUND"] = "NO_ACTION_FOUND"
    evidence: list[Evidence] = Field(default_factory=list, max_length=0)
    reasonCode: None = None
    notice: Literal[NO_ACTION_NOTICE] = NO_ACTION_NOTICE


class FallbackResponse(AnalysisBase):
    mode: Literal["fallback"] = "fallback"
    status: Literal["FALLBACK"] = "FALLBACK"
    evidence: list[Evidence] = Field(default_factory=list, max_length=0)
    reasonCode: FallbackReason
    notice: Literal[FALLBACK_NOTICE] = FALLBACK_NOTICE


AnalyzeResponse = Annotated[
    VerifiedResponse | NoActionResponse | FallbackResponse, Field(discriminator="status")
]


class GuidanceRequest(StrictModel):
    actions: list[UserAction] = Field(min_length=1, max_length=7)

    @field_validator("actions")
    @classmethod
    def valid_combination(cls, actions):
        if len(set(actions)) != len(actions):
            raise ValueError("duplicate action")
        if len(actions) > 1 and {"NOT_INTERACTED", "UNKNOWN"} & set(actions):
            raise ValueError("exclusive action")
        return actions


StepCode = Literal[
    "G_DEVICE", "G_BANK", "G_STOP", "G_CLOSE", "G_PASSWORD", "G_SESSIONS", "G_PRIVACY", "G_VERIFY", "G_HELP"
]


class GuidanceStep(StrictModel):
    code: StepCode
    priority: Literal[10, 20, 30, 40, 50, 60, 70, 80, 90]
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=500)


class GuidanceResponse(StrictModel):
    requestId: str
    apiVersion: Literal["1.0"] = "1.0"
    guidanceVersion: Literal["1.0"] = "1.0"
    actions: list[UserAction] = Field(min_length=1, max_length=7)
    urgency: Literal["routine", "prompt", "urgent"]
    steps: list[GuidanceStep] = Field(min_length=2, max_length=9)
    notice: Literal[GUIDANCE_NOTICE] = GUIDANCE_NOTICE
    limitation: Literal[LIMITATION] = LIMITATION


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    service: Literal["rpm-backend"] = "rpm-backend"
    apiVersion: Literal["1.0"] = "1.0"


class ErrorDetail(StrictModel):
    code: Literal[
        "INVALID_JSON",
        "INVALID_REQUEST",
        "CONSENT_REQUIRED",
        "INPUT_POLICY_VIOLATION",
        "SENSITIVE_DATA_DETECTED",
        "PAYLOAD_TOO_LARGE",
        "UNSUPPORTED_MEDIA_TYPE",
        "RATE_LIMITED",
        "SERVICE_BUSY",
        "INTERNAL_ERROR",
        "NOT_FOUND",
        "METHOD_NOT_ALLOWED",
    ]
    message: str = Field(min_length=1, max_length=300)
    fields: list[Literal["messageText", "consentToExternalAi", "actions"]] = Field(
        default_factory=list, max_length=3
    )
    detectedTypes: list[SensitiveType] = Field(default_factory=list, max_length=7)


class ErrorResponse(StrictModel):
    requestId: str
    apiVersion: Literal["1.0"] = "1.0"
    error: ErrorDetail
