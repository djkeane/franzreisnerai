#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ==============================================================
#   Franz – Multi‑Topic, Secure, Extensible AI Agent
#   Version: v3.0 (Security Hardened)
# ==============================================================

import os
import sys
import json
import datetime
import subprocess
import shlex
import pathlib
import shutil
import socket
import configparser
import importlib.util
import resource
import pwd
import urllib.request
import psutil
import requests
from typing import List, Dict

# --------------------------------------------------------------
# 0️⃣  ÁLLANDÓ KONFIGURÁCIÓ
# --------------------------------------------------------------
FRANZ_DIR   = os.path.expanduser("~/Franz")
MEMORY_DIR = os.path.join(FRANZ_DIR, "memory")
LOG_DIR    = os.path.join(FRANZ_DIR, "logs")
ACTIVE_TOPIC_FILE = os.path.join(MEMORY_DIR, ".active_topic")
SESSION_LOG = os.path.join(
    LOG_DIR,
    f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

# ---- Config file -------------------------------------------------
CFG_PATH = os.path.join(FRANZ_DIR, "franz.cfg")
config = configparser.ConfigParser()
config.read(CFG_PATH)

# Whitelist – melyik bináris futtatható a `run:`‑parancsnál
SAFE_COMMANDS = {
    c.strip()
    for c in config.get(
        "security",
        "whitelist",
        fallback=(
            "ls,cat,du,ps,top,netstat,ping,curl,wget,git,"
            "docker,kubectl,systemctl"
        ),
    ).split(",")
}

# Erőforrás‑limit (CPU s, CPU h, memória MiB)
CPU_SOFT = config.getint("security", "cpu_soft", fallback=5)
CPU_HARD = config.getint("security", "cpu_hard", fallback=10)
MEM_LIMIT = config.getint("security", "mem_limit_mb", fallback=200) * 1024 * 1024

# Webhook‑URL (pl. Slack) – csak kritikus eseményeknél
SECURITY_WEBHOOK = config.get("security", "alert_webhook", fallback="").strip()

# Ollama / Gemini
def _build_ollama_url(raw: str) -> str:
    u = raw.strip().rstrip("/")
    return u if u.endswith("/api/chat") else u + "/api/chat"

OLLAMA_URLS = [
    _build_ollama_url(u)
    for u in config.get("ollama", "url", fallback="http://localhost:11434").split(",")
    if u.strip()
]
OLLAMA_TIMEOUT = config.getint("ollama", "timeout", fallback=15)
DEFAULT_MODEL = config.get(
    "ollama", "default_model", fallback="jarvis-hu-coder:latest"
)
FALLBACK_MODELS = [
    m.strip()
    for m in config.get(
        "ollama", "fallback_models", fallback="jarvis-hu:latest,cronic:latest"
    ).split(",")
]
GENERIC_GEMINI_MODEL = config.get(
    "gemini", "model", fallback="gemini-1.5-flash"
)

# --------------------------------------------------------------
# 1️⃣  LOG / ALERT
# --------------------------------------------------------------
def log_event(event_type: str, message: str) -> None:
    ts = datetime.datetime.now().isoformat()
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(SESSION_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {event_type}: {message}\n")
    # kritikus esemény esetén küldj webhook‑et
    if event_type in {"DENIED", "EXCEPTION", "SECURITY", "PLUGIN_ERROR"}:
        alert_admin(event_type, message)


def alert_admin(event_type: str, message: str) -> None:
    if not SECURITY_WEBHOOK:
        return
    payload = json.dumps(
        {"text": f":warning: **Franz {event_type}** – {message}"}
    ).encode()
    try:
        req = urllib.request.Request(
            SECURITY_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass   # ne állítsa meg a szkriptet a webhook hiba


# --------------------------------------------------------------
# 2️⃣  HELPERS – PATH, RESOURCE, PRIVILEGE
# --------------------------------------------------------------
def safe_path(requested: str) -> str | None:
    """Biztonságos fájl/könyvtár‑elérés csak a FRANZ_DIR‑n belül."""
    target = os.path.abspath(os.path.join(FRANZ_DIR, requested))
    return target if target.startswith(FRANZ_DIR) else None


def limit_resources():
    """Alkalmazza a CPU‑ és memória‑limit‑eket a child‑processzekre."""
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SOFT, CPU_HARD))
    resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))


