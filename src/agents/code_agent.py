"""CodeAgent: Python/Go/JS hibakeresés és javítás – qwen2.5-coder:7b."""

from __future__ import annotations

import configparser

from src.agents.base_agent import BaseAgent


class CodeAgent(BaseAgent):
    """Kódolási és hibakeresési agent."""

    def __init__(self, cfg_section: str, config: configparser.ConfigParser) -> None:
        super().__init__(cfg_section, config)

    def system_prompt(self, task: str) -> str:
        return (
            "Te egy kód-hibakereső és javító agent vagy. "
            "Magyarul magyarázz, angolul írj kódot.\n\n"
            "SZABÁLYOK:\n"
            "1. Azonosítsd a hibát pontosan (hiba típusa, sor, ok).\n"
            "2. Adj javított kódot ```python / ```go / ```js blokkban.\n"
            "3. Egy mondatban magyarázd el a javítást.\n"
            "4. Ne generálj felesleges kódot a megoldáson túl.\n\n"
            f"Feladat: {task}"
        )
