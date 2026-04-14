"""Topic-memory management: JSONL storage, snapshot, revert, search."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
from typing import Dict, List, Optional

from src.security import FRANZ_DIR, log_event

MEMORY_DIR = FRANZ_DIR / "memory"
ACTIVE_TOPIC_FILE = MEMORY_DIR / ".active_topic"

_ENTRY_SCHEMA = {
    "type": "object",
    "required": ["timestamp", "role", "content"],
    "properties": {
        "timestamp": {"type": "string"},
        "role": {"type": "string", "enum": ["user", "assistant", "system", "tool"]},
        "content": {"type": "string"},
    },
}


def _validate_entry(entry: Dict) -> bool:
    """Basic schema check without jsonschema dependency."""
    required = {"timestamp", "role", "content"}
    valid_roles = {"user", "assistant", "system", "tool"}
    return (
        required.issubset(entry.keys())
        and isinstance(entry.get("timestamp"), str)
        and isinstance(entry.get("role"), str)
        and entry.get("role") in valid_roles
        and isinstance(entry.get("content"), str)
    )


def _topic_path(topic: str) -> pathlib.Path:
    safe = re.sub(r"[/\\ ]", "_", topic)
    return MEMORY_DIR / f"{safe}.jsonl"


def set_active_topic(topic: str) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_TOPIC_FILE.write_text(topic, encoding="utf-8")


def get_active_topic() -> str:
    try:
        return ACTIVE_TOPIC_FILE.read_text(encoding="utf-8").strip() or "default"
    except FileNotFoundError:
        return "default"


def list_topics() -> List[str]:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return sorted({p.stem for p in MEMORY_DIR.glob("*.jsonl")})


def load_topic_history(topic: str) -> List[Dict]:
    """Load all valid JSONL entries; skip malformed lines."""
    path = _topic_path(topic)
    history: List[Dict] = []
    if not path.is_file():
        return history
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                history.append(json.loads(line))
            except json.JSONDecodeError:
                log_event("MEMORY_PARSE_ERROR", f"Skipped malformed line in {path.name}")
    return history


def save_memory(topic: str, role: str, content: str) -> None:
    """Append one JSON entry to the topic JSONL file."""
    entry: Dict = {
        "timestamp": datetime.datetime.now().isoformat(),
        "role": role,
        "content": content,
    }
    if not _validate_entry(entry):
        log_event("SECURITY", f"Memory schema validation failed for role={role!r}")
        return

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with _topic_path(topic).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def make_snapshot(topic: str) -> str:
    """Copy the topic file to a timestamped backup; return backup path."""
    src = _topic_path(topic)
    if not src.is_file():
        return ""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = src.with_suffix(f".jsonl.bak-{ts}")
    shutil.copy2(src, dst)
    log_event("SNAPSHOT", f"{topic} → {dst.name}")
    return str(dst)


def revert_snapshot(topic: str, backup_name: str) -> bool:
    """Restore a backup over the current topic file."""
    src = MEMORY_DIR / backup_name
    dst = _topic_path(topic)
    if not src.is_file():
        log_event("REVERT_ERROR", f"{backup_name} not found")
        return False
    shutil.copy2(src, dst)
    log_event("REVERT", f"{topic} ← {backup_name}")
    return True


def search_memory(
    topic: str,
    query: str,
    role: Optional[str] = None,
    limit: int = 5,
) -> List[Dict]:
    """Case-insensitive substring search with optional role filter."""
    results = [
        e
        for e in load_topic_history(topic)
        if (not role or e.get("role") == role)
        and query.lower() in e.get("content", "").lower()
    ]
    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results[:limit]


def truncate_history(messages: List[Dict], keep: int = 24) -> List[Dict]:
    """Keep system messages + the most recent *keep* non-system messages."""
    system = [m for m in messages if m.get("role") == "system"]
    body = [m for m in messages if m.get("role") != "system"]
    return system + body[-keep:]
