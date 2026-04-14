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

# ── Workflow parancsok ──────────────────────────────────────────
_DIR_RE = re.compile(
    r"^(térképezd\s+fel|listázd|mi\s+van|nézzük\s+meg|nézd\s+meg|mutasd|mi\s+a|mappá)",
    re.IGNORECASE,
)

_SERVERS_RE = re.compile(
    r"(szerver|port|szolgáltatás|daemon|futó\s+folyamat|listening|halgatóz|hallgatóz|szerv)",
    re.IGNORECASE,
)

_CODE_GEN_RE = re.compile(
    r"^(írj|generálj|csináld\s+meg|kódolj|fejlessz)",
    re.IGNORECASE,
)

_WEB_LEARN_RE = re.compile(
    r"(internetről|webrő?l|keress|búvárkodj)\b",
    re.IGNORECASE,
)

_LOOP_RE = re.compile(
    r"^(indítsd|autonóm|loop)",
    re.IGNORECASE,
)


def natural_to_command(user_input: str) -> str | None:
    """
    Természetes nyelvű kérést slash-paranccá alakít.
    Támogatott: tanulás, munkakönyvtár, kódgenerálás, web-tanulás, autonóm loop.

    Pl.: 'tanulj meg valamit' → '/tanul valamit'
         'térképezd fel a mappákat' → '/dir'
         'írj egy fibonacci függvényt' → '/kod írj egy fibonacci függvényt'
         'tanuld meg az internetről pythont' → '/tanul-web python'
         'indítsd el az autonóm loopot' → '/loop'
    """
    s = user_input.strip()

    # ── Tanulási parancsok (prioritás!) ────────────────────────
    m = _LEARN_RE.match(s)
    if m:
        rest = s[m.end():].strip()
        # Ellenőrzés: van-e "internetről" vagy "webrő" a rest-ben?
        if _WEB_LEARN_RE.search(rest):
            # Web-tanulás: "tanuld meg az internetről pythont" → "/tanul-web python"
            # Eltávolítjuk az "az internetről" részt
            web_rest = re.sub(r"az?\s+internet(?:ről|rő?l)", "", rest, flags=re.IGNORECASE).strip()
            return f"/tanul-web {web_rest}" if web_rest else "/tanul-web"
        return f"/tanul {rest}" if rest else None

    if _FORGET_RE.match(s):
        rest = _FORGET_RE.sub("", s).strip()
        return f"/felejtsd {rest}" if rest else None

    if _EVOLVE_RE.match(s):
        return "/fejlodj"

    if _LIST_RE.match(s):
        return "/tudom"

    # ── Workflow parancsok ──────────────────────────────────────

    # Szerver/port lekérdezések (nagyobb prioritás mint /dir)
    # "nézd meg milyen szerverek futnak", "milyen portok vannak nyitva", stb.
    if _SERVERS_RE.search(s):
        if re.search(r"^(nézd\s+meg|mutasd|milyen|mik\s+a|mik\s+az|futó|aktív|ellenőrizd)", s, re.IGNORECASE):
            return "/servers"

    if _DIR_RE.match(s):
        return "/dir"

    if _CODE_GEN_RE.match(s):
        # "írj egy fib függvényt" → "/kod írj egy fib függvényt"
        return f"/kod {s}"

    if _LOOP_RE.match(s):
        return "/loop"

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
