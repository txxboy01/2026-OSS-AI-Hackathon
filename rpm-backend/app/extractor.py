import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from .constants import MAX_AI_OUTPUT_BYTES
from .errors import ExtractionFailure
from .prompts import PROVIDER_SCHEMA, SYSTEM_INSTRUCTION


@dataclass(frozen=True, slots=True)
class ExtractionEnvelope:
    status: Literal["completed", "blocked", "invalid"]
    text: str | None = None


class Extractor(Protocol):
    async def extract(self, message: str) -> ExtractionEnvelope: ...
    async def aclose(self) -> None: ...


class GeminiExtractor:
    def __init__(self, settings):
        self.settings = settings
        self.client = genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
            vertexai=False,
            http_options=types.HttpOptions(
                base_url="https://generativelanguage.googleapis.com",
                api_version="v1beta",
                timeout=int(settings.ai_timeout_seconds * 1000),
                # attempts includes the first call: 1 means no retry.
                retry_options=types.HttpRetryOptions(attempts=1),
                client_args={"trust_env": False},
                async_client_args={"trust_env": False},
            ),
        )

    async def extract(self, message):
        try:
            async with asyncio.timeout(self.settings.ai_timeout_seconds):
                response = await self.client.aio.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=[types.Content(role="user", parts=[types.Part(text=message)])],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_json_schema=PROVIDER_SCHEMA,
                        candidate_count=1,
                        max_output_tokens=self.settings.gemini_max_output_tokens,
                        tools=[],
                    ),
                )
        except (TimeoutError, httpx.TimeoutException):
            raise ExtractionFailure("AI_TIMEOUT") from None
        except (errors.APIError, httpx.RequestError):
            raise ExtractionFailure("AI_UNAVAILABLE") from None
        except (ValidationError, ValueError):
            raise ExtractionFailure("AI_OUTPUT_INVALID") from None
        feedback = response.prompt_feedback
        if (
            feedback
            and feedback.block_reason
            and self._value(feedback.block_reason) != "BLOCK_REASON_UNSPECIFIED"
        ):
            return ExtractionEnvelope("blocked")
        candidates = response.candidates or []
        if len(candidates) != 1:
            return ExtractionEnvelope("invalid")
        candidate = candidates[0]
        finish = self._value(candidate.finish_reason)
        if finish in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY"}:
            return ExtractionEnvelope("blocked")
        if finish != "STOP" or not candidate.content:
            return ExtractionEnvelope("invalid")
        chunks = []
        size = 0
        for part in candidate.content.parts or []:
            if part.thought:
                continue
            non_text_fields = set(part.model_dump(exclude_none=True, exclude_defaults=True)) - {
                "text",
                "thought",
                "thought_signature",
            }
            if part.text is None or non_text_fields:
                return ExtractionEnvelope("invalid")
            try:
                size += len(part.text.encode("utf-8"))
            except UnicodeError:
                return ExtractionEnvelope("invalid")
            if size > MAX_AI_OUTPUT_BYTES:
                return ExtractionEnvelope("invalid")
            chunks.append(part.text)
        return ExtractionEnvelope("completed", "".join(chunks))

    @staticmethod
    def _value(value):
        return getattr(value, "value", value)

    async def aclose(self):
        try:
            await self.client.aio.aclose()
        finally:
            self.client.close()
