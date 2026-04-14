"""Tool commands: safe shell execution and helper functions for built-in commands."""

from __future__ import annotations

import html
import os
import pathlib
import re
import shlex
import shutil
import socket
import subprocess
import urllib.request
from typing import Optional

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from src.security import (
    FRANZ_DIR,
    SAFE_COMMANDS,
    drop_privileges,
    limit_resources,
    log_event,
    safe_path,
)

# Patterns that are always blocked regardless of whitelist
_DANGER_RE = re.compile(
    r"\brm\s+-[a-z]*r[a-z]*f\s+/"
    r"|\bdd\s+if="
    r"|\bmkfs\b"
    r"|\bfdisk\b"
    r"|:\(\)\s*\{\s*:\|:&\s*\}"
    r"|\bchmod\s+-R\s+777\s+/"
    r"|\bcurl\b.*\|\s*(?:ba)?sh"
    r"|\bwget\b.*\|\s*(?:ba)?sh",
    re.IGNORECASE,
)


def _is_dangerous(cmd: str) -> bool:
    return bool(_DANGER_RE.search(cmd))


# ── Whitelisted shell execution ────────────────────────────────
def exec_shell_safe(command: str) -> str:
    """
    Run *command* only if its first token is in SAFE_COMMANDS.
    Applies resource limits and privilege drop in the child process.
    """
    args = shlex.split(command)
    if not args:
        return "[ERROR] Empty command."

    prog = os.path.basename(args[0])
    if prog not in SAFE_COMMANDS:
        log_event("DENIED", f"run: {command!r}")
        return f"[DENIED] '{prog}' is not in the whitelist."

    if _is_dangerous(command):
        log_event("DENIED", f"dangerous: {command!r}")
        return "[DENIED] Dangerous command pattern detected."

    prog_path = shutil.which(prog)
    if not prog_path:
        return f"[ERROR] Executable not found: {prog}"

    try:
        result = subprocess.run(
            [prog_path, *args[1:]],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=12,
            preexec_fn=lambda: (limit_resources(), drop_privileges()),
            env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
        out = result.stdout.strip()
        return out[:8000] if out else "(empty output)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Command took too long."
    except Exception as exc:
        log_event("EXCEPTION", f"exec_shell_safe: {exc}")
        return f"[EXCEPTION] {exc}"


# ── Agentic tool executor (LLM-driven) ────────────────────────
def exec_tool(name: str, args: dict) -> str:
    """Execute an agentic tool call. Used by the agent loop in cli.py."""
    try:
        if name == "bash":
            cmd = args.get("command", "").strip()
            if not cmd:
                return "[ERROR] Empty command."
            if _is_dangerous(cmd):
                log_event("TOOL_DANGER", cmd)
                return (
                    "[WARNING] Potentially dangerous command blocked:\n"
                    f"  {cmd}\n"
                    "Run manually in your terminal if you are sure."
                )
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ},
            )
            out = (result.stdout + result.stderr).strip()
            return out[:8000] if out else "(no output)"

        elif name == "read_file":
            path = pathlib.Path(os.path.expanduser(args.get("path", ""))).resolve()
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            if len(lines) > 500:
                text = "\n".join(lines[:500]) + f"\n… [{len(lines) - 500} lines truncated]"
            return text

        elif name == "write_file":
            path = pathlib.Path(os.path.expanduser(args.get("path", ""))).resolve()
            content = args.get("content", "")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Írva: {path} ({len(content)} karakter)"

        elif name == "list_dir":
            path = pathlib.Path(os.path.expanduser(args.get("path", "."))).resolve()
            items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = []
            for item in items:
                if item.is_dir():
                    lines.append(f"[K] {item.name}/")
                else:
                    lines.append(f"[F] {item.name}  ({item.stat().st_size:,} B)")
            return "\n".join(lines) or "(üres könyvtár)"

        elif name == "git":
            git_args = args.get("args", "")
            result = subprocess.run(
                f"git {git_args}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return (result.stdout + result.stderr).strip()[:4000]

        elif name == "web_fetch":
            url = args.get("url", "")
            req = urllib.request.Request(url, headers={"User-Agent": "Franz/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read(100_000).decode("utf-8", errors="replace")
            raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL)
            raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL)
            raw = re.sub(r"<[^>]+>", "", raw)
            raw = html.unescape(raw)
            raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
            return raw[:6000]

        else:
            return f"[ERROR] Ismeretlen tool: {name}"

    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Tool túl sokáig futott (>30 s)."
    except Exception as exc:
        log_event("TOOL_ERROR", f"{name}: {exc}")
        return f"[ERROR] {name}: {exc}"


# ── Built-in command helpers ───────────────────────────────────
def list_directory(path: str) -> str:
    """ls: – list contents restricted to FRANZ_DIR."""
    real = safe_path(path or ".")
    if not real:
        return "Hozzáférés megtagadva – csak a Franz könyvtáron belüli útvonalak engedélyezettek."
    try:
        items = sorted(os.listdir(real))
        lines = []
        for item in items:
            full = os.path.join(real, item)
            lines.append(f"\033[94m{item}/\033[0m" if os.path.isdir(full) else item)
        return "\n".join(lines) or "(üres)"
    except Exception as exc:
        return f"ls hiba: {exc}"


def cat_file(path: str) -> str:
    """cat: – read a file restricted to FRANZ_DIR (max 200 lines preview)."""
    real = safe_path(path)
    if not real or not os.path.isfile(real):
        return "Fájl nem található vagy a Franz könyvtáron kívül."
    try:
        text = pathlib.Path(real).read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) > 200:
            text = "\n".join(lines[:10] + ["…"] + lines[-10:])
        return text
    except Exception as exc:
        return f"cat hiba: {exc}"


