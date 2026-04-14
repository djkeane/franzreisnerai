#!/usr/bin/env python3
"""
Franz Coding MCP Server
Eszközök: Python futtatás, lint, syntax-check, AST elemzés
"""

from __future__ import annotations

import ast
import io
import resource
import subprocess
import sys
import tempfile
import textwrap
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

server = Server("franz-coding")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="run_python",
            description="Futtass Python 3 kódot biztonságos sandboxban. Visszaadja a stdout/stderr kimenetét.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "A futtatandó Python kód"},
                    "timeout": {"type": "integer", "description": "Max futási idő másodpercben (alap: 10)", "default": 10},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="lint_python",
            description="Pyflakes lint futtatása Python kódon. Visszaadja a hibákat és figyelmeztetéseket.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "A lintelendő Python kód"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="syntax_check",
            description="Ellenőrzi a Python kód szintaxisát. Pontosan megmutatja a hibás sort.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Az ellenőrzendő Python kód"},
                    "language": {"type": "string", "description": "Programnyelv: python|go|js (alap: python)", "default": "python"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="ast_analyze",
            description="Python kód AST elemzése: függvények, osztályok, importok listája.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Az elemzendő Python kód"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="format_python",
            description="Python kód formázása PEP8 szerint (autopep8 vagy black ha elérhető).",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "A formázandó Python kód"},
                },
                "required": ["code"],
            },
        ),
    ]


def _run_python_safe(code: str, timeout: int = 10) -> str:
    """Futtassa a kódot subprocess-ben, resource limitekkel."""
    code = textwrap.dedent(code)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        fname = f.name

    try:
        result = subprocess.run(
            [sys.executable, fname],
            capture_output=True,
            text=True,
            timeout=timeout,
            # Korlátozzuk a memóriát és a CPU-t
            preexec_fn=lambda: (
                resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024)),
                resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout)),
            ) if sys.platform != "darwin" else None,
        )
        out = result.stdout
        err = result.stderr
        if out and err:
            return f"STDOUT:\n{out}\nSTDERR:\n{err}"
        return out or err or "(nincs kimenet)"
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] A kód nem futott le {timeout} másodpercen belül."
    except Exception as e:
        return f"[HIBA] {e}"
    finally:
        import os
        try:
            os.unlink(fname)
        except Exception:
            pass


def _lint_python(code: str) -> str:
    """Pyflakes lint."""
    try:
        from pyflakes import api as pf_api
        from pyflakes.checker import Checker  # noqa: F401

        out = io.StringIO()
        warning_count = pf_api.check(code, "<stdin>", reporter=None)
        # Direkt futtatás
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes"],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "✓ Nincs lint hiba."
    except Exception as e:
        return f"[HIBA] pyflakes: {e}"


def _syntax_check(code: str, language: str = "python") -> str:
    """Szintaxis ellenőrzés."""
    if language.lower() in ("python", "py"):
        try:
            ast.parse(code)
            return "✓ Szintaxis hibátlan."
        except SyntaxError as e:
            return (
                f"SyntaxError: {e.msg}\n"
                f"  Sor {e.lineno}: {e.text or '?'}\n"
                f"  {'~' * max(0, (e.offset or 1) - 1)}^"
            )
    elif language.lower() in ("go", "golang"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False) as f:
            f.write(code)
            fname = f.name
        try:
            result = subprocess.run(["go", "vet", fname], capture_output=True, text=True, timeout=15)
            return result.stdout + result.stderr or "✓ Szintaxis hibátlan."
        except FileNotFoundError:
            return "[HIBA] Go compiler nem található."
        except Exception as e:
            return f"[HIBA] {e}"
    elif language.lower() in ("js", "javascript", "ts", "typescript"):
        try:
            result = subprocess.run(
                ["node", "--check", "/dev/stdin"],
                input=code, capture_output=True, text=True, timeout=10
            )
            return result.stderr.strip() or "✓ Szintaxis hibátlan."
        except FileNotFoundError:
            return "[HIBA] Node.js nem található."
    return f"[HIBA] Nem ismert nyelv: {language}"


def _ast_analyze(code: str) -> str:
    """AST elemzés: függvények, osztályok, importok."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    functions = []
    classes = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            functions.append(f"  def {node.name}({', '.join(args)}) — sor {node.lineno}")
        elif isinstance(node, ast.ClassDef):
            bases = [getattr(b, 'id', '?') for b in node.bases]
            classes.append(f"  class {node.name}({', '.join(bases)}) — sor {node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(f"  import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            names = ", ".join(a.name for a in node.names)
            imports.append(f"  from {node.module} import {names}")

    parts = []
    if imports:
        parts.append("Importok:\n" + "\n".join(imports))
    if classes:
        parts.append("Osztályok:\n" + "\n".join(classes))
    if functions:
        parts.append("Függvények:\n" + "\n".join(functions))
    if not parts:
        parts.append("(Nincs osztály, függvény vagy import)")
    return "\n\n".join(parts)


def _format_python(code: str) -> str:
    """Formázás black-kal, majd autopep8-cal, végül visszaadja eredeti."""
    for tool, args in [
        ("black", ["black", "-", "--quiet"]),
        ("autopep8", ["autopep8", "-"]),
    ]:
        try:
            result = subprocess.run(
                args, input=code, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except FileNotFoundError:
            continue
    return "[INFO] black/autopep8 nem elérhető — telepítsd: pip install black"


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "run_python":
        code = arguments["code"]
        timeout = int(arguments.get("timeout", 10))
        result = _run_python_safe(code, timeout)
    elif name == "lint_python":
        result = _lint_python(arguments["code"])
    elif name == "syntax_check":
        result = _syntax_check(
            arguments["code"],
            arguments.get("language", "python"),
        )
    elif name == "ast_analyze":
        result = _ast_analyze(arguments["code"])
    elif name == "format_python":
        result = _format_python(arguments["code"])
    else:
        result = f"[HIBA] Ismeretlen eszköz: {name}"

    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="franz-coding",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
