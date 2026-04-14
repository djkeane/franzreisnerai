"""Franz – teljes interaktív REPL a terminálhoz. Belépési pont: main()."""

from __future__ import annotations

import datetime
import os
import pathlib
import platform
import subprocess
import sys
from typing import Dict, List, Optional

# ── readline (opcionális, graceful degradation) ────────────────
try:
    import readline as _rl
    _HAS_READLINE = True
except ImportError:
    _HAS_READLINE = False

from src.config import cfg
from src.hooks import list_hooks, load_hooks, trigger_hook
from src.llm import (
    MAX_TOOL_STEPS,
    OLLAMA_URLS,
    STREAM_OUTPUT,
    StreamParser,
    get_answer,
    get_loaded_models,
    ollama_chat,
    parse_tool_calls,
    pick_best_model,
    strip_tool_blocks,
)
from src.memory import (
    get_active_topic,
    list_topics,
    load_topic_history,
    make_snapshot,
    revert_snapshot,
    save_memory,
    search_memory,
    set_active_topic,
    truncate_history,
)
from src.learn import bake, context_for, fetch_url, forget, learn, list_knowledge, mark_core
from src.router import natural_to_command
from src.security import FRANZ_DIR, log_event
from src.classifier import classify  # Phase A: agentic task detection
from src.tools import AGENT_TOOLS  # Phase A: tool registry
from src.workflows.code_improve import coding_loop, generate_project
from src.workflows.auto_learn import auto_learn
from src.workflows.autonomous import get_autonomous
from src.tools import (
    cat_file,
    disk_usage,
    docker_cmd,
    edit_file_lines,
    exec_shell_safe,
    exec_tool,
    explain_code,
    find_bugs,
    generate_tests,
    git_commit,
    git_diff,
    git_log,
    git_status,
    grep_in_files,
    kubectl_cmd,
    list_directory,
    listening_ports,
    network_info,
    process_list,
    review_file,
    run_tests,
    running_services,
    search_files,
    system_status,
)

# ── ASCII Banner ───────────────────────────────────────────────
_BANNER = r"""
 ███████╗██████╗  █████╗ ███╗   ██╗███████╗
 ██╔════╝██╔══██╗██╔══██╗████╗  ██║╚══███╔╝
 █████╗  ██████╔╝███████║██╔██╗ ██║  ███╔╝
 ██╔══╝  ██╔══██╗██╔══██║██║╚██╗██║ ███╔╝
 ██║     ██║  ██║██║  ██║██║ ╚████║███████╗
 ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝
   Franz v7.5 – DömösAiTech 2026  |  Advanced Agentic AI Terminal
"""

_HISTORY_FILE = pathlib.Path.home() / ".franz_history"
_DEFAULT_MODEL = cfg.get("ollama", "default_model", fallback="jarvis-hu-coder:latest")
_CONFIRM_BASH = cfg.getboolean("agent", "confirm_bash", fallback=False)


# ── Model warmup ───────────────────────────────────────────────

def warmup_model(model: str) -> None:
    """Betölti a modellt VRAM-ba a háttérben (blokkolásmentes)."""
    import threading

    try:
        import requests as _req
        _has_requests = True
    except ImportError:
        _has_requests = False

    def _do() -> None:
        for url in OLLAMA_URLS:
            load_url = url.replace("/api/chat", "/api/generate")
            try:
                if _has_requests:
                    _req.post(
                        load_url,
                        json={"model": model, "prompt": "", "keep_alive": "60m", "stream": False},
                        timeout=(5, 300),
                    )
                else:
                    import json as _json, urllib.request as _urlreq
                    data = _json.dumps({"model": model, "prompt": "", "keep_alive": "60m", "stream": False}).encode()
                    req = _urlreq.Request(load_url, data=data, headers={"Content-Type": "application/json"})
                    with _urlreq.urlopen(req, timeout=300):
                        pass
                log_event("WARMUP_OK", model)
                return
            except Exception as exc:
                log_event("WARMUP_FAIL", f"{model}@{url}: {exc}")

    threading.Thread(target=_do, daemon=True, name="franz-warmup").start()


# ── Readline setup ─────────────────────────────────────────────

def setup_readline() -> None:
    if not _HAS_READLINE:
        return
    try:
        _rl.read_history_file(str(_HISTORY_FILE))
    except (FileNotFoundError, PermissionError):
        pass
    _rl.set_history_length(2000)

    commands = [
        "/help", "/exit", "/quit", "/topic", "/topics", "/snapshot", "/revert",
        "/search", "/agent", "/agents", "/hooks", "/diag", "/clear",
        "ls:", "cat:", "du:", "ps:", "top", "net:", "svc:", "docker:", "kubectl:", "run:",
    ]

    def _completer(text: str, state: int) -> Optional[str]:
        matches = [c for c in commands if c.startswith(text)]
        return matches[state] if state < len(matches) else None

    _rl.set_completer(_completer)
    _rl.parse_and_bind("tab: complete")


def _save_history() -> None:
    if _HAS_READLINE:
        try:
            _rl.write_history_file(str(_HISTORY_FILE))
        except Exception:
            pass


# ── Input helpers ──────────────────────────────────────────────

def get_input(prompt: str) -> str:
    """
    Többsoros bevitel:
      - sor végén '\\' -> folytatás következő sorban
      - '```' -> paste mód (addig olvas, amíg újabb '```' nem érkezik)
    """
    try:
        line = input(prompt)
    except (KeyboardInterrupt, EOFError):
        return "/exit"

    if line.strip() == "```":
        print("  [paste mód – zárd '```'-vel]")
        lines: List[str] = []
        while True:
            try:
                chunk = input()
            except (KeyboardInterrupt, EOFError):
                break
            if chunk.strip() == "```":
                break
            lines.append(chunk)
        return "\n".join(lines)

    parts = [line]
    while parts[-1].endswith("\\"):
        parts[-1] = parts[-1][:-1]
        try:
            parts.append(input("... "))
        except (KeyboardInterrupt, EOFError):
            break
    return "\n".join(parts)


