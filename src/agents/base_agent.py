"""BaseAgent abstract class for all Franz agents."""

from __future__ import annotations

import configparser
from abc import ABC, abstractmethod
from typing import Dict, List

from src.security import log_event


class BaseAgent(ABC):
    """Abstract base for all agents. Subclasses must implement system_prompt()."""

    def __init__(self, cfg_section: str, config: configparser.ConfigParser) -> None:
        self.name = cfg_section
        self.display_name = config.get(cfg_section, "display_name", fallback=cfg_section)
        self.description = config.get(cfg_section, "description", fallback="")
        self.topic_prefix = config.get(cfg_section, "topic_prefix", fallback=cfg_section.lower() + "_")
        self.model = config.get(cfg_section, "model", fallback="jarvis-hu-coder:latest")
        self.temperature = config.getfloat(cfg_section, "temperature", fallback=0.2)

    @abstractmethod
    def system_prompt(self, task: str) -> str:
        """Return the system prompt for this agent given a task description."""

    def chat(self, messages: List[Dict]) -> str:
        """Send messages to the configured model via Ollama, fallback to Gemini."""
        from src.llm import gemini_chat, ollama_chat

        try:
            result = ollama_chat(self.model, messages, stream=False)
            return str(result) if result else ""
        except Exception as exc:
            log_event("AGENT_ERROR", f"{self.name}: {exc}")
            user_content = messages[-1].get("content", "") if messages else ""
            return gemini_chat(user_content)
