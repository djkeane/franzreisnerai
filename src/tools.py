"""Tool commands: safe shell execution and helper functions for built-in commands."""

from __future__ import annotations

import glob
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

# ── Agentic Tool Registry (Phase B) ────────────────────────────
AGENT_TOOLS: dict[str, str] = {
    "bash":        "Shell parancs futtatása. Args: {command: str, cwd: str?}",
    "read_file":   "Fájl olvasása. Args: {path: str}",
    "write_file":  "Fájl írása. Args: {path: str, content: str}",
    "find_files":  "Glob minta szerinti fájlkeresés. Args: {pattern: str, path: str?}",
    "grep_content":"Regex keresés fájlokban. Args: {pattern: str, path: str?, extensions: list?}",
    "edit_file":   "String csere fájlban. Args: {path: str, old_string: str, new_string: str}",
    "list_dir":    "Könyvtár listázása. Args: {path: str?}",
    "git":         "Git parancs futtatása. Args: {args: str}",
    "web_fetch":   "URL letöltése. Args: {url: str}",
    "remote_exec": "SSH parancs futtatása. Args: {host: str, cmd: str, user: str?, key_path: str?}",
    "task_done":   "Feladat befejezésének jelzése. Args: {summary: str}",
}

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


# ── Agentic Tool Helpers (Phase B.2 + B.3) ────────────────────────
def _edit_file_string_replace(path: str, old_string: str, new_string: str) -> str:
    """String csere egy fájlban (az első előfordulást)."""
    try:
        real = safe_path(path) or path
        content = pathlib.Path(real).read_text(encoding="utf-8")
        count = content.count(old_string)

        if count == 0:
            return "[ERROR] old_string nem található a fájlban."

        warn = ""
        if count > 1:
            warn = f"[WARNING] {count}-szer szerepel, első előfordulás cserélve.\n"

        new_content = content.replace(old_string, new_string, 1)
        pathlib.Path(real).write_text(new_content, encoding="utf-8")
        log_event("EDIT_FILE", f"{path}: {len(old_string)} → {len(new_string)} kar")
        return f"{warn}OK: {path} szerkesztve."
    except Exception as exc:
        log_event("EDIT_FILE_ERROR", str(exc))
        return f"[ERROR] _edit_file_string_replace: {exc}"


def _remote_exec(host: str, cmd: str, user: str = None, key_path: str = None) -> str:
    """SSH parancs futtatása whitelist-alapú biztonsággal."""
    try:
        # Whitelist: FRANZ_DIR/ssh_hosts.txt
        hosts_file = pathlib.Path(FRANZ_DIR) / "ssh_hosts.txt"
        if not hosts_file.exists():
            return "[DENIED] ssh_hosts.txt nem létezik — whitelist szükséges."

        allowed_hosts = hosts_file.read_text().splitlines()
        if host not in allowed_hosts:
            return f"[DENIED] {host!r} nincs a whitelist-en."

        if _is_dangerous(cmd):
            return "[DENIED] Veszélyes parancs minta."

        ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                   "-o", "ConnectTimeout=10"]
        if key_path:
            ssh_cmd += ["-i", key_path]

        target = f"{user}@{host}" if user else host
        ssh_cmd += [target, cmd]

        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (result.stdout + result.stderr).strip()
        log_event("REMOTE_EXEC", f"{target}: {cmd[:50]}…")
        return out[:4000] if out else "(empty output)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] SSH parancs túl sokáig futott (>30 s)."
    except Exception as exc:
        log_event("REMOTE_EXEC_ERROR", str(exc))
        return f"[ERROR] _remote_exec: {exc}"


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

        # ── Phase B.4: Agentic Tool Expansion ──────────────────────
        elif name == "find_files":
            pattern = args.get("pattern", "*")
            path = args.get("path", ".")
            return search_files(pattern, path)

        elif name == "grep_content":
            pattern = args.get("pattern", "")
            path = args.get("path", ".")
            exts = args.get("extensions")
            if isinstance(exts, str):
                exts = [e.strip() for e in exts.split(",")]
            return grep_in_files(pattern, path, exts)

        elif name == "edit_file":
            path = args.get("path", "")
            old_string = args.get("old_string", "")
            new_string = args.get("new_string", "")
            return _edit_file_string_replace(path, old_string, new_string)

        elif name == "remote_exec":
            host = args.get("host", "")
            cmd = args.get("cmd", "")
            user = args.get("user")
            key_path = args.get("key_path")
            return _remote_exec(host, cmd, user, key_path)

        elif name == "task_done":
            summary = args.get("summary", "Feladat befejezve.")
            log_event("TASK_DONE", summary[:120])
            return f"__TASK_DONE__:{summary}"

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