# ── System prompt builder ──────────────────────────────────────

def _git_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        branch = result.stdout.strip()
        return branch if branch else "none"
    except Exception:
        return "none"


def _cpu_ram() -> str:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        return f"CPU {cpu:.0f}%  RAM {ram.percent:.0f}% ({ram.used // 1_048_576} MB / {ram.total // 1_048_576} MB)"
    except Exception:
        return "CPU/RAM info nem elérhető"


def build_system_prompt(topic: str, query: str = "") -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cwd = os.getcwd()
    branch = _git_branch()
    hw = _cpu_ram()
    base = (
        "Te vagy Franz, a DömösAiTech 2026 intelligens terminál-asszisztense.\n"
        "Magyarul válaszolsz, tömören és pontosan.\n\n"
        f"Dátum/idő: {now}\n"
        f"Téma:      {topic}\n"
        f"CWD:       {cwd}\n"
        f"Git ág:    {branch}\n"
        f"Rendszer:  {hw}\n"
        f"Platform:  {platform.system()} {platform.release()}"
    )
    # RAG: tanult tudás injektálása ha van releváns találat
    if query:
        ctx = context_for(query, top_k=3)
        if ctx:
            base += f"\n\n{ctx}"
    return base


def build_agent_system_prompt(topic: str, query: str = "") -> str:
    """
    Build system prompt for agentic task (Phase A.1).
    Includes tool registry and agentic mode instructions.
    """
    base = build_system_prompt(topic, query)
    tools_block = "\n".join(f"  - {k}: {v}" for k, v in AGENT_TOOLS.items())
    return (
        base
        + "\n\n## Agentic Mód — Eszközök\n"
        + "Tool-hívás formátuma:\n```tool\n{\"tool\": \"...\", \"args\": {...}, \"reason\": \"...\"}\n```\n\n"
        + f"Elérhető eszközök:\n{tools_block}\n\n"
        + "Szabályok:\n"
        + "1. Lépésről lépésre haladj, minden lépésnél egy tool-t hívj.\n"
        + "2. Ha befejezted, MINDIG hívd meg a `task_done` eszközt.\n"
        + "3. Soha ne generálj szöveget a ```tool blokkon kívül, ha éppen toolokat használsz.\n"
    )


# ── Agent loop ─────────────────────────────────────────────────

def _log_agent_session(query: str, steps: int, tools_used: list, success: bool = True, summary: str = "") -> None:
    """Phase A: Agent session logging helper."""
    log_event(
        "AGENT_SESSION",
        f"steps={steps}, tools={len(tools_used)}, success={success}, query={query[:60]}…"
    )