def disk_usage(path: str) -> str:
    """du: – calculate total size of a path inside FRANZ_DIR."""
    real = safe_path(path or ".")
    if not real:
        return "Hozzáférés megtagadva."
    total = 0
    for root, _, files in os.walk(real):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    size: float = float(total)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def process_list(filter_str: str = "") -> str:
    """ps: – list processes, optionally filtered by name."""
    if not _HAS_PSUTIL:
        return "[ERROR] psutil nincs telepítve."
    procs = list(psutil.process_iter(["pid", "name", "username"]))
    if filter_str:
        procs = [p for p in procs if filter_str.lower() in (p.info["name"] or "").lower()]
    lines = [
        f"{p.info['pid']:>6}  {(p.info['username'] or ''):<12}  {p.info['name']}"
        for p in procs[:40]
    ]
    return "\n".join(lines) or "(nincs találat)"


def system_status(service_action: str, service_name: str) -> str:
    """svc: – run 'systemctl <action> <service>'."""
    return exec_shell_safe(f"systemctl {service_action} {service_name}")


def docker_cmd(args: str) -> str:
    """docker: – run 'docker <args>'."""
    return exec_shell_safe(f"docker {args}")


def kubectl_cmd(args: str) -> str:
    """kubectl: – run 'kubectl <args>'."""
    return exec_shell_safe(f"kubectl {args}")


def network_info(target: str = "") -> str:
    """net: – show interfaces or check host:port connectivity."""
    if not target:
        if not _HAS_PSUTIL:
            return "[ERROR] psutil nincs telepítve."
        lines = []
        for iface, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                lines.append(f"{iface}: {a.address}")
        return "\n".join(lines)
    try:
        host, port_str = target.split(":")
        s = socket.create_connection((host, int(port_str)), timeout=2)
        s.close()
        return "Port nyitva"
    except Exception:
        return "Port zárva vagy nem elérhető"