# ── Fájlrendszer műveletek (Phase A) ────────────────────────────
def search_files(pattern: str, path: str = ".", max_results: int = 50) -> str:
    """
    Search for files by name using glob patterns.
    Examples: "*.py", "src/**/*.ts", "**/*test*"
    """
    try:
        real_path = safe_path(path) or path
        matches = glob.glob(
            pattern,
            root_dir=real_path,
            recursive=True,
        )

        if not matches:
            return "(Nincs találat)"

        lines = ["Fájl  │ Méret"]
        lines.append("──────────────────────")

        for i, match in enumerate(sorted(matches)[:max_results]):
            full_path = os.path.join(real_path, match)
            try:
                size = os.path.getsize(full_path)
                size_str = f"{size:,}" if size < 1_000_000 else f"{size/1_000_000:.1f}M"
            except Exception:
                size_str = "?"
            lines.append(f"{match:40} │ {size_str:>10}")

        if len(matches) > max_results:
            lines.append(f"\n… és még {len(matches) - max_results} fájl")

        return "\n".join(lines)
    except Exception as exc:
        log_event("SEARCH_FILES_ERROR", str(exc))
        return f"[ERROR] search_files: {exc}"


def grep_in_files(
    pattern: str, path: str = ".", extensions: list[str] = None, max_results: int = 20
) -> str:
    """
    Search for text content in files using regex.
    Extensions: [".py", ".ts"] or None for all files.
    Returns: file:line:content format
    """
    try:
        real_path = safe_path(path) or path
        regex = re.compile(pattern, re.IGNORECASE)

        matches = []
        for root, _, files in os.walk(real_path):
            for fname in files:
                if extensions and not any(fname.endswith(ext) for ext in extensions):
                    continue

                full_path = os.path.join(root, fname)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = os.path.relpath(full_path, real_path)
                                content = line.strip()[:80]
                                matches.append(f"{rel_path}:{line_num}: {content}")
                                if len(matches) >= max_results:
                                    break
                    if len(matches) >= max_results:
                        break
                except Exception:
                    pass

        if not matches:
            return "(Nincs találat)"

        lines = ["Fájl:sor: Tartalom"]
        lines.append("─" * 70)
        lines.extend(matches[:max_results])

        if len(matches) > max_results:
            lines.append(f"\n… és még {len(matches) - max_results} találat")

        return "\n".join(lines)
    except Exception as exc:
        log_event("GREP_ERROR", str(exc))
        return f"[ERROR] grep_in_files: {exc}"


def edit_file_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    Edit specific lines in a file (1-based indexing).
    Replaces lines [start_line, end_line] with new_content.
    """
    try:
        real_path = safe_path(path)
        if not real_path or not os.path.isfile(real_path):
            return f"[ERROR] Fájl nem elérhető: {path}"

        with open(real_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Validate line numbers (1-based)
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return f"[ERROR] Érvénytelen sor-tartomány (van {len(lines)} sor)"

        # Replace lines (convert to 0-based)
        new_lines = lines[: start_line - 1] + [new_content + "\n"] + lines[end_line:]

        with open(real_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        log_event("EDIT_FILE", f"{path}:{start_line}-{end_line}")
        return f"OK: {path} {start_line}–{end_line} módosítva"
    except Exception as exc:
        log_event("EDIT_FILE_ERROR", str(exc))
        return f"[ERROR] edit_file_lines: {exc}"


# ── Git integráció (Phase B) ────────────────────────────────────
def git_status(cwd: str = ".") -> str:
    """Show git status with short format."""
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        return output if output else "(clean)"
    except Exception as exc:
        return f"[ERROR] git_status: {exc}"


def git_diff(path: str = None, cwd: str = ".") -> str:
    """Show git diff for a file or all changes."""
    try:
        cmd = ["git", "diff"]
        if path:
            cmd.append(path)

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout
        lines = output.split("\n")
        if len(lines) > 200:
            return "\n".join(lines[:100]) + f"\n\n… [truncated, total {len(lines)} lines]"
        return output.strip() or "(no changes)"
    except Exception as exc:
        return f"[ERROR] git_diff: {exc}"


def git_commit(message: str, cwd: str = ".") -> str:
    """Commit all staged changes."""
    try:
        # Add all changes first
        subprocess.run(
            ["git", "add", "-A"],
            cwd=cwd,
            capture_output=True,
            timeout=10,
        )

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            log_event("GIT_COMMIT", message[:50])
            return result.stdout.strip()
        else:
            return result.stderr.strip() or "Nincs mit commitolni"
    except Exception as exc:
        return f"[ERROR] git_commit: {exc}"


def git_log(n: int = 10, cwd: str = ".") -> str:
    """Show git log (last n commits)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-n{n}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or "(empty)"
    except Exception as exc:
        return f"[ERROR] git_log: {exc}"


