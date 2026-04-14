"""Diagnostics command: system health overview for Franz."""

from __future__ import annotations

import os
import pathlib
import urllib.request

try:
    import requests as _req
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    from rich.console import Console
    _console = Console(highlight=False)
    _RICH = True
except ImportError:
    _RICH = False
    _console = None  # type: ignore[assignment]

from src.config import cfg
from src.llm import OLLAMA_URLS
from src.security import FRANZ_DIR, LOG_DIR, log_event


def run_diagnostics() -> None:
    """Print a comprehensive health report to stdout."""
    memory_dir = FRANZ_DIR / "memory"

    _h("=== Franz v5.0 Diagnostics ===")

    # ── Directory permissions ──────────────────────────────────
    _h("\nKönyvtár jogosultságok")
    for d in [FRANZ_DIR, memory_dir, LOG_DIR]:
        if d.exists():
            mode = oct(d.stat().st_mode)[-3:]
            _p(f"  {d}: {mode}")
        else:
            _p(f"  {d}: [hiányzik]")

    # ── Configuration ──────────────────────────────────────────
    _h("\nKonfiguráció (franz.cfg)")
    for sec in cfg.sections():
        _p(f"  [{sec}]")
        for k, v in cfg[sec].items():
            # mask webhook URLs
            display_v = v if "webhook" not in k.lower() else (v[:20] + "…" if v else "(nincs)")
            _p(f"    {k} = {display_v}")

    # ── Memory & log sizes ─────────────────────────────────────
    _h("\nTárhely")
    mem_sz = sum(f.stat().st_size for f in memory_dir.glob("*.jsonl")) if memory_dir.exists() else 0
    log_sz = sum(f.stat().st_size for f in LOG_DIR.glob("*.log")) if LOG_DIR.exists() else 0
    _p(f"  Memória fájlok : {mem_sz / 1024:.1f} KB")
    _p(f"  Log fájlok     : {log_sz / 1024:.1f} KB")

    # ── Ollama endpoints ───────────────────────────────────────
    _h("\nOllama végpontok")
    for url in OLLAMA_URLS:
        tags_url = url.replace("/api/chat", "/api/tags")
        try:
            if _HAS_REQUESTS:
                r = _req.get(tags_url, timeout=4)
                models = [m["name"] for m in r.json().get("models", [])]
                _p(f"  OK {url}")
                _p(f"     Modellek: {', '.join(models[:6]) or '(nincs)'}")
            else:
                urllib.request.urlopen(tags_url, timeout=4)
                _p(f"  OK {url}")
        except Exception as exc:
            _p(f"  HIBA {url}: {exc}")

    # ── API keys ───────────────────────────────────────────────
    _h("\nAPI kulcsok")
    _p(f"  Gemini      : {'megvan' if os.getenv('GEMINI_API_KEY') else 'hiányzik'}")
    _p(f"  Anthropic   : {'megvan' if os.getenv('ANTHROPIC_API_KEY') else 'hiányzik'}")

    # ── Agents ────────────────────────────────────────────────
    try:
        from src.agents import AgentRegistry
        registry = AgentRegistry()
        agents = registry.list()
        _h(f"\nBetöltött agensek ({len(agents)})")
        for name, display, desc in agents:
            _p(f"  • {display}: {desc}")
    except Exception as exc:
        _p(f"  Agensek nem tölthetők be: {exc}")

    # ── Plugins ────────────────────────────────────────────────
    try:
        from src.hooks import list_hooks
        hooks = list_hooks()
        _h(f"\nBetöltött pluginok ({len(hooks)})")
        for h in hooks:
            _p(f"  • {h}")
    except Exception as exc:
        _p(f"  Pluginok nem tölthetők be: {exc}")

    _h("")


def _h(text: str) -> None:
    if _RICH:
        _console.print(f"[bold cyan]{text}[/bold cyan]")
    else:
        print(text)


def _p(text: str) -> None:
    if _RICH:
        _console.print(text)
    else:
        print(text)
