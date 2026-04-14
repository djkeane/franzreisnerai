"""OpenRouter adapter — fallback LLM, sok modell egységes API-n."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Iterator

from src.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from src.security import log_event

_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient(BaseLLMClient):
    """OpenRouter API kliens — fallback, ingyenes modellek."""

    provider = "openrouter"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")

    def is_available(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("sk-or-v1-xxx"))

    def _build_messages(self, request: LLMRequest) -> list[dict]:
        """Üzenetek összeállítása OpenAI-kompatibilis formátumba."""
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
        """Szinkron OpenRouter hívás."""
        if not self.is_available():
            raise RuntimeError("OpenRouter API kulcs hiányzik (.env OPENROUTER_API_KEY)")

        start = time.time()
        payload = json.dumps({
            "model": self.model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }).encode()

        req = urllib.request.Request(
            _API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://domosaitech.hu",
                "X-Title": "Franz CLI Agent",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except Exception as exc:
            log_event("OPENROUTER_ERROR", str(exc))
            raise

        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        latency = (time.time() - start) * 1000

        resp = LLMResponse(
            text=text,
            model=data.get("model", self.model),
            provider=self.provider,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency,
        )
        resp.quality_score = self._score_response(text)
        log_event("OPENROUTER_OK", f"{resp.output_tokens} token, {latency:.0f}ms")
        return resp

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """OpenRouter streaming (SSE)."""
        if not self.is_available():
            raise RuntimeError("OpenRouter API kulcs hiányzik")

        payload = json.dumps({
            "model": self.model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }).encode()

        req = urllib.request.Request(
            _API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://domosaitech.hu",
                "X-Title": "Franz CLI Agent",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                for raw_line in r:
                    line = raw_line.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError):
                            continue
        except Exception as exc:
            log_event("OPENROUTER_STREAM_ERROR", str(exc))
            yield f"\n[HIBA] OpenRouter stream megszakadt: {exc}"
