"""Franz feladat-típus osztályozó — kulcsszó-alapú pontozás (Phase C)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TaskType:
    """Feladat osztályozási eredmény."""

    type: str  # "agentic"|"code"|"think"|"fast"|"chat"
    is_agentic: bool
    model_hint: str  # Router kulcs: "code"|"research"|"hungarian"|"general"


# ── Kulcsszó halmazok ─────────────────────────────────────────────

_AGENTIC_KEYWORDS = [
    "telepít",
    "majd",
    "aztán",
    "deploy",
    "lépés",
    "csináld meg",
    "automatikusan",
    "futtat",
    "konfigurál",
    "generál",
    "hozz létre",
    "módosítsd",
    "szerkeszd",
    "keress és",
    "ellenőrizd majd",
    "futtasd le",
    "install",
    "setup",
    "build",
    "create project",
    "step by step",
    "lépésről lépésre",
    "majd indítsd",
    "hajtsd végre",
    "sorrend",
    "workflow",
]

_CODE_KEYWORDS = [
    "python",
    "def ",
    "class ",
    "bug",
    "error",
    "hiba",
    "kód",
    "script",
    "import",
    "docker",
    "git",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
]

_THINK_KEYWORDS = [
    "miért",
    "hogyan működik",
    "magyarázd",
    "explain",
    "analyze",
    "architektúra",
    "miért van",
    "milyen a",
    "hogy működik",
]

_FAST_KEYWORDS = [
    "mi az",
    "ki az",
    "mikor",
    "hány",
    "fordítsd",
    "röviden",
    "quickly",
    "mi volt",
    "ki volt",
]


def _is_agentic(text: str) -> bool:
    """Ellenőrzés: van-e >= 2 agentic kulcsszó?"""
    t = text.lower()
    count = sum(1 for kw in _AGENTIC_KEYWORDS if kw in t)
    return count >= 2


def classify(text: str) -> TaskType:
    """
    Feladat klasszifikálása kulcsszó-alapú pontozás szerint.

    Sorrend:
    1. Agentic (>= 2 agentic keyword) → agent loop szükséges
    2. Think (>= 2 think keyword) → research modell
    3. Code (>= 1 code keyword) → code routing
    4. Fast (>= 1 fast keyword) → hungarian routing
    5. Chat (default) → general routing
    """
    t = text.lower()

    # 1. Agentic
    if _is_agentic(t):
        return TaskType("agentic", True, "code")

    # 2. Think
    think_hits = sum(1 for kw in _THINK_KEYWORDS if kw in t)
    if think_hits >= 2:
        return TaskType("think", False, "research")

    # 3. Code
    code_hits = sum(1 for kw in _CODE_KEYWORDS if kw in t)
    if code_hits >= 1:
        return TaskType("code", False, "code")

    # 4. Fast
    fast_hits = sum(1 for kw in _FAST_KEYWORDS if kw in t)
    if fast_hits >= 1:
        return TaskType("fast", False, "hungarian")

    # 5. Chat (default)
    return TaskType("chat", False, "hungarian")
