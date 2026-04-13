# -*- coding: utf-8 -*-
from agents import BaseAgent


class DeveloperAgent(BaseAgent):
    def system_prompt(self, task: str) -> str:
        return (
            "Te egy **Developer Agent** vagy, amely Python/Go/Node.js kódot, "
            "Dockerfile‑t, unit‑testet és Git‑parancsokat generál. "
            "Kérlek, adj a válaszodban csak a kódrészletet markdown‑blokkban."
            f"\n\n**Feladat:** {task}"
        )
