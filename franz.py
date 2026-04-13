#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================
#   Franz – Agentic Terminal AI  v4.0
#   Fejlesztő: DömösAiTech 2026
# ==============================================================

import os, sys, json, datetime, subprocess, pathlib, shutil
import configparser, importlib.util, resource, pwd, readline, atexit
import urllib.request, html, re, signal
from typing import List, Dict, Optional, Tuple

# ── Optional deps ──────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax
    _RICH = True
    console = Console(highlight=False)
except ImportError:
    _RICH = False
    class _FakeConsole:
        def print(self, *a, **kw):
            # strip rich markup
            text = " ".join(str(x) for x in a)
            text = re.sub(r'\[/?[^\]]*\]', '', text)
            print(text)
    console = _FakeConsole()

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import requests as _req
    _REQUESTS = True
except ImportError:
    _REQUESTS = False

# ── Dirs & Config ──────────────────────────────────────────────
FRANZ_DIR         = os.path.expanduser("~/Franz")
MEMORY_DIR        = os.path.join(FRANZ_DIR, "memory")
LOG_DIR           = os.path.join(FRANZ_DIR, "logs")
HISTORY_FILE      = os.path.join(FRANZ_DIR, ".history")
ACTIVE_TOPIC_FILE = os.path.join(MEMORY_DIR, ".active_topic")
SESSION_LOG       = os.path.join(
    LOG_DIR, f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

CFG_PATH = os.path.join(FRANZ_DIR, "franz.cfg")
config = configparser.ConfigParser()
config.read(CFG_PATH)

def _build_url(u: str) -> str:
    u = u.strip().rstrip("/")
    return u if u.endswith("/api/chat") else u + "/api/chat"

OLLAMA_URLS     = [_build_url(u) for u in config.get("ollama", "url", fallback="http://localhost:11434").split(",") if u.strip()]
OLLAMA_TIMEOUT  = config.getint("ollama", "timeout", fallback=60)
DEFAULT_MODEL   = config.get("ollama", "default_model", fallback="jarvis-hu-coder:latest")
FALLBACK_MODELS = [m.strip() for m in config.get("ollama", "fallback_models", fallback="jarvis-hu:latest").split(",")]
GEMINI_MODEL    = config.get("gemini", "model", fallback="gemini-1.5-flash")
SECURITY_WEBHOOK = config.get("security", "alert_webhook", fallback="").strip()
MAX_TOOL_STEPS  = config.getint("agent", "max_tool_steps", fallback=10)
STREAM_OUTPUT   = config.getboolean("agent", "streaming", fallback=True)

# ── Logging ────────────────────────────────────────────────────
def log_event(event_type: str, message: str) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.datetime.now().isoformat()
    with open(SESSION_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {event_type}: {message}\n")
    if event_type in {"DENIED", "EXCEPTION", "SECURITY", "PLUGIN_ERROR"}:
        _alert_admin(event_type, message)

def _alert_admin(event_type: str, message: str) -> None:
    if not SECURITY_WEBHOOK:
        return
    payload = json.dumps({"text": f":warning: Franz {event_type}: {message}"}).encode()
    try:
        req = urllib.request.Request(SECURITY_WEBHOOK, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass

# ── Output helpers ─────────────────────────────────────────────
def print_franz(text: str) -> None:
    if _RICH:
        console.print(Panel(Markdown(text), title="[bold blue]Franz[/]",
                            border_style="blue", padding=(0, 1)))
    else:
        print(f"\033[1;34mFranz:\033[0m {text}\n")

def print_tool_call(name: str, args: dict) -> None:
    args_str = json.dumps(args, ensure_ascii=False)
    if len(args_str) > 120:
        args_str = args_str[:117] + "..."
    if _RICH:
        console.print(f"  [dim]🔧 [bold cyan]{name}[/bold cyan]({args_str})[/dim]")
    else:
        print(f"  🔧 {name}({args_str})")

def print_tool_result(result: str) -> None:
    preview = result[:300] + ("…" if len(result) > 300 else "")
    if _RICH:
        console.print(f"  [dim green]→ {preview}[/dim green]\n")
    else:
        print(f"  → {preview}\n")

def print_info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]" if _RICH else msg)

def print_ok(msg: str) -> None:
    console.print(f"[bold green]✓[/bold green] {msg}" if _RICH else f"✓ {msg}")

def print_error(msg: str) -> None:
    console.print(f"[bold red]✗[/bold red] {msg}" if _RICH else f"✗ {msg}")

# ── Readline setup ─────────────────────────────────────────────
_COMPLETIONS = [
    "exit", "quit", "help", "diagnosztizál", "topics", "snapshot", "hooks",
    "topic:", "reset:", "revert:", "search:", "dev:", "debug:",
    "hook:",
]

def setup_readline() -> None:
    readline.set_completer_delims(" \t\n")
    readline.parse_and_bind("tab: complete")

    def _completer(text, state):
        options = [c for c in _COMPLETIONS if c.startswith(text)]
        return options[state] if state < len(options) else None

    readline.set_completer(_completer)
    os.makedirs(FRANZ_DIR, exist_ok=True)
    try:
        readline.read_history_file(HISTORY_FILE)
    except FileNotFoundError:
        pass
    readline.set_history_length(2000)
    atexit.register(readline.write_history_file, HISTORY_FILE)

# ── Multi-line input ───────────────────────────────────────────
def get_input(prompt_str: str) -> str:
    r"""Bevitel: \ = soremelés-folytatás, ``` blokk = paste mód."""
    first = input(prompt_str).strip()
    if not first:
        return ""

    if first.endswith("\\"):
        lines = [first[:-1]]
        while True:
            try:
                line = input("... ").rstrip()
                if line.endswith("\\"):
                    lines.append(line[:-1])
                else:
                    lines.append(line)
                    break
            except EOFError:
                break
        return "\n".join(lines)

    if first == "```":
        lines = []
        print("(Paste mód – ``` a végén)")
        while True:
            try:
                line = input("")
                if line.strip() == "```":
                    break
                lines.append(line)
            except EOFError:
                break
        return "\n".join(lines)

    return first

# ── Memory / Topic ─────────────────────────────────────────────
def _topic_path(topic: str) -> str:
    safe = re.sub(r'[/\\ ]', '_', topic)
    return os.path.join(MEMORY_DIR, f"{safe}.jsonl")

def set_active_topic(topic: str) -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    pathlib.Path(ACTIVE_TOPIC_FILE).write_text(topic, encoding="utf-8")

def get_active_topic() -> str:
    try:
        return pathlib.Path(ACTIVE_TOPIC_FILE).read_text(encoding="utf-8").strip() or "default"
    except FileNotFoundError:
        return "default"

def list_topics() -> List[str]:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    return sorted({p.stem for p in pathlib.Path(MEMORY_DIR).glob("*.jsonl")})

def load_topic_history(topic: str) -> List[Dict]:
    path = _topic_path(topic)
    history = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    history.append(json.loads(line.rstrip()))
                except Exception:
                    continue
    return history

def save_memory(topic: str, role: str, content: str) -> None:
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "role": role,
        "content": content,
    }
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
        with open(_topic_path(topic), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log_event("SAVE_MEMORY_ERROR", str(e))

def make_snapshot(topic: str) -> str:
    src = _topic_path(topic)
    if not os.path.isfile(src):
        return ""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"{src}.bak-{ts}"
    shutil.copy2(src, dst)
    log_event("SNAPSHOT", f"{topic} → {dst}")
    return dst

def revert_snapshot(topic: str, backup_file: str) -> bool:
    src = os.path.join(MEMORY_DIR, backup_file)
    dst = _topic_path(topic)
    if not os.path.isfile(src):
        return False
    shutil.copy2(src, dst)
    log_event("REVERT", f"{topic} ← {backup_file}")
    return True

def search_memory(topic: str, query: str, role: Optional[str] = None, limit: int = 5) -> List[Dict]:
    results = [
        e for e in load_topic_history(topic)
        if (not role or e.get("role") == role)
        and query.lower() in e.get("content", "").lower()
    ]
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]

def truncate_history(messages: List[Dict]) -> List[Dict]:
    if not messages:
        return messages
    system = [m for m in messages if m["role"] == "system"]
    body   = [m for m in messages if m["role"] != "system"]
    return system + body[-24:]

# ── System Context ─────────────────────────────────────────────
def _git_context() -> str:
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=2, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--short"],
            stderr=subprocess.DEVNULL, timeout=2, text=True
        ).strip()
        n = len(status.splitlines()) if status else 0
        return f"branch={branch}" + (f", {n} módosítás" if n else ", tiszta")
    except Exception:
        return "nem git repo"

