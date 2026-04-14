"""DeveloperAgent: generates code, Dockerfiles, unit tests, and Git commands."""

from __future__ import annotations

import configparser

from src.agents.base_agent import BaseAgent


class DeveloperAgent(BaseAgent):
    """Specialised agent for code-generation tasks."""

    def __init__(self, cfg_section: str, config: configparser.ConfigParser) -> None:
        super().__init__(cfg_section, config)

    def system_prompt(self, task: str) -> str:
        return (
            "Te egy **Developer Agent** vagy, amely Python/Go/Node.js kódot, "
            "Dockerfile‑t, unit‑teszteket és Git‑parancsokat generál. "
            "A válaszban kizárólag a kódrészlet szerepeljen markdown‑code‑blokkban.\n\n"
            f"**Feladat:** {task}"
        )
