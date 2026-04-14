"""Automatikus model-router: kulcsszó alapján választ kód vs. nyelvi agent között."""

from __future__ import annotations

import re
from typing import Tuple

from src.config import cfg
from src.security import log_event

# ── Kód-kapcsolódó kulcsszavak ────────────────────────────────
_CODE_PATTERNS = re.compile(
    r"""
    \b(
      # Hibatípusok
      error|exception|traceback|hiba|hibaüzenet|
      indexerror|typeerror|valueerror|attributeerror|
      keyerror|nameerror|syntaxerror|importerror|
      runtimeerror|assertionerror|recursionerror|
      oserror|filenotfounderror|permissionerror|
      zerodivisionerror|overflowerror|memoryerror|
      # Kód kulcsszavak
      def|class|import|return|function|async|await|
      lambda|yield|decorator|görög|script|modul|
      # Debug szavak
      javít|fix|debug|hib[aá]|stack.?trace|log|
      # Technológiák
      python|go\b|golang|javascript|typescript|bash|sql|
      docker|kubernetes|git|pytest|unittest|
      # Fájlok / parancsok
      \.py|\.go|\.js|\.ts|\.sh|\.yaml|\.json|\.toml|
      pip|npm|cargo|make|cmake
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Modellek a configból
_CODE_MODEL = cfg.get("CodeAgent", "model", fallback="qwen2.5-coder:7b")
_LANG_MODEL = cfg.get("ollama", "default_model", fallback="franz-coder:latest")


def route(user_input: str) -> Tuple[str, str]:
    """
    Visszaadja (model, agent_type) párt.
    agent_type: 'code' | 'lang'
    """
    hits = len(_CODE_PATTERNS.findall(user_input))
    if hits >= 1:
        log_event("ROUTER", f"code ({hits} hit) → {_CODE_MODEL}")
        return _CODE_MODEL, "code"
    log_event("ROUTER", f"lang → {_LANG_MODEL}")
    return _LANG_MODEL, "lang"
