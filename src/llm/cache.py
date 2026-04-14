"""Fájl alapú LLM cache — API límit és költség csökkentés."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from src.security import log_event


class LLMCache:
    """Egyszerű fájl cache — azonos prompt → tárolt válasz, TTL-lel."""

    def __init__(self, cache_dir: str = ".cache", ttl_hours: int = 24) -> None:
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl_sec = ttl_hours * 3600

    def _key(self, messages: list[dict], model: str) -> str:
        """Cache kulcs = prompt + modell hash."""
        raw = json.dumps(messages, ensure_ascii=False) + model
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, messages: list[dict], model: str) -> str | None:
        """Visszaadja a cache-elt választ, ha él és nem járt le."""
        path = self.dir / f"{self._key(messages, model)}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data["ts"] > self.ttl_sec:
                path.unlink(missing_ok=True)
                return None
            log_event("CACHE_HIT", path.name)
            return data["text"]
        except Exception:
            return None

    def set(self, messages: list[dict], model: str, text: str) -> None:
        """Választ cache-el."""
        path = self.dir / f"{self._key(messages, model)}.json"
        try:
            path.write_text(
                json.dumps({"ts": time.time(), "text": text}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            log_event("CACHE_WRITE_ERROR", str(exc))

    def clear_expired(self) -> int:
        """Lejárt cache fájlok törlése. Visszaadja a törölt darabszámot."""
        count = 0
        for f in self.dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if time.time() - data["ts"] > self.ttl_sec:
                    f.unlink()
                    count += 1
            except Exception:
                f.unlink(missing_ok=True)
                count += 1
        return count

    def stats(self) -> dict:
        """Cache statisztikák."""
        files = list(self.dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "bejegyzések": len(files),
            "méret_kb": round(total_size / 1024, 1),
            "könyvtár": str(self.dir),
        }
