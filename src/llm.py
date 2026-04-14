"""LLM wrapper: Ollama → Gemini → Claude fallback chain with streaming support."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Dict, Generator, List, Optional, Tuple

try:
    import requests as _req
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from src.config import cfg
from src.security import log_event

# ── Config ─────────────────────────────────────────────────────
def _build_url(raw: str) -> str:
    u = raw.strip().rstrip("/")
    return u if u.endswith("/api/chat") else u + "/api/chat"


OLLAMA_URLS: List[str] = [
    _build_url(u)
    for u in cfg.get("ollama", "url", fallback="http://localhost:11434").split(",")
    if u.strip()
]
OLLAMA_TIMEOUT = cfg.getint("ollama", "timeout", fallback=60)
DEFAULT_MODEL = cfg.get("ollama", "default_model", fallback="jarvis-hu-coder:latest")
FALLBACK_MODELS: List[str] = [
    m.strip()
    for m in cfg.get("ollama", "fallback_models", fallback="jarvis-hu:latest").split(",")
    if m.strip()
]
GEMINI_MODEL = cfg.get("gemini", "model", fallback="gemini-1.5-flash")
STREAM_OUTPUT = cfg.getboolean("agent", "streaming", fallback=True)
MAX_TOOL_STEPS = cfg.getint("agent", "max_tool_steps", fallback=10)

# ── Stream Parser ──────────────────────────────────────────────
TOOL_OPEN = "```tool\n"
TOOL_CLOSE = "\n```"


class StreamParser:
    """Separates plain text from embedded ```tool ... ``` blocks during streaming."""

    def __init__(self) -> None:
        self.text_parts: List[str] = []
        self.tool_calls: List[Dict] = []
        self._buf = ""
        self._in_tool = False
        self._tool_buf = ""

    def feed(self, chunk: str) -> str:
        """Process one chunk; return printable text portion."""
        printable = ""
        for ch in chunk:
            self._buf += ch
            if self._in_tool:
                self._tool_buf += ch
                if self._tool_buf.endswith(TOOL_CLOSE):
                    raw = self._tool_buf[: -len(TOOL_CLOSE)].strip()
                    try:
                        self.tool_calls.append(json.loads(raw))
                    except json.JSONDecodeError as exc:
                        log_event("TOOL_PARSE_ERROR", f"{exc}: {raw[:80]}")
                    self._in_tool = False
                    self._tool_buf = ""
                    self._buf = ""
            else:
                if self._buf.endswith(TOOL_OPEN):
                    pre = self._buf[: -len(TOOL_OPEN)]
                    if pre:
                        self.text_parts.append(pre)
                        printable += pre
                    self._in_tool = True
                    self._tool_buf = ""
                    self._buf = ""
                elif len(self._buf) > len(TOOL_OPEN):
                    safe = self._buf[: -len(TOOL_OPEN)]
                    self.text_parts.append(safe)
                    printable += safe
                    self._buf = self._buf[-len(TOOL_OPEN):]
        return printable

    def flush(self) -> str:
        if self._buf and not self._in_tool:
            rem, self._buf = self._buf, ""
            self.text_parts.append(rem)
            return rem
        self._buf = ""
        return ""

    @property
    def full_text(self) -> str:
        return "".join(self.text_parts)


def parse_tool_calls(text: str) -> List[Dict]:
    """Extract all ```tool ... ``` blocks from a full response string."""
    calls: List[Dict] = []
    for m in re.finditer(r"```tool\s*\n(.*?)\n```", text, re.DOTALL):
        try:
            calls.append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass
    return calls


def strip_tool_blocks(text: str) -> str:
    """Remove all ```tool ... ``` blocks from text."""
    return re.sub(r"```tool\s*\n.*?\n```\s*", "", text, flags=re.DOTALL).strip()


# ── Ollama ─────────────────────────────────────────────────────
def ollama_chat(
    model: str,
    messages: List[Dict],
    stream: bool = False,
) -> Optional[str]:
    """
    Call Ollama. Returns the response string (non-streaming) or a requests.Response
    object (streaming). Tries every configured URL in order.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": "30m",  # model marad VRAM-ban 30 percig tétlenség után
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    last_err: Exception = RuntimeError("No Ollama URLs configured")
    for url in OLLAMA_URLS:
        try:
            if _HAS_REQUESTS:
                if stream:
                    # connect timeout rövid (10s), read timeout hosszú (model betöltés)
                    resp = _req.post(url, json=payload, stream=True, timeout=(10, OLLAMA_TIMEOUT))
                    resp.raise_for_status()
                    return resp  # type: ignore[return-value]
                resp = _req.post(url, json=payload, timeout=(10, OLLAMA_TIMEOUT))
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
            # urllib fallback (no streaming)
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as r:
                return json.loads(r.read()).get("message", {}).get("content", "")
        except Exception as exc:
            last_err = exc
            log_event("OLLAMA_ERROR", f"{model}@{url}: {exc}")
    raise ConnectionError(f"All Ollama endpoints failed: {last_err}") from last_err


# ── Gemini ─────────────────────────────────────────────────────
def gemini_chat(prompt: str) -> str:
    """Send a single prompt to Gemini; return the response text."""
    try:
        import google.generativeai as genai  # type: ignore
        client = genai.GenerativeModel(GEMINI_MODEL)
        resp = client.generate_content(prompt)
        return resp.text.strip()
    except Exception as exc:
        log_event("GEMINI_ERROR", str(exc))
        return f"[GEMINI_ERROR] {exc}"


# ── Claude ─────────────────────────────────────────────────────
def claude_chat(prompt: str) -> str:
    """Claude API hívás – ANTHROPIC_API_KEY szükséges."""
    api_key = __import__("os").environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log_event("CLAUDE_FALLBACK", "No ANTHROPIC_API_KEY set")
        return "[CLAUDE-FALLBACK] Set ANTHROPIC_API_KEY environment variable."
    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as exc:
        log_event("CLAUDE_ERROR", str(exc))
        return f"[CLAUDE_ERROR] {exc}"


# ── get_answer ─────────────────────────────────────────────────
def get_answer(messages: List[Dict]) -> str:
    """Ollama (default) → Ollama fallbacks → Gemini → Claude."""
    # 1. Primary model
    try:
        result = ollama_chat(DEFAULT_MODEL, messages, stream=False)
        if result:
            return str(result)
    except Exception as exc:
        log_event("LLM_PRIMARY_FAIL", str(exc))

    # 2. Fallback models
    for model in FALLBACK_MODELS:
        try:
            result = ollama_chat(model, messages, stream=False)
            if result:
                log_event("FALLBACK_OK", f"model={model}")
                return str(result)
        except Exception:
            continue

    # 3. Gemini
    log_event("FALLBACK", "Switching to Gemini")
    user_prompt = messages[-1].get("content", "") if messages else ""
    result = gemini_chat(user_prompt)
    if not result.startswith("[GEMINI_ERROR]"):
        return result

    # 4. Claude
    log_event("FALLBACK", "Switching to Claude")
    return claude_chat(user_prompt)