# ── Kód review és magyarázat (Phase C) ──────────────────────────
def review_file(path: str) -> str:
    """
    Request LLM code review for a file.
    Checks for: errors, security issues, improvements.
    """
    try:
        real_path = safe_path(path)
        if not real_path or not os.path.isfile(real_path):
            return f"[ERROR] Fájl nem elérhető: {path}"

        with open(real_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        if len(lines) > 300:
            content = "\n".join(lines[:300]) + f"\n\n… [truncated, total {len(lines)} lines]"

        # Import here to avoid circular dependency
        from src.llm import get_answer

        messages = [
            {
                "role": "user",
                "content": f"""Nézd át ezt a kódot és jelezd:
1. Hibák vagy problémák
2. Biztonsági problémák
3. Javítási javaslatok

Fájl: {path}

```
{content}
```""",
            }
        ]

        response = get_answer(messages)
        log_event("REVIEW_FILE", path)
        return response
    except Exception as exc:
        log_event("REVIEW_FILE_ERROR", str(exc))
        return f"[ERROR] review_file: {exc}"


def explain_code(path: str, start_line: int = None, end_line: int = None) -> str:
    """Explain code in a file (or specific line range)."""
    try:
        real_path = safe_path(path)
        if not real_path or not os.path.isfile(real_path):
            return f"[ERROR] Fájl nem elérhető: {path}"

        with open(real_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Extract specific lines if requested
        if start_line and end_line:
            if start_line < 1 or end_line > len(lines):
                return f"[ERROR] Érvénytelen sor-tartomány"
            content = "".join(lines[start_line - 1 : end_line])
            range_str = f" ({start_line}–{end_line})"
        else:
            content = "".join(lines)
            range_str = ""

        from src.llm import get_answer

        messages = [
            {
                "role": "user",
                "content": f"""Magyarázd el ezt a kódot {range_str}:

Fájl: {path}

```
{content}
```""",
            }
        ]

        response = get_answer(messages)
        log_event("EXPLAIN_CODE", path)
        return response
    except Exception as exc:
        log_event("EXPLAIN_CODE_ERROR", str(exc))
        return f"[ERROR] explain_code: {exc}"


def find_bugs(path: str) -> str:
    """Find potential bugs and security issues in code."""
    try:
        real_path = safe_path(path)
        if not real_path or not os.path.isfile(real_path):
            return f"[ERROR] Fájl nem elérhető: {path}"

        with open(real_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        if len(lines) > 300:
            content = "\n".join(lines[:300])

        from src.llm import get_answer

        messages = [
            {
                "role": "user",
                "content": f"""Keresd meg a hibákat és biztonsági problémákat ebben a kódban:

Fájl: {path}

```
{content}
```

Listázd:
1. Kritikus hibák
2. Biztonsági problémák
3. Potenciális runtime hibák""",
            }
        ]

        response = get_answer(messages)
        log_event("FIND_BUGS", path)
        return response
    except Exception as exc:
        log_event("FIND_BUGS_ERROR", str(exc))
        return f"[ERROR] find_bugs: {exc}"


# ── Teszt integráció (Phase D) ─────────────────────────────────
def run_tests(path: str = ".", test_file: str = None, timeout: int = 60) -> str:
    """Run pytest tests."""
    try:
        target = test_file if test_file else path
        result = subprocess.run(
            ["python3", "-m", "pytest", target, "-v", "--tb=short"],
            cwd=".",
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = (result.stdout + result.stderr).split("\n")
        if len(output) > 100:
            output = output[:50] + ["…"] + output[-50:]

        return "\n".join(output)
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Tesztek túl sokáig futottak ({timeout}s)"
    except Exception as exc:
        return f"[ERROR] run_tests: {exc}"


def generate_tests(path: str) -> str:
    """Generate pytest tests for a file using LLM."""
    try:
        real_path = safe_path(path)
        if not real_path or not os.path.isfile(real_path):
            return f"[ERROR] Fájl nem elérhető: {path}"

        with open(real_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        if len(lines) > 200:
            content = "\n".join(lines[:200])

        from src.llm import get_answer

        messages = [
            {
                "role": "user",
                "content": f"""Generálj pytest unit teszteket ehhez a kódhoz:

Fájl: {path}

```python
{content}
```

Írj komplett, futtatható pytest tesztkódot. Az output legyen csak Python kód, nincs magyarázat.""",
            }
        ]

        response = get_answer(messages)

        # Extract code block if present
        code_match = re.search(r"```(?:python)?\n(.*?)\n```", response, re.DOTALL)
        if code_match:
            test_code = code_match.group(1)
        else:
            test_code = response

        # Write test file
        test_path = real_path.replace(".py", "_test.py")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)

        log_event("GENERATE_TESTS", f"{path} → {test_path}")
        return f"OK: Tesztek írva: {test_path}\n\n{test_code[:500]}…"
    except Exception as exc:
        log_event("GENERATE_TESTS_ERROR", str(exc))
        return f"[ERROR] generate_tests: {exc}"
