"""AgentRegistry: dinamikusan tölti be és példányosítja az összes *Agent config-szekciót."""

from __future__ import annotations

import importlib
import re
from typing import List, Optional, Tuple

from src.config import cfg
from src.security import log_event


class AgentRegistry:
    """
    Iterál a config.sections()-on; minden *Agent végű szekciót betölt.

    Névkonvenció (pl. DeveloperAgent):
      - szekció neve:  DeveloperAgent
      - modul neve:    developer_agent
      - osztály neve:  DeveloperAgent
    """

    def __init__(self) -> None:
        self._agents: dict[str, object] = {}
        self._load()

    @staticmethod
    def _section_to_module(section: str) -> str:
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", section).lower()
        return name

    def _load(self) -> None:
        for section in cfg.sections():
            if not section.endswith("Agent"):
                continue
            module_name = self._section_to_module(section)
            full_module = f"src.agents.{module_name}"
            try:
                mod = importlib.import_module(full_module)
                cls = getattr(mod, section)
                instance = cls(section, cfg)
                self._agents[section] = instance
                log_event("AGENT_LOADED", f"{section} from {full_module}")
            except ModuleNotFoundError:
                log_event("AGENT_MISSING_MODULE", f"{full_module} – kihagyva")
            except AttributeError:
                log_event("AGENT_MISSING_CLASS", f"Class {section!r} not in {full_module}")
            except Exception as exc:
                log_event("AGENT_LOAD_ERROR", f"{section}: {exc}")

    def get(self, name: str) -> Optional[object]:
        return self._agents.get(name)

    def list(self) -> List[Tuple[str, str, str]]:
        result: List[Tuple[str, str, str]] = []
        for name, agent in self._agents.items():
            display = getattr(agent, "display_name", name)
            desc = getattr(agent, "description", "")
            result.append((name, display, desc))
        return result