def listening_ports() -> str:
    """
    List all listening ports with associated processes.
    Falls back to lsof if psutil fails (permission issues).
    """
    if not _HAS_PSUTIL:
        return "[ERROR] psutil nincs telepítve."

    try:
        # First try psutil
        try:
            connections = psutil.net_connections(kind="inet")
            listening = [c for c in connections if c.status == "LISTEN" and c.laddr]
        except (psutil.AccessDenied, psutil.Error):
            # Fallback to lsof command with LISTEN filter
            result = subprocess.run(
                ["lsof", "-i", "-P", "-n", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                lines = ["Port  │ Process  │ PID"]
                lines.append("──────────────────────")
                seen = set()
                for line in result.stdout.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 9:
                        cmd = parts[0]
                        pid = parts[1]
                        # Extract port from NAME column (parts[8])
                        name_port = parts[8]
                        # Extract just the port number if in format *:PORT or 127.0.0.1:PORT
                        port_match = re.search(r'[:\[](\d+)\]?$', name_port)
                        if port_match:
                            port_num = port_match.group(1)
                            key = f"{port_num}:{cmd}"
                            if key not in seen:
                                seen.add(key)
                                lines.append(f"{port_num:6} │ {cmd:8} │ {pid}")
                return "\n".join(lines) if len(lines) > 1 else "(Nincs hallgatózó port)"
            raise psutil.AccessDenied("Cannot read network connections (need elevated privileges)")

        if not listening:
            return "(Nincs hallgatózó port)"

        lines = ["Port  │ PID  │ Felhasználó   │ Folyamat"]
        lines.append("─────────────────────────────────────────")

        for conn in sorted(listening, key=lambda x: x.laddr.port if x.laddr else 0):
            port = conn.laddr.port
            pid = conn.pid
            if not pid or not port:
                continue

            try:
                proc = psutil.Process(pid)
                name = proc.name()
                user = proc.username()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                name = "?"
                user = "?"

            lines.append(f"{port:5} │ {pid:4} │ {user:<13} │ {name}")

        return "\n".join(lines) if len(lines) > 1 else "(Nincs hallgatózó port)"
    except Exception as exc:
        log_event("LISTENING_PORTS_ERROR", str(exc))
        return f"[INFO] Hallgatózó portok megtekintéséhez:\n  sudo python3 -c \"from src.tools import listening_ports; print(listening_ports())\""


def running_services() -> str:
    """
    List known server/daemon processes currently running.
    Searches for: web servers, databases, caches, message queues, Ollama, etc.
    """
    if not _HAS_PSUTIL:
        return "[ERROR] psutil nincs telepítve."

    known_services = {
        # Web servers
        "nginx", "apache2", "apache", "httpd", "gunicorn", "uwsgi",
        "node", "python3", "python", "ruby", "java",
        # Databases
        "postgres", "postgresql", "mysql", "mariadb", "mongodb", "sqlite3",
        # Caches
        "redis-server", "redis", "memcached", "memcacheCp",
        # Message queues
        "rabbitmq", "kafka", "activemq",
        # LLM / AI
        "ollama", "vllm", "triton",
        # System
        "sshd", "docker", "containerd", "systemd", "systemd-resolved",
    }

    try:
        running = []
        for proc in psutil.process_iter(["pid", "name", "username"]):
            try:
                name = proc.info.get("name", "").lower()
                if any(service in name for service in known_services):
                    running.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if not running:
            return "(Nincs ismert szolgáltatás futva)"

        lines = ["PID  │ Felhasználó   │ Folyamat"]
        lines.append("─────────────────────────────────────")

        for proc in sorted(running, key=lambda p: p.info.get("pid", 0)):
            pid = proc.info.get("pid", "?")
            user = proc.info.get("username", "?")
            pname = proc.info.get("name", "?")
            lines.append(f"{pid:<4} │ {user:<13} │ {pname}")

        return "\n".join(lines)
    except Exception as exc:
        log_event("RUNNING_SERVICES_ERROR", str(exc))
        return f"[ERROR] running_services: {exc}"
