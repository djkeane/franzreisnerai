"""Ollama adapter — offline/helyi fallback a meglévő src/llm.py alapján."""

from __future__ import annotations

import json
import time
from typing import Iterator

from src.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from src.security import log_event


class OllamaClient(BaseLLMClient):
    """Ollama helyi LLM — offline fallback, a meglévő ollama_chat()-ot hívja."""

    provider = "ollama"

    def __init__(self) -> None:
        # Lazy import hogy elkerüljük a körkörös importot
        from src.llm import pick_best_model
        self.model = pick_best_model()

    def is_available(self) -> bool:
        return True  # Ollama lokálisan mindig feltételezett

    def chat(self, request: LLMRequest) -> LLMResponse:
        from src.llm import ollama_chat
        start = time.time()
        try:
            text = ollama_chat(self.model, request.messages) or ""
        except Exception as exc:
            log_event("OLLAMA_ERROR", str(exc))
            text = f"[HIBA] Ollama: {exc}"
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.provider,
            latency_ms=(time.time() - start) * 1000,
            quality_score=self._score_response(text),
        )

    def stream(self, request: LLMRequest) -> Iterator[str]:
        from src.llm import ollama_chat
        try:
            resp = ollama_chat(self.model, request.messages, stream=True)
            if resp is None:
                yield "[HIBA] Ollama nem válaszolt"
                return
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                    chunk = obj.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                except Exception:
                    continue
        except Exception as exc:
            yield f"\n[HIBA] Ollama stream: {exc}"