def get_sys_context() -> str:
    cwd  = os.getcwd()
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    git  = _git_context()
    if _PSUTIL:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        hw  = f"CPU {cpu:.0f}% | RAM {mem.percent:.0f}% ({mem.used>>20}MB/{mem.total>>20}MB)"
    else:
        hw = f"platform={sys.platform}"
    return f"Dátum: {date} | CWD: {cwd} | {hw} | Git: {git}"

def build_system_prompt(topic: str) -> str:
    ctx = get_sys_context()
    return f"""Te Franz vagy, egy profi terminál AI-ügynök (DömösAiTech 2026).
Segítsz shell-feladatokban, kódírásban, rendszeradminisztrációban és hibakeresésben.

Kontextus: {ctx}
Aktív topic: {topic}

## Eszközök (Tools)
Feladatokhoz eszközöket használhatsz az alábbi formátumban:

```tool
{{"name": "<eszköz>", "args": {{<JSON argumentumok>}}}}
```

| Eszköz | Argumentumok | Leírás |
|--------|-------------|--------|
| bash | command: str | Bash parancs futtatása |
| read_file | path: str | Fájl beolvasása (max 500 sor) |
| write_file | path: str, content: str | Fájl létrehozása/felülírása |
| list_dir | path: str | Könyvtár listázása |
| git | args: str | Git parancs (pl. "status", "log -5 --oneline") |
| web_fetch | url: str | Weboldal szöveges tartalmának lekérése |

Több eszközt egymás után is használhatsz – az eredmény visszakerül és folytathatsz.
Veszélyes műveletek (rm -rf, stb.) előtt mindig figyelmeztesd a felhasználót.
Válaszolj magyarul, kódot természetes nyelven / angolul."""

