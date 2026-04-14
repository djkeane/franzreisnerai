"""Plugin/hook loader: scans plugins/ for *.py files and exposes trigger_hook()."""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Any, Callable, Dict

from src.security import FRANZ_DIR, log_event

_PLUGINS_DIR = FRANZ_DIR / "plugins"
_hooks: Dict[str, Callable[[str, str], Any]] = {}


def load_hooks() -> None:
    """Import every non-private *.py file from the plugins/ directory."""
    _hooks.clear()
    if not _PLUGINS_DIR.is_dir():
        return
    for fpath in sorted(_PLUGINS_DIR.glob("*.py")):
        if fpath.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(fpath.stem, fpath)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if hasattr(mod, "hook") and callable(mod.hook):
                _hooks[fpath.stem] = mod.hook
                log_event("PLUGIN_LOADED", fpath.stem)
        except Exception as exc:
            log_event("PLUGIN_ERROR", f"{fpath.stem}: {exc}")


def trigger_hook(name: str, args: str) -> bool:
    """
    Call hook *name* with *args* in every loaded plugin that defines it.
    Returns True if at least one plugin handled the call.
    """
    handled = False
    for plugin_name, hook_fn in _hooks.items():
        try:
            result = hook_fn(name, args)
            if result:
                handled = True
        except Exception as exc:
            log_event("PLUGIN_ERROR", f"{plugin_name}.hook({name!r}): {exc}")
    return handled


def list_hooks() -> list[str]:
    """Return names of all loaded plugin hooks."""
    return sorted(_hooks.keys())
