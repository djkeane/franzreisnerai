"""Teljes kódolási ciklus — generálás → futtatás → hibajavítás → retry."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from src.security import log_event

logger = logging.getLogger(__name__)

# Engedélyezett fájl kiterjesztések
ALLOWED_EXTENSIONS = {".py", ".js", ".ts", ".go", ".sh", ".json", ".yaml", ".yml", ".toml", ".md"}

# Tiltott parancsok és minták
FORBIDDEN_PATTERNS = {
    r"rm\s+-rf",
    r"rm\s+-r\s+/",
    r"sudo\s+",
    r"curl\s+[^\s]*\s*\|\s*",
    r"wget\s+[^\s]*\s*\|\s*",
    r"chmod\s+777",
    r"dd\s+if=",
    r":\(\)\s*{\s*:\s*\|\s*:\s*&\s*\};",  # fork bomb
    r"eval\s+",
    r"exec\s+rm",
    r"pkill",
    r"killall",
    r"shutdown",
    r"reboot",
}


def _check_safety(code: str) -> bool:
    """Ellenőrzi, hogy a kód nem tartalmaz veszélyes parancsokat."""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return False
    return True


def _check_file_path(path: Path) -> bool:
    """Ellenőrzi, hogy a fájl kiterjesztése engedélyezett."""
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def run_code(
    filepath: str | Path,
    timeout: int = 30,
    cwd: str | Path = ".",
) -> dict:
    """
    Futtat egy Python vagy shell scriptot.

    Argumentumok:
        filepath: futtatandó fájl (.py, .sh, stb.)
        timeout: maximum futási idő (másodperc)
        cwd: munkakönyvtár

    Visszaadás:
        {"returncode": int, "stdout": str, "stderr": str, "elapsed_ms": float}
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Fájl nem létezik: {filepath}",
            "elapsed_ms": 0,
        }

    if not _check_file_path(filepath):
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Nem engedélyezett kiterjesztés: {filepath.suffix}",
            "elapsed_ms": 0,
        }

    # Végre hajtás
    start = time.time()
    try:
        if filepath.suffix == ".py":
            cmd = ["python3", str(filepath)]
        elif filepath.suffix in {".sh"}:
            cmd = ["bash", str(filepath)]
        else:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Nem támogatott: {filepath.suffix}",
                "elapsed_ms": 0,
            }

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
        elapsed = (time.time() - start) * 1000

        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],  # max 5000 char
            "stderr": result.stderr[:5000],
            "elapsed_ms": elapsed,
        }

    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Timeout után {timeout}s",
            "elapsed_ms": (time.time() - start) * 1000,
        }
    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
            "elapsed_ms": (time.time() - start) * 1000,
        }


def fix_code(
    code: str,
    stderr: str,
    task: str,
    llm_fn: Callable[[str], str],
) -> str:
    """
    Próbálja javítani a kódot a hibamessage alapján.

    Argumentumok:
        code: az eredeti (hibás) kód
        stderr: a futtatási hiba üzenete
        task: az eredeti feladat leírása
        llm_fn: LLM hívás függvény (prompt → válasz)

    Visszaadás:
        javított kód vagy üres string ha nem sikerült
    """
    prompt = f"""A következő kódban hiba van:

FELADAT: {task}

KÓD:
```python
{code}
```

HIBA:
{stderr}

Javítsd meg a kódot. Csak a javított kódot írj ki, magyarázat nélkül."""

    try:
        fixed = llm_fn(prompt)
        # Kód извлечение (``` vagy ```python blokk közül)
        match = re.search(r"```(?:python)?\n(.*?)```", fixed, re.DOTALL)
        if match:
            return match.group(1).strip()
        return fixed.strip()
    except Exception as exc:
        log_event("FIX_CODE_ERROR", str(exc))
        return ""