def agent_loop(
    messages: List[Dict],
    tools_exec_fn=exec_tool,
    model: str = _DEFAULT_MODEL,
    stream: bool = STREAM_OUTPUT,
) -> str:
    """
    Streaming + tool-call agent hurok, max MAX_TOOL_STEPS iteráció (Phase A.2–A.5).
    - task_done sentinel support
    - JSON parse error recovery (max 3 retries per step)
    - Max-step summary fallback
    - Agent session logging
    """
    step = 0
    final_text = ""
    original_query = messages[-1].get("content", "")[:200] if messages else ""
    all_tool_names: list[str] = []
    parse_retries = 0
    MAX_PARSE_RETRIES = 3

    while step < MAX_TOOL_STEPS:
        step += 1
        parser = StreamParser()

        if stream:
            try:
                resp = ollama_chat(model, messages, stream=True)
                if resp is None:
                    raise ConnectionError("Null response from Ollama")
                for raw_line in resp.iter_lines():  # type: ignore[union-attr]
                    if not raw_line:
                        continue
                    import json as _json
                    try:
                        obj = _json.loads(raw_line)
                    except Exception:
                        continue
                    chunk = obj.get("message", {}).get("content", "")
                    printable = parser.feed(chunk)
                    if printable:
                        print(printable, end="", flush=True)
                    if obj.get("done"):
                        break
                remainder = parser.flush()
                if remainder:
                    print(remainder, end="", flush=True)
                print()
            except Exception as exc:
                log_event("STREAM_ERROR", str(exc))
                answer = get_answer(messages)
                print(answer)
                final_text = answer
                break
        else:
            answer = get_answer(messages)
            print(answer)
            parser.text_parts = [answer]
            parser.tool_calls = parse_tool_calls(answer)

        full = parser.full_text if stream else answer  # type: ignore[possibly-undefined]
        final_text = strip_tool_blocks(full)
        tool_calls = parser.tool_calls if stream else parse_tool_calls(full)  # type: ignore[possibly-undefined]

        # Phase A.3: JSON parse error recovery
        if parser.had_parse_error and parse_retries < MAX_PARSE_RETRIES:
            messages.append({
                "role": "user",
                "content": (
                    "[PARSE_ERROR] Az előző tool-hívás érvénytelen JSON volt. "
                    "Formátum: ```tool\n{\"tool\": \"...\", \"args\": {...}}\n```"
                )
            })
            parser.had_parse_error = False
            parse_retries += 1
            continue

        if not tool_calls:
            break

        messages.append({"role": "assistant", "content": full})

        for tc in tool_calls:
            name = tc.get("tool", tc.get("name", ""))
            args = tc.get("args", tc.get("arguments", {}))
            log_event("TOOL_CALL", f"{name}({args})")
            all_tool_names.append(name)

            # Megerősítés kérése bash tool-ra ha confirm_bash = true
            if name == "bash" and _CONFIRM_BASH:
                cmd = args.get("command", "")
                print(f"\033[33m[TOOL bash] Parancs: {cmd}\033[0m")
                try:
                    confirm = input("Futtatod? [i/N] ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    confirm = "n"
                if confirm not in ("i", "igen", "y", "yes"):
                    result = "[SKIP] Felhasználó megszakította."
                    print(f"\033[33m{result}\033[0m")
                    messages.append({"role": "user", "content": f"[Tool: {name}]\n{result}"})
                    continue

            result = tools_exec_fn(name, args)

            # Phase A.2: task_done sentinel handling
            if isinstance(result, str) and result.startswith("__TASK_DONE__:"):
                summary = result[len("__TASK_DONE__:"):]
                print(f"\n\033[92m✓ KÉSZ: {summary}\033[0m\n")
                _log_agent_session(original_query, step, all_tool_names, success=True, summary=summary)
                return final_text + f"\n\n{summary}"

            tool_msg = f"[Tool: {name}]\n{result}"
            print(f"\033[33m{tool_msg}\033[0m")
            messages.append({"role": "user", "content": tool_msg})

    # Phase A.5: Max step reached — request summary
    if step >= MAX_TOOL_STEPS:
        log_event("AGENT_STEP_LIMIT", f"max {MAX_TOOL_STEPS} lépés elérve")
        messages.append({
            "role": "user",
            "content": "[RENDSZER] Elérted a maximális lépéskorlátot. Foglalja össze röviden mi lett kész és mi maradt."
        })
        summary = get_answer(messages)
        print(f"\033[33m[ÖSSZEFOGLALÓ] {summary}\033[0m")
        _log_agent_session(original_query, step, all_tool_names, success=False, summary=summary)

    return final_text


# ── Help ───────────────────────────────────────────────────────

def _print_help() -> None:
    help_text = """
\033[1mFranz v7.5 – Parancsok\033[0m

  /help               Ez a súgó
  /exit | /quit       Kilépés
  /clear              Képernyő törlése
  /diag               Diagnosztika futtatása

\033[1mTéma-kezelés:\033[0m
  /topic <név>        Aktív témát vált (létrehozza ha nem létezik)
  /topics             Meglévő témák listája
  /snapshot           Aktuális téma pillanatkép mentése
  /revert <bak>       Visszaállítás backup fájlból
  /search <kulcsszó>  Keresés az emlékezetben

\033[1mAgensek:\033[0m
  /agents             Elérhető agensek listája
  /agent <név> <feladat>  Agens indítása feladattal

\033[1m📚 MAGYAR NYELVTAN TANÍTÓ (v7.5):\033[0m
  /nyelvtan           Összes szabály listázása
  /nyelvtan <rule_id> Egy szabály tanítása (pl. case_nominative)
  /nyelvtan elemzés <mondat>  Mondat nyelvtani elemzése
  /nyelvtan gyakorlat Nyelvtani gyakorlat kitöltése
  /nyelvtan ellenőrzés <szöveg>  Szöveg ellenőrzése
  /nyt <rule_id>      Gyors nyelvtan parancs

\033[1m🤖 SMART MODEL ROUTER (v7.5):\033[0m
  /modellek           Összes modell listázása
  /modell-status      Router státusza + teljesítmény
  /modell-reset       Modell statisztikájának alaphelyzetbe állítása
  /modell-test <m>    Modell tesztelése (timeout: 15s)

\033[1mMunkafolyamatok:\033[0m
  /kod <feladat>      Teljes kódolási ciklus (generálás → írás → futtatás → debug)
  /projekt <feladat>  Többfájlos projekt generálása
  /tanul-web <téma>   Web keresés + tanulás (DuckDuckGo → RAG)
  /loop               Autonóm loop indítása (tanulás + fejlesztés)
  /loop-status        Loop állapota
  /loop-stop          Loop leállítása

\033[1mBeépített eszközök:\033[0m
  /dir [path]         Könyvtár tartalom listázása
  /servers            Hallgatózó portok + futó szolgáltatások
  /ports              Hallgatózó portok listája
  ls:<path>           Könyvtár tartalom (Franz-on belül)
  cat:<path>          Fájl olvasása
  du:<path>           Lemezhasználat
  ps:<filter>         Folyamatok listája
  top                 Rendszer-terhelés (CPU/RAM)
  net:<host:port>     Hálózati info / port ellenőrzés
  svc:<action> <svc>  systemctl művelet
  docker:<args>       Docker parancs
  kubectl:<args>      kubectl parancs
  run:<cmd>           Shell parancs (whitelist-en szereplők)

\033[1mFájlrendszer & keresés:\033[0m
  /keresés <minta>    Fájlkeresés glob minta alapján (pl. "*.py", "src/**/*.ts")
  /grep <minta>       Szöveges keresés fájlokban (regex)
  /szerk <f> <s-e> <t> Sor-szintű szerkesztés (start-end sor, tartalom)

\033[1mGit integráció:\033[0m
  /git status         Git állapot
  /git diff [fájl]    Git diff (összes vagy adott fájl)
  /git commit "<msg>" Commit a megadott üzenettel
  /git log [n]        Utolsó n commit

\033[1mKód analízis (LLM-alapú):\033[0m
  /review <fájl>      Kód review (hibák, biztonsági problémák, javaslatok)
  /magyaráz <fájl>    Kód magyarázata
  /hibák <fájl>       Potenciális hibák és biztonsági problémák keresése

\033[1mTesztelés:\033[0m
  /teszt [fájl]       Pytest futtatása
  /teszt-generál <f>  Unit tesztek generálása LLM-mel

\033[1mTanulás / önfejlesztés:\033[0m
  /tanul <szöveg>         Tény megtanulása (embedding + tárolás)
  /tanul url:<url>        URL tartalmának megtanulása
  /tanul core:<id>        Bejegyzés core-nak jelölése
  /felejtsd <minta>       Bejegyzések törlése
  /tudom                  Tanult tudás listája
  /tudom <keresés>        Keresés a tudásban
  /fejlodj                Tudás beépítése Modelfile-ba → ollama create

\033[1mPlugin hook-ok:\033[0m  """ + ", ".join(list_hooks() or ["(nincs betöltve)"]) + """

  Minden egyéb szöveg: LLM-nek küldve (auto-routing: code→qwen2.5-coder:7b).
"""
    print(help_text)


# ── Command handlers ───────────────────────────────────────────

def handle_tool_commands(user_input: str) -> bool:
    stripped = user_input.strip()

    # ── Könyvtár parancsok ──────────────────────────────────────
    if stripped == "/dir" or stripped.startswith("/dir "):
        path = stripped[4:].strip() if stripped.startswith("/dir ") else "."
        print(list_directory(path))
        return True

    # ── Szerver / Port parancsok ────────────────────────────────
    if stripped == "/servers":
        print("\n📡 Hallgatózó portok:")
        print(listening_ports())
        print("\n🔧 Futó szolgáltatások:")
        print(running_services())
        return True

    if stripped == "/ports":
        print(listening_ports())
        return True

    # ── Fájlrendszer parancsok (Phase A) ────────────────────────
    if stripped.startswith("/keresés "):
        pattern = stripped[9:].strip()
        print(search_files(pattern))
        return True

    if stripped.startswith("/grep "):
        args = stripped[6:].strip()
        # Parse: /grep <pattern> [--ext .py,.ts]
        parts = args.split(" --ext ")
        pattern = parts[0]
        extensions = None
        if len(parts) > 1:
            extensions = [ext.strip() for ext in parts[1].split(",")]
        print(grep_in_files(pattern, extensions=extensions))
        return True

    if stripped.startswith("/szerk "):
        # /szerk <fájl> <start>-<end> <tartalom>
        args = stripped[7:].strip()
        parts = args.split(None, 2)
        if len(parts) >= 3:
            file_path = parts[0]
            range_str = parts[1]
            content = parts[2]
            try:
                start, end = map(int, range_str.split("-"))
                print(edit_file_lines(file_path, start, end, content))
            except ValueError:
                print("[ERROR] Formátum: /szerk <fájl> <start>-<end> <tartalom>")
        else:
            print("[ERROR] Formátum: /szerk <fájl> <start>-<end> <tartalom>")
        return True

    # ── Git parancsok (Phase B) ────────────────────────────────
    if stripped == "/git status":
        print(git_status())
        return True

    if stripped.startswith("/git diff"):
        path = stripped[9:].strip() if len(stripped) > 9 else None
        print(git_diff(path))
        return True

    if stripped.startswith("/git commit "):
        message = stripped[12:].strip()
        print(git_commit(message))
        return True

    if stripped.startswith("/git log"):
        n_str = stripped[8:].strip()
        n = int(n_str) if n_str.isdigit() else 10
        print(git_log(n))
        return True

    # ── Kód review parancsok (Phase C) ──────────────────────────
    if stripped.startswith("/review "):
        file_path = stripped[8:].strip()
        print(f"\n🔍 Kód review: {file_path}\n")
        print(review_file(file_path))
        return True

    if stripped.startswith("/magyaráz "):
        args = stripped[10:].strip()
        parts = args.split()
        if not parts:
            print("[ERROR] Használat: /magyaráz <fájl> [start-end]")
            return True
        file_path = parts[0]
        start_line, end_line = None, None
        if len(parts) > 1:
            try:
                start_line, end_line = map(int, parts[1].split("-"))
            except ValueError:
                pass
        print(f"\n📖 Kód magyarázat: {file_path}\n")
        print(explain_code(file_path, start_line, end_line))
        return True

    if stripped.startswith("/hibák "):
        file_path = stripped[7:].strip()
        print(f"\n🐛 Hibakerés: {file_path}\n")
        print(find_bugs(file_path))
        return True

    # ── Teszt parancsok (Phase D) ──────────────────────────────
    if stripped == "/teszt" or stripped.startswith("/teszt "):
        test_file = stripped[7:].strip() if len(stripped) > 7 else None
        print(f"\n✅ Tesztek futtatása {test_file or '(alapkönyvtár)'}\n")
        print(run_tests(test_file=test_file))
        return True

    if stripped.startswith("/teszt-generál "):
        file_path = stripped[15:].strip()
        print(f"\n✍️  Tesztgenerálás: {file_path}\n")
        print(generate_tests(file_path))
        return True

    if stripped.startswith("ls:"):
        print(list_directory(stripped[3:].strip() or "."))
        return True
    if stripped.startswith("cat:"):
        print(cat_file(stripped[4:].strip()))
        return True
    if stripped.startswith("du:"):
        print(disk_usage(stripped[3:].strip() or "."))
        return True
    if stripped.startswith("ps:"):
        print(process_list(stripped[3:].strip()))
        return True
    if stripped == "top":
        print(_cpu_ram())
        return True
    if stripped.startswith("net:"):
        print(network_info(stripped[4:].strip()))
        return True
    if stripped.startswith("svc:"):
        rest = stripped[4:].strip().split(None, 1)
        if len(rest) == 2:
            print(system_status(rest[0], rest[1]))
        else:
            print("[ERROR] Használat: svc:<action> <service_name>")
        return True
    if stripped.startswith("docker:"):
        print(docker_cmd(stripped[7:].strip()))
        return True
    if stripped.startswith("kubectl:"):
        print(kubectl_cmd(stripped[8:].strip()))
        return True
    if stripped.startswith("run:"):
        print(exec_shell_safe(stripped[4:].strip()))
        return True

    return False


def handle_topic_commands(user_input: str, history: List[Dict]) -> bool:
    stripped = user_input.strip()

    if stripped.startswith("/topic "):
        new_topic = stripped[7:].strip()
        if new_topic:
            set_active_topic(new_topic)
            history.clear()
            history.extend(load_topic_history(new_topic))
            print(f"Téma váltva: \033[92m{new_topic}\033[0m ({len(history)} bejegyzés)")
            log_event("TOPIC_SWITCH", new_topic)
        else:
            print(f"Aktív téma: \033[92m{get_active_topic()}\033[0m")
        return True

    if stripped == "/topics":
        topics = list_topics()
        active = get_active_topic()
        for t in topics:
            print(f"  {'*' if t == active else ' '} {t}")
        if not topics:
            print("  (nincs téma)")
        return True

    if stripped == "/snapshot":
        bak = make_snapshot(get_active_topic())
        print(f"Pillanatkép: {bak}" if bak else "Nincs mit menteni.")
        return True

    if stripped.startswith("/revert "):
        bak_name = stripped[8:].strip()
        topic = get_active_topic()
        if revert_snapshot(topic, bak_name):
            history.clear()
            history.extend(load_topic_history(topic))
            print(f"Visszaállítva: {bak_name}")
        else:
            print(f"[ERROR] Backup nem található: {bak_name}")
        return True

    if stripped.startswith("/search "):
        query = stripped[8:].strip()
        results = search_memory(get_active_topic(), query)
        if results:
            for r in results:
                print(f"  [{r.get('role','?')}] {r.get('timestamp','')[:19]}  {r.get('content','')[:120]}")
        else:
            print("  (nincs találat)")
        return True

    return False


def handle_agent_commands(user_input: str, history: List[Dict], registry) -> bool:
    stripped = user_input.strip()

    if stripped == "/agents":
        agents = registry.list()
        if agents:
            print(f"\n{'Név':<20}  {'Megjelenési név':<25}  Leírás")
            print("-" * 80)
            for name, display, desc in agents:
                print(f"  {name:<18}  {display:<25}  {desc}")
        else:
            print("  (nincs betöltött agens)")
        print()
        return True

    if stripped.startswith("/agent "):
        rest = stripped[7:].strip()
        parts = rest.split(None, 1)
        if len(parts) < 2:
            print("[ERROR] Használat: /agent <AgentNév> <feladat>")
            return True
        agent_name, task = parts[0], parts[1]
        agent = registry.get(agent_name)
        if agent is None:
            print(f"[ERROR] Ismeretlen agens: {agent_name!r}")
            print(f"  Elérhető: {[n for n, _, _ in registry.list()]}")
            return True

        topic = get_active_topic()
        sys_prompt = agent.system_prompt(task)  # type: ignore[attr-defined]
        messages: List[Dict] = [{"role": "system", "content": sys_prompt}]
        messages += truncate_history(history)
        messages.append({"role": "user", "content": task})

        print(f"\n\033[94m[{agent.display_name}]\033[0m {task}\n")  # type: ignore[attr-defined]
        answer = agent_loop(messages, model=agent.model)  # type: ignore[attr-defined]

        save_memory(topic, "user", f"[{agent_name}] {task}")
        save_memory(topic, "assistant", answer)
        history.append({"role": "user", "content": task})
        history.append({"role": "assistant", "content": answer})
        log_event("AGENT_RUN", f"{agent_name}: {task[:80]}")
        return True

    return False


def handle_grammar_commands(user_input: str) -> bool:
    """
    Magyar nyelvtan tanító parancsok (v7.5):
      /nyelvtan                       — Összes szabály listázása
      /nyelvtan <rule_id>            — Egy szabály tanítása
      /nyelvtan elemzés <mondat>     — Mondat elemzése
      /nyelvtan gyakorlat            — Nyelvtani gyakorlat
      /nyelvtan ellenőrzés <szöveg>  — Szöveg ellenőrzése
    """
    stripped = user_input.strip()

    # ── Nyelvtan parancsok ──────────────────────────────────────
    if stripped == "/nyelvtan" or stripped.startswith("/nyelvtan "):
        from src.workflows.hungarian_grammar import (
            list_all_rules, teach_grammar, explain_grammar,
            practice_exercise, check_grammar
        )

        if stripped == "/nyelvtan":
            print(list_all_rules())
            return True

        rest = stripped[10:].strip()

        # /nyelvtan elemzés <mondat>
        if rest.startswith("elemzés "):
            sentence = rest[8:].strip()
            print(explain_grammar(sentence))
            return True

        # /nyelvtan gyakorlat
        if rest == "gyakorlat":
            print(practice_exercise())
            return True

        # /nyelvtan ellenőrzés <szöveg>
        if rest.startswith("ellenőrzés "):
            text = rest[11:].strip()
            print(check_grammar(text))
            return True

        # /nyelvtan <rule_id>
        if rest and not rest.startswith(" "):
            print(teach_grammar(rest))
            return True

    # ── Nyelvtan gyors parancsok ────────────────────────────────
    if stripped.startswith("/nyt "):
        from src.workflows.hungarian_grammar import teach_grammar
        rule_id = stripped[5:].strip()
        print(teach_grammar(rule_id))
        return True

    if stripped == "/nyt":
        from src.workflows.hungarian_grammar import list_all_rules
        print(list_all_rules())
        return True

    return False


def handle_router_commands(user_input: str) -> bool:
    """
    Smart Model Router parancsok (v7.5):
      /modellek               — Összes modell listázása
      /modell-status          — Router státusza + teljesítmény
      /modell-reset           — Modell statisztikájának alaphelyzetbe állítása
      /modell-test <model>    — Modell tesztelése
    """
    stripped = user_input.strip()

    if stripped == "/modellek":
        from src.model_router import list_all_models
        models = list_all_models()

        print("\n╔══════════════════════════════════════════════════════════════════════════════╗")
        print("║ 🤖 SMART MODEL ROUTER — ELÉRHETŐ MODELLEK")
        print("╚══════════════════════════════════════════════════════════════════════════════╝\n")

        by_category = {}
        for name, info in models.items():
            cat = info["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((name, info))

        for cat in sorted(by_category.keys()):
            print(f"\n🏷️  {cat.upper()}")
            print("─" * 80)
            for name, info in by_category[cat]:
                enabled = "✅" if info["enabled"] else "❌"
                print(f"{enabled} {name:30} | Speed: {info['speed']:6} | Quality: {info['quality']:6}")
                print(f"   Timeout: {info['timeout']:6} | Suitable: {', '.join(info['suitable_for'][:3])}")
                if info["failures"] > 0:
                    print(f"   ⚠️  Failures: {info['failures']} | Avg response: {info['avg_response_time']}")

        return True

    if stripped == "/modell-status":
        from src.llm.smart_ollama import get_smart_model_status
        print(get_smart_model_status())
        return True

    if stripped == "/modell-reset":
        from src.model_router import router
        router.reset_model_stats()
        print("✅ Összes modell statisztikája alaphelyzetbe állítva")
        return True

    if stripped.startswith("/modell-test "):
        model = stripped[13:].strip()
        print(f"🧪 {model} tesztelése...")
        # Ez egy egyszerű tesztület
        from src.llm.smart_ollama import smart_chat
        result = smart_chat(
            [{"role": "user", "content": "Válaszolj: OK"}],
            model=model,
            timeout=15
        )
        if result:
            print(f"✅ {model} válaszolt: {result[:100]}…")
        else:
            print(f"❌ {model} nem válaszolt vagy timeout")
        return True

    return False


def handle_learn_commands(user_input: str) -> bool:
    """
    Tanulási parancsok:
      /tanul <szöveg>         — tény megtanulása
      /tanul url:<url>        — URL tartalmának megtanulása
      /tanul core:<id>        — bejegyzés core-nak jelölése (Modelfile-ba kerül)
      /felejtsd <minta>       — bejegyzések törlése
      /tudom                  — tanult tudás listája
      /tudom <keresés>        — keresés a tudásban
      /fejlodj                — tanult tudás beépítése a Modelfile-ba (ollama create)
    """
    stripped = user_input.strip()

    # ── /tanul ────────────────────────────────────────────────
    if stripped.startswith("/tanul "):
        rest = stripped[7:].strip()

        if rest.startswith("url:"):
            url = rest[4:].strip()
            print(f"\033[33mLetöltés: {url}\033[0m")
            content = fetch_url(url)
            if content.startswith("[HIBA]"):
                print(content)
                return True
            entry_id = learn(content, source=url)
            preview = content[:120].replace("\n", " ")
            print(f"\033[92m✓ Megtanulva [{entry_id}]:\033[0m {preview}…")
            return True

        if rest.startswith("core:"):
            entry_id = rest[5:].strip()
            ok = mark_core(entry_id, True)
            if ok:
                print(f"\033[92m✓ [{entry_id}] core-nak jelölve → /fejlodj-kor Modelfile-ba kerül.\033[0m")
            else:
                print(f"\033[91m[ERROR] Nem találtam ilyen ID-t: {entry_id}\033[0m")
            return True

        # Egyszerű szöveg tanulása
        entry_id = learn(rest, source="user")
        print(f"\033[92m✓ Megtanulva [{entry_id}]:\033[0m {rest[:100]}")
        return True

    # ── /felejtsd ─────────────────────────────────────────────
    if stripped.startswith("/felejtsd "):
        pattern = stripped[10:].strip()
        count = forget(pattern)
        if count:
            print(f"\033[93m✓ {count} bejegyzés törölve (minta: '{pattern}').\033[0m")
        else:
            print(f"  Nincs ilyen bejegyzés: '{pattern}'")
        return True

    # ── /tudom ────────────────────────────────────────────────
    if stripped == "/tudom" or stripped.startswith("/tudom "):
        query = stripped[7:].strip() if stripped.startswith("/tudom ") else ""
        if query:
            # RAG keresés
            from src.learn import recall
            hits = recall(query, top_k=5, min_score=0.0)
            if hits:
                print(f"\n  Találatok '{query}' kérdésre:\n")
                for h in hits:
                    core_mark = " \033[93m[CORE]\033[0m" if h.get("core") else ""
                    print(f"  [{h.get('id','?')}]{core_mark} {h.get('text','')[:120]}")
                    print(f"         forrás: {h.get('source','?')} | hozzáférés: {h.get('access_count',0)}×\n")
            else:
                print("  (nincs találat)")
        else:
            entries = list_knowledge(20)
            if not entries:
                print("  (nincs tanult tudás — használd: /tanul <szöveg>)")
                return True
            print(f"\n  {'ID':<10} {'Core':<6} {'Elérés':<8} {'Forrás':<20} Szöveg")
            print("  " + "-" * 80)
            for e in entries:
                core = "\033[93m●\033[0m" if e.get("core") else " "
                src = e.get("source", "?")[:18]
                text = e.get("text", "")[:50].replace("\n", " ")
                cnt = e.get("access_count", 0)
                print(f"  [{e.get('id','?')}]  {core:<5} {cnt:<8} {src:<20} {text}")
            print()
        return True

    # ── /fejlodj ──────────────────────────────────────────────
    if stripped == "/fejlodj":
        print("\033[33mModelfile frissítés és franz-coder újrabuildelés…\033[0m")
        result = bake(max_facts=15)
        if result.startswith("✓"):
            print(f"\033[92m{result}\033[0m")
        else:
            print(result)
        return True

    return False


# ── Workflows parancsok ──────────────────────────────────────────

def handle_workflow_commands(user_input: str) -> bool:
    """
    Workflow parancsok:
      /kod <feladat>        — teljes kódolási ciklus (gen → fut → debug)
      /projekt <feladat>    — többfájlos projekt generálás
      /tanul-web <url/téma> — webről tanulás (scraping + RAG)
      /loop                 — autonóm loop indítása
      /loop-stop            — autonóm loop leállítása
      /loop-status          — autonóm loop állapota
    """
    stripped = user_input.strip()

    # ── /kod ────────────────────────────────────────────────────
    if stripped.startswith("/kod "):
        task = stripped[5:].strip()
        if not task:
            print("  Használat: /kod <feladat leírása>")
            return True

        print(f"\033[33m[Kódolási ciklus indítása…]\033[0m {task[:60]}")

        try:
            from src.llm import llm_gateway
            result = coding_loop(
                task,
                working_dir=".",
                llm_fn=lambda p: llm_gateway.chat([{"role": "user", "content": p}], task_type="code"),
                max_retries=5,
            )
        except Exception as exc:
            print(f"\033[91m[ERROR] Kódolás: {exc}\033[0m")
            return True

        if result["success"]:
            print(f"\033[92m✓ Sikeres futás {result['iterations']} iteráció után\033[0m")
            if result["output"]:
                print(f"\n  OUTPUT:\n{result['output'][:500]}")
        else:
            print(f"\033[91m✗ Sikertelen {result['iterations']} próba után\033[0m")
            print(f"  KÓD:\n{result['code'][:300]}")

        return True

    # ── /projekt ────────────────────────────────────────────────
    if stripped.startswith("/projekt "):
        task = stripped[9:].strip()
        if not task:
            print("  Használat: /projekt <feladat leírása>")
            return True

        print(f"\033[33m[Projekt generálás…]\033[0m {task[:60]}")

        try:
            from src.llm import llm_gateway
            result = generate_project(
                task,
                output_dir="./generated",
                llm_fn=lambda p: llm_gateway.chat([{"role": "user", "content": p}], task_type="code"),
            )
        except Exception as exc:
            print(f"\033[91m[ERROR] Projekt: {exc}\033[0m")
            return True

        if result["success"]:
            print(f"\033[92m✓ {result['files']} fájl generálva\033[0m")
            for path in result["paths"][:5]:
                print(f"  📄 {path}")
        else:
            print(f"\033[91m✗ Hibák történtek:\033[0m")
            for err in result["errors"][:3]:
                print(f"  • {err}")

        return True

    # ── /tanul-web ──────────────────────────────────────────────
    if stripped.startswith("/tanul-web "):
        topic = stripped[11:].strip()
        if not topic:
            print("  Használat: /tanul-web <url vagy téma>")
            return True

        print(f"\033[33m[Web tanulás…]\033[0m {topic[:60]}")

        try:
            from src.llm import llm_gateway
            stored = auto_learn(
                topic,
                llm_fn=lambda p: llm_gateway.chat([{"role": "user", "content": p}], task_type="research"),
                max_pages=3,
            )
        except Exception as exc:
            print(f"\033[91m[ERROR] Tanulás: {exc}\033[0m")
            return True

        if stored > 0:
            print(f"\033[92m✓ {stored} tény tárolta meg\033[0m")
            log_event("WEB_LEARN", f"{topic[:50]}: {stored} facts")
        else:
            print(f"\033[93m  (nincs eredmény vagy letöltési hiba)\033[0m")

        return True

    # ── /loop ───────────────────────────────────────────────────
    if stripped == "/loop":
        auto = get_autonomous()
        if auto.status()["running"]:
            print("  Autonóm loop már fut → /loop-status")
            return True

        print("\033[33m[Autonóm loop indítása…]\033[0m")
        auto.start(interval_sec=3600)  # 1 óra
        status = auto.status()
        print(f"\033[92m✓ Loop fut (iteráció/{status['iterations_today']})\033[0m")
        log_event("AUTONOMOUS_START", "user request")
        return True

    # ── /loop-stop ──────────────────────────────────────────────
    if stripped == "/loop-stop":
        auto = get_autonomous()
        if not auto.status()["running"]:
            print("  Autonóm loop nem fut")
            return True

        print("\033[33m[Autonóm loop leállítása…]\033[0m")
        auto.stop()
        print("\033[92m✓ Loop leállítva\033[0m")
        log_event("AUTONOMOUS_STOP", "user request")
        return True

    # ── /loop-status ────────────────────────────────────────────
    if stripped == "/loop-status":
        auto = get_autonomous()
        status = auto.status()
        running = "🟢 FUT" if status["running"] else "🔴 LEÁLLT"
        print(f"\n  {running}")
        print(f"  Iteráció ma: {status['iterations_today']}")
        print(f"  API hívások: {status['api_calls_today']}")
        print(f"  Tanult témák: {status['topics_learned']}")
        if status["last_topics"]:
            print(f"\n  Utolsó 5 téma:")
            for topic in status["last_topics"][-5:]:
                print(f"    • {topic['topic']}: {topic['facts']} fakt")
        print()
        return True

    return False


# ── Main REPL ──────────────────────────────────────────────────

def main() -> None:
    """Franz főhurok."""
    setup_readline()
    load_hooks()

    from src.agents import AgentRegistry
    registry = AgentRegistry()

    topic = get_active_topic()
    history: List[Dict] = list(truncate_history(load_topic_history(topic)))

    print(_BANNER)
    print(f"  Téma: \033[92m{topic}\033[0m  |  Agensek: {len(registry.list())}  |  Hook-ok: {len(list_hooks())}")

    # VRAM-aware model warmup
    loaded = get_loaded_models()
    best = pick_best_model()
    if best in loaded:
        print(f"  Modell VRAM-ban: \033[92m{best}\033[0m")
    else:
        print(f"  Modell betöltés háttérben: \033[33m{best}\033[0m")
        warmup_model(best)

    print("  Írd: \033[1m/help\033[0m a parancsokért, \033[1m/exit\033[0m a kilépéshez.\n")
    log_event("SESSION_START", f"topic={topic}")

    while True:
        try:
            current_topic = get_active_topic()
            prompt_str = f"\033[96mFranz\033[0m[\033[92m{current_topic}\033[0m]> "
            user_input = get_input(prompt_str)
        except (KeyboardInterrupt, EOFError):
            print("\nViszlát!")
            _save_history()
            log_event("SESSION_END", "KeyboardInterrupt")
            sys.exit(0)

        stripped = user_input.strip()
        if not stripped:
            continue

        # ── Természetes nyelvű parancs-felismerés ───────────────
        cmd = natural_to_command(stripped)
        if cmd:
            stripped = cmd

        # ── Meta-parancsok ──────────────────────────────────────
        if stripped in ("/exit", "/quit"):
            print("Viszlát!")
            _save_history()
            log_event("SESSION_END", "exit")
            sys.exit(0)

        if stripped in ("/help", "help"):
            _print_help()
            continue

        if stripped == "/clear":
            os.system("clear" if os.name != "nt" else "cls")
            continue

        if stripped == "/diag":
            try:
                from src.diagnostics import run_diagnostics
                run_diagnostics()
            except Exception as exc:
                print(f"[ERROR] Diagnosztika: {exc}")
            continue

        # ── Tanulási parancsok ──────────────────────────────────
        if handle_learn_commands(stripped):
            continue

        # ── Workflow parancsok (kódolás, webtanulás, loop) ─────
        if handle_workflow_commands(stripped):
            continue

        # ── Agens parancsok ─────────────────────────────────────
        if handle_agent_commands(stripped, history, registry):
            continue

        # ── Téma parancsok ─────────────────────────────────────
        if handle_topic_commands(stripped, history):
            continue

        # ── Beépített eszközök ──────────────────────────────────
        if handle_tool_commands(stripped):
            log_event("CMD", stripped[:100])
            continue

        # ── Magyar Nyelvtan Tanító parancsok ─────────────────────
        if handle_grammar_commands(stripped):
            log_event("GRAMMAR_CMD", stripped[:100])
            continue

        # ── Smart Model Router parancsok ──────────────────────────
        if handle_router_commands(stripped):
            log_event("ROUTER_CMD", stripped[:100])
            continue

        # ── Plugin hook-ok ──────────────────────────────────────
        if trigger_hook("input", stripped):
            continue

        # ── LLM chat ────────────────────────────────────────────
        topic = get_active_topic()

        log_event("USER_INPUT", stripped[:200])
        save_memory(topic, "user", stripped)

        # Phase A.4: Classify task type (agentic vs. regular)
        task = classify(stripped)
        log_event("CLASSIFY", f"{task.type}, agentic={task.is_agentic}, confidence={task.confidence:.2f}")

        # Phase D.5: Clarification — kérdezz vissza, ha bizonytalan (confidence < 0.6)
        if task.confidence < 0.6 and task.clarification:
            print(f"\033[33m❓ {task.clarification}\033[0m")
            try:
                clarified = get_input("  > ").strip()
                if clarified:
                    stripped = clarified
                    task = classify(stripped)  # Re-classify with clarified input
                    log_event("CLARIFIED", f"original='{stripped[:60]}', new confidence={task.confidence:.2f}")
            except (KeyboardInterrupt, EOFError):
                continue

        if task.is_agentic:
            # Agentic mode: use agent-specific prompt and tool registry
            sys_prompt = build_agent_system_prompt(topic, query=stripped)
            messages: List[Dict] = [{"role": "system", "content": sys_prompt}]
            messages += truncate_history(history)
            messages.append({"role": "user", "content": stripped})
            print(f"\033[92m[agentic→{task.model_hint}]\033[0m ")
            print()
            answer = agent_loop(messages, model=task.model_hint)
        else:
            # Regular mode: use router-based model selection
            from src.router import route
            routed_model, agent_type = route(stripped)
            sys_prompt = build_system_prompt(topic, query=stripped)
            messages: List[Dict] = [{"role": "system", "content": sys_prompt}]
            messages += truncate_history(history)
            messages.append({"role": "user", "content": stripped})
            if agent_type == "code":
                print(f"\033[90m[code→{routed_model}]\033[0m ")
            print()
            answer = agent_loop(messages, model=routed_model)
        print()

        save_memory(topic, "assistant", answer)
        history.append({"role": "user", "content": stripped})
        history.append({"role": "assistant", "content": answer})
        log_event("ASSISTANT_REPLY", answer[:200])

        _save_history()


if __name__ == "__main__":
    main()