# ── Tool Executor ──────────────────────────────────────────────
_DANGER_RE = re.compile(
    r'\brm\s+-[a-z]*r[a-z]*f\s+/'
    r'|\bdd\s+if='
    r'|\bmkfs\b'
    r'|\bfdisk\b'
    r'|:\(\)\s*\{\s*:\|:&\s*\}'
    r'|\bchmod\s+-R\s+777\s+/'
    r'|\bcurl\b.*\|\s*(?:ba)?sh'
    r'|\bwget\b.*\|\s*(?:ba)?sh',
    re.IGNORECASE,
)

def _is_dangerous(cmd: str) -> bool:
    return bool(_DANGER_RE.search(cmd))

def exec_tool(name: str, args: dict) -> str:
    try:
        if name == "bash":
            cmd = args.get("command", "").strip()
            if not cmd:
                return "[HIBA] Üres parancs."
            if _is_dangerous(cmd):
                log_event("TOOL_DANGER", cmd)
                return (
                    f"[FIGYELMEZTETÉS] Potenciálisan veszélyes parancs blokkolva:\n  {cmd}\n"
                    "Ha biztos vagy benne, futtasd manuálisan a terminálban."
                )
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=30, env={**os.environ}
            )
            out = (result.stdout + result.stderr).strip()
            return out[:8000] if out else "(nincs kimenet)"

        elif name == "read_file":
            path = os.path.expanduser(args.get("path", ""))
            txt = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
            lines = txt.splitlines()
            if len(lines) > 500:
                txt = "\n".join(lines[:500]) + f"\n… [{len(lines)-500} sor csonkítva]"
            return txt

        elif name == "write_file":
            path = os.path.expanduser(args.get("path", ""))
            content = args.get("content", "")
            p = pathlib.Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"✓ Fájl írva: {path} ({len(content)} karakter)"

        elif name == "list_dir":
            path = os.path.expanduser(args.get("path", "."))
            items = sorted(pathlib.Path(path).iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = []
            for item in items:
                if item.is_dir():
                    lines.append(f"📁 {item.name}/")
                else:
                    sz = item.stat().st_size
                    lines.append(f"📄 {item.name}  ({sz:,} B)")
            return "\n".join(lines) or "(üres könyvtár)"

        elif name == "git":
            git_args = args.get("args", "")
            result = subprocess.run(
                f"git {git_args}", shell=True, capture_output=True, text=True, timeout=15
            )
            return (result.stdout + result.stderr).strip()[:4000]

        elif name == "web_fetch":
            url = args.get("url", "")
            req = urllib.request.Request(url, headers={"User-Agent": "Franz/4.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read(100_000).decode("utf-8", errors="replace")
            raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
            raw = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.DOTALL)
            raw = re.sub(r'<[^>]+>', '', raw)
            raw = html.unescape(raw)
            raw = re.sub(r'\n{3,}', '\n\n', raw).strip()
            return raw[:6000]

        else:
            return f"[HIBA] Ismeretlen eszköz: {name}"

    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Parancs túl sokáig futott (>30s)."
    except Exception as e:
        log_event("TOOL_ERROR", f"{name}: {e}")
        return f"[HIBA] {name}: {e}"

# ── Stream Parser ──────────────────────────────────────────────
class StreamParser:
    """Streaming szövegből szétválasztja a szöveget és a tool hívásokat."""

    OPEN  = "```tool\n"
    CLOSE = "\n```"

    def __init__(self):
        self.text_parts: List[str] = []
        self.tool_calls: List[Dict] = []
        self._buf      = ""
        self._in_tool  = False
        self._tool_buf = ""

    def feed(self, chunk: str) -> str:
        """Feldolgoz egy chunk-ot, visszaadja a nyomtatható szöveget."""
        printable = ""
        for ch in chunk:
            self._buf += ch

            if self._in_tool:
                self._tool_buf += ch
                if self._tool_buf.endswith(self.CLOSE):
                    tool_json = self._tool_buf[:-len(self.CLOSE)].strip()
                    try:
                        tc = json.loads(tool_json)
                        self.tool_calls.append(tc)
                    except json.JSONDecodeError as e:
                        log_event("TOOL_PARSE_ERROR", f"{e}: {tool_json[:120]}")
                    self._in_tool  = False
                    self._tool_buf = ""
                    self._buf      = ""
            else:
                if self._buf.endswith(self.OPEN):
                    pre = self._buf[:-len(self.OPEN)]
                    if pre:
                        self.text_parts.append(pre)
                        printable += pre
                    self._in_tool  = True
                    self._tool_buf = ""
                    self._buf      = ""
                elif len(self._buf) > len(self.OPEN):
                    safe = self._buf[:-len(self.OPEN)]
                    self.text_parts.append(safe)
                    printable += safe
                    self._buf = self._buf[-len(self.OPEN):]

        return printable

    def flush(self) -> str:
        if self._buf and not self._in_tool:
            self.text_parts.append(self._buf)
            rem, self._buf = self._buf, ""
            return rem
        self._buf = ""
        return ""

    @property
    def full_text(self) -> str:
        return "".join(self.text_parts)

# ── Tool block helpers (non-streaming) ────────────────────────
def _parse_tool_calls(text: str) -> List[Dict]:
    tcs = []
    for m in re.finditer(r'```tool\s*\n(.*?)\n```', text, re.DOTALL):
        try:
            tcs.append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass
    return tcs

def _strip_tool_blocks(text: str) -> str:
    return re.sub(r'```tool\s*\n.*?\n```\s*', '', text, flags=re.DOTALL).strip()

# ── LLM calls ─────────────────────────────────────────────────
def _ollama_call(model: str, messages: List[Dict], stream: bool = False):
    """Ollama hívás – streaming vagy full response. Több endpoint-et próbál."""
    payload = {
        "model": model,
        "messages": truncate_history(messages),
        "stream": stream,
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    last_err = None
    for url in OLLAMA_URLS:
        try:
            if _REQUESTS:
                if stream:
                    resp = _req.post(url, json=payload, stream=True, timeout=OLLAMA_TIMEOUT)
                    resp.raise_for_status()
                    return resp
                else:
                    resp = _req.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
                    resp.raise_for_status()
                    return resp.json().get("message", {}).get("content", "")
            else:
                # urllib fallback (no streaming)
                data = json.dumps(payload).encode()
                req = urllib.request.Request(url, data=data,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as r:
                    return json.loads(r.read()).get("message", {}).get("content", "")
        except Exception as e:
            last_err = e
            log_event("OLLAMA_ERROR", f"{model}@{url}: {e}")
    raise ConnectionError(f"Egyik Ollama endpoint sem elérhető: {last_err}")

def _gemini_chat(prompt: str) -> str:
    try:
        from google import genai
        client = genai.Client()
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return resp.text
    except Exception as e:
        log_event("GEMINI_ERROR", str(e))
        return "⛔ Gemini hiba – nézd a logot."

# ── Agentic Loop ───────────────────────────────────────────────
def agent_loop(messages: List[Dict]) -> str:
    """LLM → tool hívások → eredmény visszacsatolás → ismétlés (max MAX_TOOL_STEPS)."""
    model = DEFAULT_MODEL

    for step in range(MAX_TOOL_STEPS + 1):
        # ── LLM hívás ──
        if STREAM_OUTPUT and _REQUESTS:
            parser = StreamParser()
            try:
                resp = _ollama_call(model, messages, stream=True)
                print(f"\033[1;34mFranz:\033[0m ", end="", flush=True)
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            printable = parser.feed(delta)
                            if printable:
                                print(printable, end="", flush=True)
                        if chunk.get("done"):
                            tail = parser.flush()
                            if tail:
                                print(tail, end="", flush=True)
                            break
                    except json.JSONDecodeError:
                        continue
                print()
                response_text = parser.full_text
                tool_calls    = parser.tool_calls

            except Exception as e:
                log_event("STREAM_ERROR", str(e))
                # Fallback to non-streaming
                try:
                    response_text = _ollama_call(model, messages, stream=False)
                    tool_calls    = _parse_tool_calls(response_text)
                    display       = _strip_tool_blocks(response_text)
                    if display.strip():
                        print_franz(display)
                except Exception as e2:
                    response_text = _gemini_chat(messages[-1].get("content", ""))
                    tool_calls    = []
                    print_franz(response_text)
        else:
            # Non-streaming
            print_info("Gondolkodik…")
            try:
                response_text = _ollama_call(model, messages, stream=False)
            except Exception as e:
                log_event("FALLBACK", str(e))
                for fb_model in FALLBACK_MODELS:
                    try:
                        response_text = _ollama_call(fb_model, messages, stream=False)
                        log_event("FALLBACK_OK", fb_model)
                        break
                    except Exception:
                        continue
                else:
                    response_text = _gemini_chat(messages[-1].get("content", ""))

            tool_calls = _parse_tool_calls(response_text)
            display    = _strip_tool_blocks(response_text)
            if display.strip():
                print_franz(display)

        if not response_text:
            break

        # ── Nincs tool hívás → kész ──
        if not tool_calls:
            return response_text

        # ── Tool végrehajtás ──
        messages.append({"role": "assistant", "content": response_text})

        tool_results = []
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {})
            print_tool_call(name, args)
            result = exec_tool(name, args)
            print_tool_result(result)
            log_event("TOOL", f"{name}: {result[:150]}")
            tool_results.append(
                f"## Eszköz eredménye – {name}\n```\n{result}\n```"
            )

        messages.append({
            "role": "user",
            "content": "\n\n".join(tool_results)
                       + "\n\nFolytasd a feladat elvégzését a fentiek alapján.",
        })

    return response_text or ""

# ── Plugin / Hook ──────────────────────────────────────────────
HOOKS: Dict[str, object] = {}

def load_hooks() -> None:
    plugins_dir = os.path.join(FRANZ_DIR, "plugins")
    if not os.path.isdir(plugins_dir):
        return
    for f in sorted(pathlib.Path(plugins_dir).glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "hook"):
                HOOKS[f.stem] = mod.hook
                log_event("PLUGIN_LOADED", f.stem)
        except Exception as e:
            log_event("PLUGIN_ERROR", f"{f.stem}: {e}")

# ── Agent Registry ─────────────────────────────────────────────
class AgentRegistry:
    def __init__(self):
        self._agents: Dict = {}
        if FRANZ_DIR not in sys.path:
            sys.path.insert(0, FRANZ_DIR)
        for sec in [s for s in config.sections() if s.lower().endswith("agent")]:
            # "DeveloperAgent" → "developer_agent"
            mod_name = sec[0].lower() + sec[1:].replace("Agent", "_agent")
            try:
                spec = importlib.util.find_spec(f"agents.{mod_name}")
                if spec is None:
                    log_event("AGENT_SKIP", f"{sec} – nincs agents.{mod_name}")
                    continue
                mod   = importlib.import_module(f"agents.{mod_name}")
                klass = getattr(mod, sec)
                self._agents[sec] = klass(sec)
                log_event("AGENT_LOADED", sec)
            except Exception as e:
                log_event("AGENT_ERROR", f"{sec}: {e}")

    def get(self, name: str):
        return self._agents.get(name)

    def list(self):
        return [(a.name, a.display_name, a.description) for a in self._agents.values()]

AGENT_REGISTRY = None  # init in main()

# ── Command Handlers ───────────────────────────────────────────
def handle_special_commands(user_input: str, chat_history: List[Dict]) -> bool:
    ui = user_input.strip()

    # help
    if ui.lower() in ("help", "?", "súgó"):
        _print_help()
        return True

    # diagnosztizál
    if ui == "diagnosztizál":
        _run_diagnostics()
        return True

    # topics
    if ui == "topics":
        active = get_active_topic()
        console.print("[bold magenta]Elérhető témák:[/bold magenta]" if _RICH else "Elérhető témák:")
        for t in list_topics():
            mark = " ◀ aktív" if t == active else ""
            console.print(f" • {t}{mark}")
        return True

    # topic: <name>
    if ui.startswith("topic:"):
        name = ui.split(":", 1)[1].strip() or "default"
        set_active_topic(name)
        chat_history.clear()
        chat_history.append({"role": "system", "content": build_system_prompt(name)})
        for e in load_topic_history(name):
            if e.get("role") in ("user", "assistant"):
                chat_history.append(e)
        print_ok(f"Topic: {name}")
        return True

    # reset:
    if ui.startswith("reset"):
        cur = get_active_topic()
        try:
            os.remove(_topic_path(cur))
        except FileNotFoundError:
            pass
        chat_history.clear()
        chat_history.append({"role": "system", "content": build_system_prompt(cur)})
        print_ok(f"{cur} topic törölve.")
        return True

    # snapshot
    if ui == "snapshot":
        cur = get_active_topic()
        bak = make_snapshot(cur)
        if bak:
            print_ok(f"Snapshot: {os.path.basename(bak)}")
        else:
            print_error("Nincs mit menteni (üres topic).")
        return True

    # revert: <file>
    if ui.startswith("revert:"):
        cur = get_active_topic()
        bak = ui.split(":", 1)[1].strip()
        if revert_snapshot(cur, bak):
            chat_history.clear()
            chat_history.append({"role": "system", "content": build_system_prompt(cur)})
            for e in load_topic_history(cur):
                if e.get("role") in ("user", "assistant"):
                    chat_history.append(e)
            print_ok("Visszaállítás sikeres.")
        else:
            print_error("Visszaállítás sikertelen.")
        return True

    # search: <query> [role]
    if ui.startswith("search:"):
        query = ui.split(":", 1)[1].strip()
        role = None
        if " " in query:
            q, maybe = query.rsplit(" ", 1)
            if maybe in {"user", "assistant", "system"}:
                query, role = q, maybe
        hits = search_memory(get_active_topic(), query, role=role)
        if not hits:
            console.print("[yellow]🔍 Nincs találat.[/yellow]" if _RICH else "Nincs találat.")
        else:
            for h in hits:
                ts  = h["timestamp"][:19].replace("T", " ")
                tag = {"user": "🧑", "assistant": "🤖", "system": "⚙️"}.get(h["role"], "?")
                preview = h["content"].replace("\n", " ")[:80]
                console.print(f"{tag} [{ts}] {preview}")
        return True

    # hooks
    if ui == "hooks":
        if HOOKS:
            console.print("[bold]Betöltött hook-ok:[/bold]" if _RICH else "Betöltött hook-ok:")
            for h in sorted(HOOKS):
                console.print(f" • {h}")
        else:
            print_info("Nincs betöltött plugin.")
        return True

    # hook: <name> <args>
    if ui.startswith("hook:"):
        parts = ui[5:].strip().split(None, 1)
        name  = parts[0] if parts else ""
        args  = parts[1] if len(parts) > 1 else ""
        if name in HOOKS:
            try:
                result = HOOKS[name](name, args)
                console.print(result or "(nincs kimenet)")
            except Exception as e:
                log_event("PLUGIN_ERROR", f"{name}: {e}")
                print_error(f"Plugin hiba: {e}")
        else:
            avail = ", ".join(HOOKS) if HOOKS else "nincs"
            print_error(f"Ismeretlen hook: '{name}'. Elérhető: {avail}")
        return True

    # dev: <task>
    if ui.startswith("dev:"):
        _start_agent("DeveloperAgent", ui.split(":", 1)[1].strip(), chat_history)
        return True

    # debug: <task>
    if ui.startswith("debug:"):
        _start_agent("DebugAgent", ui.split(":", 1)[1].strip(), chat_history)
        return True

    return False

def _start_agent(agent_name: str, task: str, chat_history: List[Dict]) -> None:
    agent = AGENT_REGISTRY.get(agent_name)
    if not agent:
        print_error(f"{agent_name} nincs regisztrálva.")
        return
    base  = task.split()[0] if task else "session"
    topic = f"{agent.topic_prefix}{base}"
    set_active_topic(topic)
    chat_history.clear()
    chat_history.append({"role": "system", "content": agent.system_prompt(task)})
    for e in load_topic_history(topic):
        if e.get("role") in ("user", "assistant"):
            chat_history.append(e)
    icon = "🛠️" if "Developer" in agent_name else "🐞"
    print_ok(f"{icon} {agent.display_name} elindítva (topic: {topic})")

def _run_diagnostics() -> None:
    console.print("[bold cyan]=== Franz v4.0 Diagnosztika ===[/bold cyan]" if _RICH else "=== Diagnosztika ===")
    for d in [FRANZ_DIR, MEMORY_DIR, LOG_DIR]:
        mode = oct(os.stat(d).st_mode)[-3:] if os.path.exists(d) else "hiányzik"
        console.print(f" 📁 {d}: jogok={mode}")

    console.print("\n[bold]Konfiguráció:[/bold]" if _RICH else "\nKonfiguráció:")
    for sec in config.sections():
        for k, v in config[sec].items():
            console.print(f"   [{sec}] {k} = {v}")

    mem_sz = sum(f.stat().st_size for f in pathlib.Path(MEMORY_DIR).glob("*.jsonl")) if pathlib.Path(MEMORY_DIR).exists() else 0
    log_sz = sum(f.stat().st_size for f in pathlib.Path(LOG_DIR).glob("*.log")) if pathlib.Path(LOG_DIR).exists() else 0
    console.print(f"\n 💾 Memory: {mem_sz/1024:.1f} KB | 🗒 Log: {log_sz/1024:.1f} KB")

    console.print("\n[bold]Ollama:[/bold]" if _RICH else "\nOllama:")
    for url in OLLAMA_URLS:
        tags_url = url.replace("/api/chat", "/api/tags")
        try:
            if _REQUESTS:
                r = _req.get(tags_url, timeout=3)
                models = [m["name"] for m in r.json().get("models", [])]
                console.print(f"  ✅ {url} – {', '.join(models[:5]) or 'nincs modell'}")
            else:
                urllib.request.urlopen(tags_url, timeout=3)
                console.print(f"  ✅ {url}")
        except Exception as e:
            console.print(f"  ❌ {url}: {e}")

    console.print(f"\n 🔑 Gemini API-kulcs: {'van' if os.getenv('GEMINI_API_KEY') else 'hiányzik'}")
    console.print(f" 🤖 Agensek: {', '.join(a[1] for a in AGENT_REGISTRY.list()) or 'nincs'}")
    console.print(f" 🔌 Pluginek: {', '.join(HOOKS) or 'nincs'}")
    console.print(f" 📡 Streaming: {'be' if STREAM_OUTPUT else 'ki'} | Rich UI: {'be' if _RICH else 'ki'}")

def _print_help() -> None:
    text = """
## Franz v4.0 – Parancsok

### Chat
- `<kérdés>` – AI válasz, eszköz-hívással ha szükséges
- `` ` `` → Enter – paste mód (``` a végén zárja)
- `\\` sor végén – következő sor folytatás

### Agensek
- `dev: <feladat>` – Developer Agent (kódgenerálás)
- `debug: <feladat>` – Debug Agent (log/hibaelemzés)

### Topic / Memória
- `topic: <név>` – Topic váltás
- `topics` – Topic lista
- `reset:` – Topic törlése
- `snapshot` – Backup készítés
- `revert: <fájl>` – Visszaállítás
- `search: <szó> [role]` – Keresés

### Pluginek
- `hook: <név> <args>` – Plugin hívás
- `hooks` – Plugin lista

### Egyéb
- `diagnosztizál` – Rendszer-diagnosztika
- `help` – Ez a súgó
- `exit` / `quit` – Kilépés

### Elérhető eszközök (automatikus)
`bash` · `read_file` · `write_file` · `list_dir` · `git` · `web_fetch`
"""
    if _RICH:
        from rich.panel import Panel
        console.print(Panel(Markdown(text), title="[bold]Súgó[/]", border_style="green"))
    else:
        print(text)

# ── Banner ─────────────────────────────────────────────────────
BANNER = r"""
 ███████╗██████╗  █████╗ ███╗   ██╗███████╗
 ██╔════╝██╔══██╗██╔══██╗████╗  ██║╚══███╔╝
 █████╗  ██████╔╝███████║██╔██╗ ██║  ███╔╝
 ██╔══╝  ██╔══██╗██╔══██║██║╚██╗██║ ███╔╝
 ██║     ██║  ██║██║  ██║██║ ╚████║███████╗
 ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝
   Agentic Terminal AI  v4.0  │  DömösAiTech 2026
"""

# ── Main ───────────────────────────────────────────────────────
def main() -> None:
    global AGENT_REGISTRY

    os.system("clear" if os.name == "posix" else "cls")

    if _RICH:
        console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    else:
        print(BANNER)

    setup_readline()
    load_hooks()
    AGENT_REGISTRY = AgentRegistry()

    # Status sor
    features = []
    if _RICH:     features.append("Rich UI")
    if _PSUTIL:   features.append("psutil")
    if STREAM_OUTPUT: features.append("streaming")
    if HOOKS:     features.append(f"{len(HOOKS)} plugin")
    agents = AGENT_REGISTRY.list()
    if agents:    features.append(f"{len(agents)} agent")
    print_info("  ".join(features))

    active = get_active_topic()
    print_info(f"📁 Topic: {active}  |  'help' a parancsokhoz\n")

    chat_history = [{"role": "system", "content": build_system_prompt(active)}]
    for e in load_topic_history(active):
        if e.get("role") in ("user", "assistant"):
            chat_history.append(e)

    while True:
        try:
            topic      = get_active_topic()
            prompt_str = f"\033[1;32mFranz({topic}) >\033[0m "
            user_input = get_input(prompt_str)

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "kilépés"):
                print_ok("Viszlát!")
                break

            log_event("USER", user_input[:200])

            if handle_special_commands(user_input, chat_history):
                save_memory(topic, "user", user_input)
                continue

            # Agentic LLM loop
            save_memory(topic, "user", user_input)
            chat_history.append({"role": "user", "content": user_input})

            response = agent_loop(chat_history)

            if response:
                save_memory(topic, "assistant", response)
                log_event("FRANZ", response[:200])
                chat_history.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            print("\n[Ctrl+C – kilépéshez 'exit']")
        except EOFError:
            print_ok("Viszlát!")
            break
        except Exception as e:
            log_event("UNEXPECTED_ERROR", str(e))
            print_error(f"Váratlan hiba: {e}")


if __name__ == "__main__":
    main()