def drop_privileges():
    """Unix‑specifikus: a folyamat a ’nobody’ felhasználóra vált (ha root)."""
    if os.getuid() != 0:
        return
    try:
        pw = pwd.getpwnam("nobody")
        os.setgid(pw.pw_gid)
        os.setuid(pw.pw_uid)
    except Exception as e:
        log_event("PRIVILEGE_DROP", f"Failed: {e}")


# --------------------------------------------------------------
# 3️⃣  MEMORY / TOPIC kezelés
# --------------------------------------------------------------
def _topic_path(topic: str) -> str:
    safe = topic.replace("/", "_").replace(" ", "_")
    return os.path.join(MEMORY_DIR, f"{safe}.jsonl")


def set_active_topic(topic: str) -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(ACTIVE_TOPIC_FILE, "w", encoding="utf-8") as f:
        f.write(topic)


def get_active_topic() -> str:
    if os.path.isfile(ACTIVE_TOPIC_FILE):
        with open(ACTIVE_TOPIC_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "default"
    return "default"


def list_topics() -> List[str]:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    return sorted(
        {p.stem for p in pathlib.Path(MEMORY_DIR).glob("*.jsonl")}
    )


def load_topic_history(topic: str) -> List[Dict]:
    path = _topic_path(topic)
    history = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    history.append(json.loads(line.rstrip("\n")))
                except Exception:
                    continue
    return history


def save_memory(topic: str, role: str, content: str) -> None:
    """
    Egy bejegyzés a megadott topic‑memóriába.
    role: "user" | "assistant" | "system"
    """
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
        log_event("SAVE_MEMORY_ERROR", f"{topic}: {e}")


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
        log_event("REVERT_ERROR", f"{backup_file} not found")
        return False
    shutil.copy2(src, dst)
    log_event("REVERT", f"{topic} ← {backup_file}")
    return True


def search_memory(topic: str, query: str, role: str | None = None, limit: int = 5) -> List[Dict]:
    results = []
    for entry in load_topic_history(topic):
        if role and entry.get("role") != role:
            continue
        if query.lower() in entry.get("content", "").lower():
            results.append(entry)
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


# --------------------------------------------------------------
# 4️⃣  SAFE SHELL EXECUTION (`run:`)
# --------------------------------------------------------------
def exec_shell_safe(command: str) -> str:
    """
    Whitelist‑alapú, erőforrás‑korlátos, alacsony‑jogú shell‑parancs.
    """
    args = shlex.split(command)
    if not args:
        return "[ERROR] Üres parancs."

    prog = os.path.basename(args[0])
    if prog not in SAFE_COMMANDS:
        log_event("DENIED", f"run: {command} – not whitelisted")
        return f"[DENIED] '{prog}' nincs a whitelist‑en."

    prog_path = shutil.which(prog)
    if not prog_path:
        return f"[ERROR] Program nem található: {prog}"

    # környezet minimalizálása
    env = {"PATH": "/usr/bin:/bin"}

    try:
        result = subprocess.run(
            [prog_path, *args[1:]],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=12,
            preexec_fn=lambda: (limit_resources(), drop_privileges()),
            env=env,
        )
        out = result.stdout.strip()
        return out if out else "(nincs kimenet)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Parancs túl hosszú."
    except Exception as e:
        log_event("EXCEPTION", f"run: {command} – {e}")
        return f"[EXCEPTION] {e}"


# --------------------------------------------------------------
# 5️⃣  PLUGIN / HOOK RENDSZER
# --------------------------------------------------------------
HOOKS: Dict[str, object] = {}

def load_hooks() -> None:
    """Betölti a plugins/ könyvtárban lévő Python-modulokat."""
    plugins_dir = os.path.join(FRANZ_DIR, "plugins")
    if not os.path.isdir(plugins_dir):
        return
    for f in sorted(pathlib.Path(plugins_dir).glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "hook"):
                HOOKS[f.stem] = mod.hook
                log_event("PLUGIN_LOADED", f.stem)
        except Exception as e:
            log_event("PLUGIN_ERROR", f"{f.stem}: {e}")


# --------------------------------------------------------------
# 6️⃣  AGENT‑MANAGER
# --------------------------------------------------------------
# Agent‑registry – betölti az agents/ modulokat (DeveloperAgent, DebugAgent, stb.)
class AgentRegistry:
    def __init__(self):
        self._agents = {}
        # sys.path-ba kell a Franz könyvtár, hogy az agents csomag importálható legyen
        if FRANZ_DIR not in sys.path:
            sys.path.insert(0, FRANZ_DIR)
        sections = [
            s for s in config.sections() if s.lower().endswith("agent")
        ]
        for sec in sections:
            # "DeveloperAgent" → "developer_agent"
            mod_name = sec[0].lower() + sec[1:].replace("Agent", "_agent")
            try:
                spec = importlib.util.find_spec(f"agents.{mod_name}")
                if spec is None:
                    log_event("AGENT_SKIP", f"{sec} – modul 'agents.{mod_name}' nem található")
                    continue
                mod = importlib.import_module(f"agents.{mod_name}")
                klass = getattr(mod, sec)
                self._agents[sec] = klass(sec)
                log_event("AGENT_LOADED", sec)
            except Exception as e:
                log_event("AGENT_ERROR", f"{sec}: {e}")

    def get(self, name: str):
        return self._agents.get(name)

    def list(self):
        return [(a.name, a.display_name, a.description) for a in self._agents.values()]


AGENT_REGISTRY = AgentRegistry()

# --------------------------------------------------------------
# 6️⃣  TOOL‑HANDLER (ls, cat, du, ps, top, net, svc, docker, kubectl, run)
# --------------------------------------------------------------
def handle_tools(user_input: str) -> bool:
    # -------- ls --------
    if user_input.startswith("ls:"):
        path = user_input[3:].strip() or "."
        real = safe_path(path)
        if not real:
            print("⚠️ Hozzáférés megtagadva – csak a Franz könyvtárban listázhatsz.")
            return True
        try:
            items = sorted(os.listdir(real))
            for i in items:
                full = os.path.join(real, i)
                if os.path.isdir(full):
                    print(f"\033[94m{i}/\033[0m")
                else:
                    print(i)
        except Exception as e:
            print(f"❌ ls hiba: {e}")
        return True

    # -------- cat --------
    if user_input.startswith("cat:"):
        raw = user_input[4:].strip()
        real = safe_path(raw)
        if not real or not os.path.isfile(real):
            print("⚠️ A megadott fájl nem létezik vagy kívül van a Franz területén.")
            return True
        try:
            txt = pathlib.Path(real).read_text(encoding="utf-8")
            lines = txt.splitlines()
            if len(lines) > 200:
                txt = "\n".join(lines[:10] + ["…"] + lines[-10:])
            print(txt)
        except Exception as e:
            print(f"❌ cat hiba: {e}")
        return True

    # -------- du --------
    if user_input.startswith("du:"):
        target = user_input[3:].strip() or "."
        real = safe_path(target)
        if not real:
            print("⚠️ Hozzáférés megtagadva.")
            return True
        total = 0
        for root, _, files in os.walk(real):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
        size = total
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                break
            size /= 1024
        print(f"{size:.2f} {unit}")
        return True

    # -------- ps --------
    if user_input.startswith("ps:"):
        arg = user_input[3:].strip().lower()
        procs = [
            p
            for p in psutil.process_iter(["pid", "name", "username"])
        ]
        if arg:
            procs = [
                p for p in procs if arg in (p.info["name"] or "").lower()
            ]
        for p in procs[:30]:
            print(
                f"{p.info['pid']:>6} {p.info['username']:<12} {p.info['name']}"
            )
        return True

    # -------- top --------
    if user_input.startswith("top"):
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        print(
            f"CPU: {cpu}% | RAM: {mem.percent}% ({mem.used/1e9:.2f}/{mem.total/1e9:.2f} GB)"
        )
        return True

    # -------- net --------
    if user_input.startswith("net:"):
        target = user_input[4:].strip()
        if not target:
            for iface, addrs in psutil.net_if_addrs().items():
                for a in addrs:
                    print(f"{iface}: {a.address}")
        else:
            try:
                host, port = target.split(":")
                s = socket.create_connection((host, int(port)), timeout=2)
                s.close()
                print("✅ Port nyitva")
            except Exception:
                print("❌ Port ZÁRVA vagy nem elérhető")
        return True

    # -------- svc (systemd) --------
    if user_input.startswith("svc:"):
        parts = user_input[4:].strip().split()
        if len(parts) >= 2:
            action, service = parts[0], parts[1]
            print(exec_shell_safe(f"systemctl {action} {service}"))
        else:
            print("Használat: svc: <action> <service>")
        return True

    # -------- docker --------
    if user_input.startswith("docker:"):
        cmd = "docker " + user_input[7:].strip()
        print(exec_shell_safe(cmd))
        return True

    # -------- kubectl --------
    if user_input.startswith("kubectl:"):
        cmd = "kubectl " + user_input[8:].strip()
        print(exec_shell_safe(cmd))
        return True

    # -------- run (generic) --------
    if user_input.startswith("run:"):
        cmd = user_input[4:].strip()
        print(exec_shell_safe(cmd))
        return True

    # -------- hook --------
    if user_input.startswith("hook:"):
        parts = user_input[5:].strip().split(None, 1)
        name = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        if name in HOOKS:
            try:
                result = HOOKS[name](name, args)
                print(result or "(nincs kimenet)")
            except Exception as e:
                log_event("PLUGIN_ERROR", f"{name}: {e}")
                print(f"❌ Plugin hiba: {e}")
        else:
            available = ", ".join(HOOKS) if HOOKS else "nincs betöltve"
            print(f"⚠️ Ismeretlen hook: '{name}'. Elérhető: {available}")
        return True

    # -------- hooks (lista) --------
    if user_input.strip() == "hooks":
        if HOOKS:
            print("\033[1;35mBetöltött plugin hook-ok:\033[0m")
            for h in sorted(HOOKS):
                print(f" • {h}")
        else:
            print("Nincs betöltött plugin.")
        return True

    # -------- diagnosztizál --------
    if user_input.strip() == "diagnosztizál":
        print("\n=== Franz – Diagnosztika ===")
        # 1. könyvtár‑engedélyek
        mode = oct(os.stat(FRANZ_DIR).st_mode)[-3:]
        print(f"📂 Franz könyvtár jogai: {mode}")
        # 2. konfiguráció
        print("⚙️  Konfiguráció (franz.cfg):")
        for sec in config.sections():
            print(f"   [{sec}]")
            for k, v in config[sec].items():
                print(f"     {k} = {v}")
        # 3. memória és log fájlok mérete
        mem_sz = sum(
            os.path.getsize(p)
            for p in pathlib.Path(MEMORY_DIR).glob("*.jsonl")
        )
        log_sz = sum(
            os.path.getsize(p)
            for p in pathlib.Path(LOG_DIR).glob("*.log")
        )
        print(f"💾 Memory fájlok: {mem_sz/1024:.1f} KB")
        print(f"🗒️  Log fájlok: {log_sz/1024:.1f} KB")
        # 4. Ollama elérhetőség
        for url in OLLAMA_URLS:
            tags_url = url.replace("/api/chat", "/api/tags")
            try:
                r = requests.get(tags_url, timeout=5)
                if r.status_code == 200:
                    print(f"🤖 Ollama elérhető: {url}")
                    break
            except Exception:
                print(f"🚫 Ollama nem elérhető: {url}")
        else:
            print("🚫 Egyik Ollama endpoint sem válaszol.")
        # 5. Gemini kulcs ellenőrzés
        has_key = bool(os.getenv("GEMINI_API_KEY"))
        print(f"🔑 Gemini API‑kulcs: {'van' if has_key else 'hiányzik'}")
        return True

    return False


# --------------------------------------------------------------
# 7️⃣  LLM‑KÉRÉS (Ollama → fallback → Gemini) & truncate
# --------------------------------------------------------------
def truncate_history(messages: List[Dict]) -> List[Dict]:
    """Legújabb ~20 üzenet (plus system) – megakadályozza a token‑túllépést."""
    if not messages:
        return messages
    system = messages[0]
    body = messages[1:]
    body = body[-20:]  # legfrissebb 20
    return [system] + body


def get_answer(messages: List[Dict]) -> str:
    # 1. Elsődleges modell
    answer = None
    try:
        answer = _ollama_chat(DEFAULT_MODEL, messages)
    except Exception:
        answer = None

    if answer:
        return answer

    # 2. fallback‑modellek
    for m in FALLBACK_MODELS:
        try:
            answer = _ollama_chat(m, messages)
            if answer:
                log_event("FALLBACK_OK", f"Model: {m}")
                return answer
        except Exception:
            continue

    # 3. Gemini
    log_event("FALLBACK", "Gemini-re váltás")
    user_prompt = messages[-1]["content"]
    return _gemini_chat(user_prompt)


def _ollama_chat(model: str, msgs: List[Dict]) -> str | None:
    payload = {
        "model": model,
        "messages": truncate_history(msgs),
        "stream": False,
        "options": {"temperature": 0.2},
    }
    for url in OLLAMA_URLS:
        try:
            r = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
            r.raise_for_status()
            return (
                r.json()
                .get("message", {})
                .get("content", "[NO RESPONSE]")
            )
        except Exception as e:
            log_event("OLLAMA_ERROR", f"{model}@{url}: {e}")
    return None


def _gemini_chat(prompt: str) -> str:
    try:
        from google import genai

        client = genai.Client()
        resp = client.models.generate_content(
            model=GENERIC_GEMINI_MODEL, contents=prompt
        )
        return resp.text
    except Exception as e:
        log_event("GEMINI_ERROR", str(e))
        return "⛔ Gemini hiba – nézd a logot."


# --------------------------------------------------------------
# 8️⃣  TOPIC‑PARANCs (topic:, topics, reset:, snapshot:, revert:, search:)
# --------------------------------------------------------------
def handle_topic_commands(user_input: str, chat_history: List[Dict]) -> bool:
    # ---------- topics (list) ----------
    if user_input.strip() == "topics":
        print("\033[1;35mElérhető témák:\033[0m")
        for t in list_topics():
            mark = " (aktív)" if t == get_active_topic() else ""
            print(f" • {t}{mark}")
        return True

    # ---------- topic: <name> ----------
    if user_input.startswith("topic:"):
        name = user_input.split(":", 1)[1].strip() or "default"
        set_active_topic(name)
        chat_history.clear()
        # rendszer‑prompt a topic‑információval
        chat_history.append(
            {
                "role": "system",
                "content": f"Te Franz vagy, egy profi admin. Aktuális téma: {name}",
            }
        )
        # előzmények betöltése (ha léteznek)
        for e in load_topic_history(name):
            chat_history.append(e)
        print(f"\033[1;32m→ Topic váltva: {name}\033[0m")
        return True

    # ---------- reset ----------
    if user_input.startswith("reset:"):
        cur = get_active_topic()
        p = _topic_path(cur)
        try:
            os.remove(p)
            print(f"\033[1;31m• {cur} törölve\033[0m")
        except FileNotFoundError:
            print("Nincs mit törölni.")
        chat_history.clear()
        chat_history.append(
            {
                "role": "system",
                "content": f"Franz – újraindult a {cur} topic üres memóriával.",
            }
        )
        return True

    # ---------- snapshot ----------
    if user_input.strip() == "snapshot":
        cur = get_active_topic()
        bak = make_snapshot(cur)
        if bak:
            print(f"\033[1;32m✓ Snapshot kész: {os.path.basename(bak)}\033[0m")
        else:
            print("❌ Nincs mit menteni (üres topic).")
        return True

    # ---------- revert ----------
    if user_input.startswith("revert:"):
        cur = get_active_topic()
        bak = user_input.split(":", 1)[1].strip()
        if revert_snapshot(cur, bak):
            chat_history.clear()
            chat_history.append(
                {
                    "role": "system",
                    "content": f"Franz – visszaállítva a {bak} snapshotból.",
                }
            )
            for e in load_topic_history(cur):
                chat_history.append(e)
            print("\033[1;32m✓ Visszaállítás sikeres.\033[0m")
        else:
            print("❌ Visszaállítás sikertelen.")
        return True

    # ---------- search ----------
    if user_input.startswith("search:"):
        query = user_input.split(":", 1)[1].strip()
        role = None
        # Ha a keresés után szó van (pl. "search: timeout assistant")
        if " " in query:
            q, possible_role = query.rsplit(" ", 1)
            if possible_role in {"user", "assistant", "system"}:
                query, role = q, possible_role
        hits = search_memory(get_active_topic(), query, role=role)
        if not hits:
            print("\033[1;33m🔍 Nincs találat.\033[0m")
        else:
            print("\033[1;35m🔍 Találatok (újabb → régebbi):\033[0m")
            for h in hits:
                ts = h["timestamp"][:19].replace("T", " ")
                tag = {"user": "🧑", "assistant": "🤖", "system": "⚙️"}.get(
                    h["role"], "?"
                )
                preview = h["content"].replace("\n", " ")[:80]
                print(f"{tag} [{ts}] {preview}")
        return True

    return False


# --------------------------------------------------------------
# 9️⃣  AGENT‑PARANCs (dev:, debug:)
# --------------------------------------------------------------
def handle_agent_commands(user_input: str, chat_history: List[Dict]) -> bool:
    # ---------- dev ----------
    if user_input.startswith("dev:"):
        task = user_input.split(":", 1)[1].strip()
        agent = AGENT_REGISTRY.get("DeveloperAgent")
        if not agent:
            print("❌ Developer Agent nincs regisztrálva.")
            return True

        # új topic (dev_<first‑word‑of‑task>)
        base = task.split()[0] if task else "session"
        topic = f"{agent.topic_prefix}{base}"
        set_active_topic(topic)

        chat_history.clear()
        chat_history.append(
            {"role": "system", "content": agent.system_prompt(task)}
        )
        # korábbi bejegyzések (ha vannak)
        for e in load_topic_history(topic):
            chat_history.append(e)

        print(f"\033[1;34m🛠️  Developer Agent elindítva (topic: {topic})\033[0m")
        return True

    # ---------- debug ----------
    if user_input.startswith("debug:"):
        task = user_input.split(":", 1)[1].strip()
        agent = AGENT_REGISTRY.get("DebugAgent")
        if not agent:
            print("❌ Debug Agent nincs regisztrálva.")
            return True

        base = task.split()[0] if task else "session"
        topic = f"{agent.topic_prefix}{base}"
        set_active_topic(topic)

        chat_history.clear()
        chat_history.append(
            {"role": "system", "content": agent.system_prompt(task)}
        )
        for e in load_topic_history(topic):
            chat_history.append(e)

        print(f"\033[1;35m🐞 Debug Agent elindítva (topic: {topic})\033[0m")
        return True

    return False


# --------------------------------------------------------------
# 10️⃣  BANNER & ÜDVÖZLŐ SZÖVEG
# --------------------------------------------------------------
BANNER = r"""
 ███████╗██████╗  █████╗ ███╗   ██╗███████╗
 ██╔════╝██╔══██╗██╔══██╗████╗  ██║╚══███╔╝
 █████╗  ██████╔╝███████║██╔██╗ ██║  ███╔╝ 
 ██╔══╝  ██╔══██╗██╔══██║██║╚██╗██║ ███╔╝  
 ██║     ██║  ██║██║  ██║██║ ╚████║███████╗
 ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝
        >> SMART AGENT v3.0 (Security Hardened) <<
"""

# --------------------------------------------------------------
# 11️⃣  MAIN LOOP
# --------------------------------------------------------------
def main() -> None:
    os.system("clear" if os.name == "posix" else "cls")
    print("\033[1;36m" + BANNER + "\033[0m")

    load_hooks()
    if HOOKS:
        print(f"🔌 Pluginek: {', '.join(HOOKS)}")

    # Aktív topic betöltése, vagy default
    active = get_active_topic()
    print(f"📁 Aktív topic: {active}")

    # Üdvözlő system‑prompt (témaspecifikus)
    chat_history = [
        {
            "role": "system",
            "content": f"Te Franz vagy, egy profi szerver‑adminisztrátor. Aktuális téma: {active}",
        }
    ]
    # előzmények betöltése
    for e in load_topic_history(active):
        chat_history.append(e)

    print("Írd be: 'exit' vagy 'quit' a kilépéshez.\n")

    while True:
        try:
            user_input = input("\033[1;32mFranz > \033[0m").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Viszlát!")
                break

            # 1️⃣  Agent parancsok (dev:, debug:)
            if handle_agent_commands(user_input, chat_history):
                save_memory(get_active_topic(), "user", user_input)
                log_event("USER", user_input)
                continue

            # 2️⃣  Topic parancsok
            if handle_topic_commands(user_input, chat_history):
                save_memory(get_active_topic(), "user", user_input)
                log_event("USER", user_input)
                continue

            # 3️⃣  Tool‑parancsok (ls:, cat:, run:, stb.)
            if handle_tools(user_input):
                save_memory(get_active_topic(), "user", user_input)
                log_event("USER", user_input)
                continue

            # 4️⃣  Normál LLM kérdés
            save_memory(get_active_topic(), "user", user_input)
            log_event("USER", user_input)
            chat_history.append({"role": "user", "content": user_input})

            print("\033[1;33mGondolkodik…\033[0m", end="\r")
            response = get_answer(chat_history)
            print(" " * 30, end="\r")
            print(f"\033[1;34mFranz:\033[0m {response}\n")

            save_memory(get_active_topic(), "assistant", response)
            log_event("FRANZ", response)
            chat_history.append(
                {"role": "assistant", "content": response}
            )

        except KeyboardInterrupt:
            print("\nKilépés…")
            break
        except Exception as e:
            log_event("UNEXPECTED_ERROR", str(e))
            print(f"⚠️ Hiba: {e}")


if __name__ == "__main__":
    main()
