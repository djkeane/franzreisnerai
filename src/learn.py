"""
Franz tanulási rendszer — RAG alapú tudásbázis + Modelfile önfejlesztés.

Rétegek:
  1. learn()    — szöveg/URL beágyazása és tárolása (nomic-embed-text)
  2. recall()   — koszinusz-hasonlóság alapú visszakeresés
  3. forget()   — bejegyzések törlése
  4. bake()     — a legjobb tudás beépítése a Modelfile SYSTEM promptba
                  → ollama create franz-coder → Franz valóban fejlődik
"""

from __future__ import annotations

import datetime
import json
import math
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

from src.security import FRANZ_DIR, log_event

# ── Útvonalak ─────────────────────────────────────────────────
MEMORY_DIR   = FRANZ_DIR / "memory"
KNOWLEDGE_DB = MEMORY_DIR / "knowledge.jsonl"
MODELFILE    = FRANZ_DIR / "Modelfile.franz-coder"
OLLAMA_URL   = "http://localhost:11434"

_EMBED_MODEL = "nomic-embed-text:latest"


# ─────────────────────────────────────────────────────────────
# Embedding (Ollama nomic-embed-text)
# ─────────────────────────────────────────────────────────────

def _embed(text: str) -> list[float]:
    """Szöveg → float vektor az Ollama /api/embeddings végponton."""
    payload = json.dumps({"model": _EMBED_MODEL, "prompt": text[:4096]}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("embedding", [])
    except Exception as exc:
        log_event("EMBED_ERROR", str(exc))
        return []


def _cosine(a: list[float], b: list[float]) -> float:
    """Koszinusz-hasonlóság két vektoron."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ─────────────────────────────────────────────────────────────
# Tudásbázis CRUD
# ─────────────────────────────────────────────────────────────

def _load_all() -> list[dict]:
    if not KNOWLEDGE_DB.is_file():
        return []
    entries = []
    with KNOWLEDGE_DB.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _save_all(entries: list[dict]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with KNOWLEDGE_DB.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def learn(
    text: str,
    source: str = "user",
    tags: list[str] | None = None,
) -> str:
    """
    Szöveg megtanulása: beágyaz + JSONL-be ment.
    Visszaadja az új bejegyzés ID-ját.
    """
    text = text.strip()
    if not text:
        return ""

    vec = _embed(text)
    if not vec:
        log_event("LEARN_WARN", "Embedding sikertelen, szöveg mentése embedding nélkül.")

    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.datetime.now().isoformat(),
        "source": source,
        "tags": tags or [],
        "text": text,
        "embedding": vec,
        "access_count": 0,
        "core": False,          # /core paranccsal jelölhető Modelfile-ba
    }

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with KNOWLEDGE_DB.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log_event("LEARN", f"[{entry['id']}] {text[:80]} (source={source})")
    return entry["id"]


def recall(query: str, top_k: int = 3, min_score: float = 0.3) -> list[dict]:
    """
    RAG visszakeresés: query embedding → top_k legközelebbi tudásbejegyzés.
    Csak min_score fölötti találatokat ad vissza.
    Mellékhatás: növeli az access_count-ot a találatokon.
    """
    entries = _load_all()
    if not entries:
        return []

    q_vec = _embed(query)
    if not q_vec:
        # Embedding nélkül: kulcsszavas fallback
        q_lower = query.lower()
        return [
            e for e in entries
            if any(w in e.get("text", "").lower() for w in q_lower.split())
        ][:top_k]

    scored = []
    for e in entries:
        ev = e.get("embedding", [])
        score = _cosine(q_vec, ev) if ev else 0.0
        scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [(s, e) for s, e in scored if s >= min_score][:top_k]

    if results:
        # access_count frissítése
        ids_to_update = {e["id"] for _, e in results}
        updated = []
        for e in entries:
            if e.get("id") in ids_to_update:
                e["access_count"] = e.get("access_count", 0) + 1
            updated.append(e)
        _save_all(updated)

    return [e for _, e in results]


def forget(pattern: str) -> int:
    """
    Töröl minden bejegyzést ahol a szöveg tartalmazza a mintát (case-insensitive).
    Visszaadja a törölt bejegyzések számát.
    """
    entries = _load_all()
    before = len(entries)
    kept = [e for e in entries if pattern.lower() not in e.get("text", "").lower()]
    _save_all(kept)
    removed = before - len(kept)
    log_event("FORGET", f"'{pattern}' → {removed} törölt bejegyzés")
    return removed


def mark_core(entry_id: str, value: bool = True) -> bool:
    """Egy bejegyzést 'core'-nak jelöl → Modelfile-ba kerül a bake()-kor."""
    entries = _load_all()
    found = False
    for e in entries:
        if e.get("id") == entry_id:
            e["core"] = value
            found = True
    if found:
        _save_all(entries)
    return found


def list_knowledge(limit: int = 20) -> list[dict]:
    """Visszaadja a legutóbbi / leggyakrabban elért bejegyzéseket."""
    entries = _load_all()
    entries.sort(key=lambda e: (e.get("access_count", 0), e.get("timestamp", "")), reverse=True)
    return entries[:limit]


# ─────────────────────────────────────────────────────────────
# URL tartalom letöltése
# ─────────────────────────────────────────────────────────────

def fetch_url(url: str, max_chars: int = 4000) -> str:
    """URL tartalom letöltése — HTML tag-ek eltávolítása után."""
    if not url.startswith(("http://", "https://")):
        return f"[HIBA] Csak http/https URL-ek engedélyeztek: {url}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Franz/5.0 (+DömösAiTech)"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(max_chars * 3).decode("utf-8", errors="replace")
        # HTML tag-ek eltávolítása
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        return f"[HIBA] {exc}"


# ─────────────────────────────────────────────────────────────
# Modelfile önfejlesztés (bake)
# ─────────────────────────────────────────────────────────────

_BAKE_MARKER_START = "# ── Tanult tudás (auto-generált) ──"
_BAKE_MARKER_END   = "# ── Tanult tudás vége ──"


def bake(max_facts: int = 15, min_access: int = 0) -> str:
    """
    A core vagy sokat hívott bejegyzéseket beépíti a Modelfile SYSTEM promptba,
    majd újra-buildeli a franz-coder:latest modellt.

    Visszaadja az eredmény szöveget.
    """
    entries = _load_all()
    # Core bejegyzések + sokat elért nem-core-ok
    core = [e for e in entries if e.get("core")]
    popular = sorted(
        [e for e in entries if not e.get("core")],
        key=lambda e: e.get("access_count", 0),
        reverse=True,
    )
    selected = (core + popular)[:max_facts]

    if not selected:
        return "Nincs tanult tudás amit beépíthetnék."

    if not MODELFILE.is_file():
        return f"[HIBA] Modelfile nem található: {MODELFILE}"

    # Beépítendő szöveg összeállítása
    facts_block = "\n".join(
        f"- [{e.get('id','?')}] {e.get('text','')[:200]}"
        for e in selected
    )
    inject = (
        f"\n{_BAKE_MARKER_START}\n"
        f"Az alábbi tényeket megtanultam és biztosan tudok róluk:\n"
        f"{facts_block}\n"
        f"{_BAKE_MARKER_END}\n"
    )

    # Modelfile szerkesztése: régi beépített blokk cseréje
    content = MODELFILE.read_text(encoding="utf-8")
    # Régi blokk eltávolítása
    cleaned = re.sub(
        rf"{re.escape(_BAKE_MARKER_START)}.*?{re.escape(_BAKE_MARKER_END)}\n?",
        "",
        content,
        flags=re.DOTALL,
    )
    # SYSTEM """ blokkon belülre injektálás (a záró """ elé)
    if 'SYSTEM """' in cleaned:
        cleaned = cleaned.replace('"""', inject + '"""', 1)
        # Az első occurrence helyettesítése nem lesz jó ha SYSTEM """\n...
        # Pontosabb: a záró """ elé rakjuk
        cleaned = re.sub(
            r'(SYSTEM """)(.*?)(""")',
            lambda m: m.group(1) + m.group(2).rstrip() + "\n" + inject + m.group(3),
            cleaned,
            count=1,
            flags=re.DOTALL,
        )
    else:
        cleaned += f'\nSYSTEM """{inject}"""\n'

    MODELFILE.write_text(cleaned, encoding="utf-8")
    log_event("BAKE_MODELFILE", f"{len(selected)} tény beépítve")

    # ollama create újrabuildelés
    import subprocess
    result = subprocess.run(
        ["ollama", "create", "franz-coder", "-f", str(MODELFILE)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(FRANZ_DIR),
    )
    if result.returncode == 0:
        msg = f"✓ {len(selected)} tény beépítve → franz-coder:latest újrabuildelve."
    else:
        msg = f"[WARN] Modelfile frissítve, de ollama create hibát adott:\n{result.stderr[:300]}"

    log_event("BAKE_DONE", msg)
    return msg


# ─────────────────────────────────────────────────────────────
# Gyors context-inject a system promptba
# ─────────────────────────────────────────────────────────────

def context_for(query: str, top_k: int = 3) -> str:
    """
    A rendszer-promptba injektálandó tudáskontextus.
    Üres stringet ad ha nincs releváns tudás.
    """
    hits = recall(query, top_k=top_k, min_score=0.35)
    if not hits:
        return ""
    lines = ["Releváns tanult tudás:"]
    for h in hits:
        lines.append(f"  • {h.get('text','')[:300]}")
    return "\n".join(lines)
