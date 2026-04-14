"""Security utilities: whitelist, path sanitizer, resource limits, privilege drop, logging, alerts."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import pwd
import resource
import urllib.request
from typing import Optional

from src.config import cfg

# ── Constants from config ──────────────────────────────────────
FRANZ_DIR = pathlib.Path(os.environ.get("FRANZ_DIR", pathlib.Path.home() / "Franz"))
LOG_DIR = FRANZ_DIR / "logs"

SAFE_COMMANDS: set[str] = {
    c.strip()
    for c in cfg.get("security", "whitelist", fallback="ls,cat,git").split(",")
    if c.strip()
}
CPU_SOFT = cfg.getint("security", "cpu_soft", fallback=5)
CPU_HARD = cfg.getint("security", "cpu_hard", fallback=10)
MEM_LIMIT = cfg.getint("security", "mem_limit_mb", fallback=200) * 1024 * 1024
SECURITY_WEBHOOK = cfg.get("security", "alert_webhook", fallback="").strip()

# Session log (one file per run)
_SESSION_LOG: Optional[pathlib.Path] = None


def _get_session_log() -> pathlib.Path:
    global _SESSION_LOG
    if _SESSION_LOG is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        _SESSION_LOG = LOG_DIR / f"session_{ts}.log"
    return _SESSION_LOG


def log_event(event_type: str, message: str) -> None:
    """Append a timestamped entry to the session log file."""
    ts = datetime.datetime.now().isoformat()
    _get_session_log().parent.mkdir(parents=True, exist_ok=True)
    with _get_session_log().open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {event_type}: {message}\n")
    if event_type in {"DENIED", "EXCEPTION", "SECURITY", "PLUGIN_ERROR"}:
        alert_admin(event_type, message)


def alert_admin(event_type: str, message: str) -> None:
    """POST a JSON alert to the configured webhook URL (swallows errors)."""
    if not SECURITY_WEBHOOK:
        return
    payload = json.dumps({"text": f":warning: Franz {event_type}: {message}"}).encode()
    try:
        req = urllib.request.Request(
            SECURITY_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass


def safe_path(requested: str) -> Optional[str]:
    """Resolve *requested* relative to FRANZ_DIR; return None if outside."""
    target = pathlib.Path(os.path.abspath(FRANZ_DIR / requested))
    if str(target).startswith(str(FRANZ_DIR)):
        return str(target)
    return None


def limit_resources() -> None:
    """Apply CPU-second and address-space limits to the current process."""
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SOFT, CPU_HARD))
        resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))
    except Exception as exc:
        log_event("RESOURCE_LIMIT_ERROR", str(exc))


def drop_privileges() -> None:
    """If running as root, switch uid/gid to 'nobody'."""
    if os.getuid() != 0:
        return
    try:
        pw = pwd.getpwnam("nobody")
        os.setgid(pw.pw_gid)
        os.setuid(pw.pw_uid)
        log_event("PRIVILEGE_DROP", "Switched to nobody")
    except Exception as exc:
        log_event("PRIVILEGE_DROP_FAILED", str(exc))
