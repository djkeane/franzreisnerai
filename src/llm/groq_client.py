"""Groq adapter — gyors inferencia, kód és real-time feladatok."""

from __future__ import annotations

import os
import time
from typing import Iterator

from src.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from src.security import log_event


class GroqClient(BaseLLMClient):
    """Groq API kliens — elsődleges LLM, alacsony latencia."""

    provider = "groq"

    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self._client = None

    def _get_client(self):
        """Lazy init — csak ha tényleg szükséges."""
        if self._client is None:
            import groq as groq_sdk
            self._client = groq_sdk.Groq(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("gsk_xxx"))

    def _build_messages(self, request: LLMRequest) -> list[dict]:
        msgs = []
        if request.system:
            msgs.append({"role": "system", "content": request.system})
        elif not any(m.get("role") == "system" for m in request.messages):
            msgs.append({
                "role": "system",
                "content": (
                    "Te Franz vagy, a DömösAiTech intelligens AI asszisztense. "
                    "Magyarul válaszolsz, tömören és pontosan."
                ),
            })
        msgs.extend(request.messages)
        return msgs

    def chat(self, request: LLMRequest) -> LLMResponse:
        """Szinkron Groq hívás."""
        if not self.is_available():
            raise RuntimeError("Groq API kulcs hiányzik (.env GROQ_API_KEY)")

        start = time.time()
        client = self._get_client()

        try:
            completion = client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(request),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except Exception as exc:
            log_event("GROQ_ERROR", str(exc))
            raise

        text = completion.choices[0].message.content or ""
        usage = completion.usage
        latency = (time.time() - start) * 1000

        resp = LLMResponse(
            text=text,
            model=self.model,
            provider=self.provider,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency,
        )
        resp.quality_score = self._score_response(text)
        log_event("GROQ_OK", f"{resp.output_tokens} token, {latency:.0f}ms")
        return resp

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Groq streaming."""
        if not self.is_available():
            raise RuntimeError("Groq API kulcs hiányzik")

        client = self._get_client()
        try:
            stream = client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(request),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception as exc:
            log_event("GROQ_STREAM_ERROR", str(exc))
            yield f"\n[HIBA] Groq stream megszakadt: {exc}"
