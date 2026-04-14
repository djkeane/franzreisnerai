"""Multi-LLM réteg — Groq, Gemini, OpenRouter, Ollama adapterek + gateway."""

# Megnevezés: src/llm/ csomag (szervezésű) vs src/llm_legacy.py (flat)
from src.llm_legacy import (
    MAX_TOOL_STEPS,
    OLLAMA_URLS,
    STREAM_OUTPUT,
    StreamParser,
    get_answer,
    get_loaded_models,
    ollama_chat,
    parse_tool_calls,
    pick_best_model,
    strip_tool_blocks,
)
from src.llm.gateway import LLMGateway, llm_gateway
from src.llm.base import BaseLLMClient, LLMRequest, LLMResponse

__all__ = [
    # Legacy API
    "MAX_TOOL_STEPS",
    "OLLAMA_URLS",
    "STREAM_OUTPUT",
    "StreamParser",
    "get_answer",
    "get_loaded_models",
    "ollama_chat",
    "parse_tool_calls",
    "pick_best_model",
    "strip_tool_blocks",
    # Új API
    "LLMGateway",
    "llm_gateway",
    "BaseLLMClient",
    "LLMRequest",
    "LLMResponse",
]