def coding_loop(
    task: str,
    working_dir: str | Path = ".",
    llm_fn: Callable[[str], str] | None = None,
    max_retries: int = 5,
) -> dict:
    """
    Teljes kódolási ciklus: generálás → futtatás → hibajavítás → retry.

    Argumentumok:
        task: feladat leírása (pl. "írj egy fib(n) függvényt")
        working_dir: munkakönyvtár
        llm_fn: LLM hívás függvény; ha None, a gateway-t használja
        max_retries: maximum próbálkozások száma

    Visszaadás:
        {
            "success": bool,
            "code": str,
            "output": str,
            "iterations": int,
            "log": [...]
        }
    """
    if llm_fn is None:
        from src.llm import llm_gateway
        llm_fn = lambda p: llm_gateway.chat([{"role": "user", "content": p}], task_type="code")

    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    log_entries = []

    # 1. Kód generálás
    gen_prompt = f"""Írj Python kódot az alábbi feladathoz:
{task}

A kódot egy temp fájlba fogom futtatni. Csak a Python kód, magyarázat nélkül."""

    try:
        generated_code = llm_fn(gen_prompt)
        # Kód kikövetkeztetés
        match = re.search(r"```(?:python)?\n(.*?)```", generated_code, re.DOTALL)
        if match:
            generated_code = match.group(1).strip()
    except Exception as exc:
        return {
            "success": False,
            "code": "",
            "output": "",
            "iterations": 0,
            "log": [{"type": "error", "msg": f"Kódgenerálás hiba: {exc}"}],
        }

    # Biztonsági ellenőrzés
    if not _check_safety(generated_code):
        return {
            "success": False,
            "code": "",
            "output": "",
            "iterations": 0,
            "log": [{"type": "security", "msg": "Veszélyes parancs detektálva"}],
        }

    log_entries.append({"type": "generated", "code_len": len(generated_code)})

    # 2. Retry loop
    code = generated_code
    for attempt in range(max_retries):
        # Temp fájl írás
        temp_file = working_dir / f"temp_code_{attempt}.py"
        try:
            temp_file.write_text(code, encoding="utf-8")
        except Exception as exc:
            log_entries.append({"type": "write_error", "msg": str(exc)})
            continue

        # Futtatás
        result = run_code(temp_file, timeout=30, cwd=working_dir)
        log_entries.append({
            "type": "run",
            "attempt": attempt + 1,
            "returncode": result["returncode"],
            "elapsed_ms": result["elapsed_ms"],
        })

        # Siker?
        if result["returncode"] == 0:
            log_event("CODING_SUCCESS", f"{task[:50]} in {attempt + 1} iter")
            return {
                "success": True,
                "code": code,
                "output": result["stdout"],
                "iterations": attempt + 1,
                "log": log_entries,
            }

        # Nem: hiba → fix
        if attempt < max_retries - 1:
            log_entries.append({"type": "fixing"})
            fixed = fix_code(code, result["stderr"], task, llm_fn)
            if fixed and _check_safety(fixed):
                code = fixed
            else:
                log_entries.append({"type": "fix_failed"})
                break

    # Sikertelenség
    log_event("CODING_FAILED", f"{task[:50]} after {max_retries} retries")
    return {
        "success": False,
        "code": code,
        "output": "",
        "iterations": max_retries,
        "log": log_entries,
    }


def generate_project(
    task: str,
    output_dir: str | Path = "./generated",
    llm_fn: Callable[[str], str] | None = None,
) -> dict:
    """
    Több fájlos projekt generálás.
    Az LLM-nek JSON-t kell visszaadnia: {"files": [{"path": "main.py", "content": "..."}]}

    Argumentumok:
        task: projekt feladat leírása
        output_dir: kimenet könyvtár
        llm_fn: LLM függvény

    Visszaadás:
        {"success": bool, "files": int, "paths": [...], "errors": [...]}
    """
    if llm_fn is None:
        from src.llm import llm_gateway
        llm_fn = lambda p: llm_gateway.chat([{"role": "user", "content": p}], task_type="code")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    errors = []

    prompt = f"""Generálj egy teljes Python projektet:
{task}

Válaszolj JSON formátumban (és csak JSON, semmilyen más szöveg):
{{
  "files": [
    {{"path": "main.py", "content": "..."}},
    {{"path": "utils.py", "content": "..."}},
    ...
  ]
}}

Csak létrehozandó fájlokat add meg."""

    try:
        response = llm_fn(prompt)
        # JSON kikövetkeztetés
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            return {
                "success": False,
                "files": 0,
                "paths": [],
                "errors": ["Nincs JSON a válaszban"],
            }

        data = json.loads(match.group(0))
    except (json.JSONDecodeError, Exception) as exc:
        return {
            "success": False,
            "files": 0,
            "paths": [],
            "errors": [f"JSON parse error: {exc}"],
        }

    # Fájlok írása
    paths = []
    for file_obj in data.get("files", []):
        path = Path(file_obj.get("path", ""))
        if not path.name:
            errors.append("Üres fájlnév")
            continue

        if not _check_file_path(path):
            errors.append(f"Nem engedélyezett: {path.suffix}")
            continue

        content = file_obj.get("content", "")
        if not _check_safety(content):
            errors.append(f"Veszélyes tartalom: {path}")
            continue

        try:
            full_path = output_dir / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            paths.append(str(path))
            log_event("FILE_GENERATED", str(path))
        except Exception as exc:
            errors.append(f"Írási hiba {path}: {exc}")

    return {
        "success": len(errors) == 0 and len(paths) > 0,
        "files": len(paths),
        "paths": paths,
        "errors": errors,
    }
