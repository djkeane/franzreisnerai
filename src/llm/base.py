"""Absztrakt LLM kliens — minden adapter ezt valósítja meg."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class LLMResponse:
    """Egységes LLM válasz formátum."""
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    quality_score: float = 1.0   # 0.0–1.0, later computed

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMRequest:
    """Egységes LLM kérés formátum."""
    messages: list[dict]
    system: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048
    stream: bool = False
    task_type: str = "general"   # code | research | hungarian | general


class BaseLLMClient(ABC):
    """Minden LLM adapter alaposztálya."""

    provider: str = "unknown"

    @abstractmethod
    def chat(self, request: LLMRequest) -> LLMResponse:
        """Szinkron chat hívás."""
        ...

    @abstractmethod
    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Streaming chat hívás — szövegrészleteket yield-el."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Visszaadja hogy az adapter elérhető-e (API kulcs megvan?)."""
        ...

    def _score_response(self, text: str) -> float:
        """Válasz minőségének egyszerű pontozása (0.0–1.0)."""
        if not text or len(text) < 10:
            return 0.0
        if text.startswith("[HIBA]") or text.startswith("[ERROR]"):
            return 0.1
        # Hosszabb, részletesebb válasz = jobb
        score = min(len(text) / 500, 1.0) * 0.5
        # Magyar tartalom bónusz
        hu_chars = sum(1 for c in text if c in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ")
        score += min(hu_chars / 20, 0.3)
        score += 0.2  # alap pontszám
        return min(score, 1.0)
