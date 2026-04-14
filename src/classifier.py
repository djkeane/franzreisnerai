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
    confidence: float = 0.5  # 0.0–1.0 bizonyossági szint (new!)
    clarification: str = ""  # Ha <0.6 confidence, ezek a kérdések


# ── Kulcsszó halmazok ─────────────────────────────────────────────

_AGENTIC_KEYWORDS = [
    # Magyar cselekvés igék (action verbs)
    "telepít", "telepítsd",           # install
    "készít", "készítsd", "készítsd el",  # create
    "ír", "írj", "írsd",              # write
    "olvas", "olvass el",             # read
    "keress", "keressd",              # search
    "javít", "javítsd", "javítsd meg",  # fix
    "futtat", "futtass", "futtasd le", "futtasd",  # run
    "indít", "indítsd",               # start
    "állít le", "állítsd le",         # stop
    "módosít", "módosítsd",           # modify
    "szerkeszt", "szerkeszd",         # edit
    "elemez", "elemezd",              # analyze
    "ellenőriz", "ellenőrizd",        # check
    "generál", "generáld",            # generate
    "hozz létre",                     # create (phrase)
    "nézd meg",                       # look at
    "csináld meg", "csináld",         # do/make
    "hajtsd végre",                   # execute
    "töröld",                         # delete
    "áthelyez", "helyezd át",         # move
    "másolj", "másold le",            # copy
    "tesztel", "teszteld",            # test
    "deploy",                         # deploy
    "build",                          # build
    "install",                        # install (eng)
    "setup",                          # setup (eng)
    "create",                         # create (eng)
    # Kötőszavak és sorrend-jelzők
    "majd",                           # then
    "aztán",                          # then/after
    "ezután",                         # then/after
    "végül",                          # finally
    "után",                           # after
    "először",                        # first
    "utána",                          # after
    "viszont",                        # but (implies action)
    "közben",                         # meanwhile
    # Szöveg kifejezések
    "step by step",                   # step by step
    "lépésről lépésre",              # step by step (hu)
    "lépés",                          # step
    "sorrend",                        # order/sequence
    "workflow",                       # workflow
    "automatikusan",                  # automatically
    "konfigurál",                     # configure
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
    "hogyan",
    "magyarázd",
    "explain",
    "analyze",
    "architektúra",
    "miért van",
    "milyen",
    "mit jelent",
    "mi a",
    "megmagyarázza",
    "értelmezd",
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
    """Ellenőrzés: van-e >= 1 agentic kulcsszó + indikátor."""
    t = text.lower()
    count = sum(1 for kw in _AGENTIC_KEYWORDS if kw in t)
    # >= 1 agentic keyword már elég, ha nem csak chat-szerű
    return count >= 1


def classify(text: str) -> TaskType:
    """
    Feladat klasszifikálása kulcsszó-alapú pontozás szerint (Phase D.5: confidence + clarification).

    Sorrend:
    1. Agentic (>= 2 agentic keyword) → agent loop szükséges
    2. Think (>= 2 think keyword) → research modell
    3. Code (>= 1 code keyword) → code routing
    4. Fast (>= 1 fast keyword) → hungarian routing
    5. Chat (default) → general routing

    Új: confidence mérés + clarification kérdések bizonytalan taszkokhoz
    """
    t = text.lower()

    # Agentic metric
    agentic_hits = sum(1 for kw in _AGENTIC_KEYWORDS if kw in t)
    # Think metric
    think_hits = sum(1 for kw in _THINK_KEYWORDS if kw in t)
    # Code metric
    code_hits = sum(1 for kw in _CODE_KEYWORDS if kw in t)
    # Fast metric
    fast_hits = sum(1 for kw in _FAST_KEYWORDS if kw in t)

    # 1. Agentic (>= 1 keyword enough if clear action intent)
    if agentic_hits >= 1:
        # High confidence if clear multi-step language
        confidence = min(0.95, 0.65 + (agentic_hits - 1) * 0.1)
        return TaskType("agentic", True, "code", confidence=confidence)

    # 2. Think (>= 1 keyword enough)
    if think_hits >= 1:
        confidence = 0.75 + (think_hits - 1) * 0.05
        return TaskType("think", False, "research", confidence=min(confidence, 1.0))

    # 3. Code
    if code_hits >= 1:
        # Medium confidence for code questions
        confidence = 0.7
        clarification = ""
        if code_hits == 1 and not any(w in t for w in ["javít", "debug", "hiba", "error"]):
            clarification = "Szeretnéd, hogy javítsam meg a kódot, vagy csak magyaráztam?"
            confidence = 0.5
        return TaskType("code", False, "code", confidence=confidence, clarification=clarification)

    # 4. Fast
    if fast_hits >= 1:
        return TaskType("fast", False, "hungarian", confidence=0.65)

    # 5. Chat (default) — LOW confidence, kérdezz vissza ha túl rövid
    confidence = 0.3 if len(t) < 20 else 0.45
    clarification = ""
    if len(t) < 15:
        clarification = "Kérlek fejtsd ki részletesebben, mit szeretnél tenni?"
    return TaskType("chat", False, "hungarian", confidence=confidence, clarification=clarification)
