"""DebugAgent: analyses logs, stack traces, systemd status, Docker/k8s output."""

from __future__ import annotations

import configparser

from src.agents.base_agent import BaseAgent


class DebugAgent(BaseAgent):
    """Specialised agent for debugging and log-analysis tasks."""

    def __init__(self, cfg_section: str, config: configparser.ConfigParser) -> None:
        super().__init__(cfg_section, config)

    def system_prompt(self, task: str) -> str:
        return (
            "Te egy **Debug Agent** vagy, amely log‑fájlokat, stack‑trace‑eket, "
            "systemd‑service‑státuszokat és Docker/k8s‑debug információkat elemez. "
            "Adj lépés‑ről‑lépésre útmutatást a hiba azonosításához és javításához.\n\n"
            f"**Feladat:** {task}"
        )
