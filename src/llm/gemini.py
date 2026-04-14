"""Gemini adapter — Google AI Studio API (gemini-1.5-flash/pro)."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Iterator

from src.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from src.security import log_event


class GeminiClient(BaseLLMClient):
    """Google Gemini API kliens — HU szöveg + hosszú kontextus."""

    provider = "gemini"

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self._base_url = (
            "https://generativelanguage.googleapis.com/v1beta/models"
            f"/{self.model}:generateContent?key={self.api_key}"
        )

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key != "AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    def _build_payload(self, request: LLMRequest) -> dict:
        """Üzenetek → Gemini API formátum."""
        contents = []

        # Rendszer prompt hozzáadása az első user üzenethez
        sys_text = request.system or (
            "Te Franz vagy, a DömösAiTech intelligens AI asszisztense. "
            "Magyarul válaszolsz, tömören és pontosan."
        )

        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                continue  # system külön kezelve
            if role == "assistant":
                role = "model"
            contents.append({"role": role, "parts": [{"text": content}]})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Helló"}]}]

        # System instruction (Gemini 1.5 feature)
        return {
            "system_instruction": {"parts": [{"text": sys_text}]},
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

    def chat(self, request: LLMRequest) -> LLMResponse:
        """Szinkron Gemini hívás."""
        if not self.is_available():
            raise RuntimeError("Gemini API kulcs hiányzik (.env GEMINI_API_KEY)")

        start = time.time()
        payload = json.dumps(self._build_payload(request)).encode()
        req = urllib.request.Request(
            self._base_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except Exception as exc:
            log_event("GEMINI_ERROR", str(exc))
            raise

        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        usage = data.get("usageMetadata", {})
        latency = (time.time() - start) * 1000

        resp = LLMResponse(
            text=text,
            model=self.model,
            provider=self.provider,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=latency,
        )
        resp.quality_score = self._score_response(text)
        log_event("GEMINI_OK", f"{resp.output_tokens} token, {latency:.0f}ms")
        return resp

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Streaming Gemini hívás (SSE szimulálva blokkos hívással)."""
        # Gemini streaming bonyolult urllib-el — egyszerű fallback: chat()
        resp = self.chat(request)
        # Szimulált stream: szavanként yield
        words = resp.text.split(" ")
        for i, word in enumerate(words):
            yield word + ("" if i == len(words) - 1 else " ")
