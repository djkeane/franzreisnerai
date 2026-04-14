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
# Nyelvi kérdésekhez erősebb modell — jarvis-hu-coder ha elérhető, különben qwen2.5-coder:7b
_LANG_MODEL = cfg.get("ollama", "lang_model",
                       fallback=cfg.get("DeveloperAgent", "model",
                                        fallback="jarvis-hu-coder:latest"))

# ── Természetes nyelvű tanulási minták ───────────────────────
_LEARN_RE = re.compile(
    r"""
    ^(
      tanulj(\s+meg)?|
      tanuld\s+meg|
      jegyezd\s+meg|
      tárold\s+el|
      memoriz[aá]ld
    )\s+
    """,
    re.IGNORECASE | re.VERBOSE,
)

_FORGET_RE = re.compile(
    r"^(felejtsd\s+(el)?|töröld\s+(ki)?|felejts\s+el)\s+",
    re.IGNORECASE,
)

_EVOLVE_RE = re.compile(
    r"^(fejl[oő]d(j)?|fejlesszd\s+magad|tanultakat\s+beépít)",
    re.IGNORECASE,
)

_LIST_RE = re.compile(
    r"^(mit\s+tudsz|mit\s+tanultál|tudásod|tudáslist[aá])",
    re.IGNORECASE,
)


def natural_to_command(user_input: str) -> str | None:
    """
    Természetes nyelvű tanulási kérést slash-paranccá alakít.
    Visszaadja az átírást, vagy None-t ha nem tanulási kérés.

    Pl.: 'tanulj meg valamit' → '/tanul valamit'
         'felejtsd el az IP-t' → '/felejtsd az IP-t'
         'fejlődj' → '/fejlodj'
    """
    s = user_input.strip()

    m = _LEARN_RE.match(s)
    if m:
        rest = s[m.end():].strip()
        return f"/tanul {rest}" if rest else None

    if _FORGET_RE.match(s):
        rest = _FORGET_RE.sub("", s).strip()
        return f"/felejtsd {rest}" if rest else None

    if _EVOLVE_RE.match(s):
        return "/fejlodj"

    if _LIST_RE.match(s):
        return "/tudom"

    return None


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
