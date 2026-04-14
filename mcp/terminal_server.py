#!/usr/bin/env python3
"""Franz Terminal MCP Server — sandboxed command execution."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: mcp library not found. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Engedélyezett parancsok — whitelist
ALLOWED_COMMANDS = {
    "ls", "pwd", "cat", "head", "tail", "grep", "find",
    "git", "python", "python3", "pip", "pip3", "ollama",
    "echo", "wc", "file", "stat", "du",
}

# Tiltott minták — regex
FORBIDDEN_PATTERNS = {
    r"rm\s+",
    r"sudo\s+",
    r"curl\s+.*\|",
    r"wget\s+.*\|",
    r"chmod\s+",
    r"chown\s+",
    r"dd\s+if=",
    r"shutdown",
    r"reboot",
    r"pkill",
    r"killall",
    r"eval",
    r"exec\s+rm",
}

server = Server("franz-terminal")


def _check_safety(cmd: str) -> bool:
    """Ellenőrzi, hogy a parancs biztonságos-e."""
    # Alapparancs ellenőrzés
    base_cmd = cmd.split()[0] if cmd.split() else ""
    if base_cmd not in ALLOWED_COMMANDS:
        return False

    # Tiltott minták
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False

    return True


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Elérhető MCP tools."""
    return [
        Tool(
            name="run_command",
            description="Terminál parancs futtatása (whitelist-en alapul)",
            inputSchema={
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "Futtatandó parancs (pl. 'ls -la', 'python script.py')",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Munkakönyvtár (default: '.')",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout másodpercben (default: 30)",
                    },
                },
                "required": ["cmd"],
            },
        ),
        Tool(
            name="read_file",
            description="Fájl olvasása",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Fájl elérési útja",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="write_file",
            description="Fájl írása (új vagy felülírás)",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Fájl elérési útja",
                    },
                    "content": {
                        "type": "string",
                        "description": "Fájl tartalma",
                    },
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="list_directory",
            description="Könyvtár tartalmának listázása",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Könyvtár elérési útja (default: '.')",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """MCP tool hívás feldolgozása."""

    try:
        if name == "run_command":
            return await _run_command(arguments)
        elif name == "read_file":
            return await _read_file(arguments)
        elif name == "write_file":
            return await _write_file(arguments)
        elif name == "list_directory":
            return await _list_directory(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _run_command(args: dict) -> list[TextContent]:
    """Parancs futtatása."""
    cmd = args.get("cmd", "").strip()
    working_dir = args.get("working_dir", ".")
    timeout = args.get("timeout", 30)

    if not cmd:
        return [TextContent(type="text", text="Error: empty command")]

    # Biztonsági ellenőrzés
    if not _check_safety(cmd):
        return [TextContent(type="text", text="Error: forbidden command or pattern")]

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )

        output = f"Exit code: {result.returncode}\n\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        return [TextContent(type="text", text=output)]

    except subprocess.TimeoutExpired:
        return [TextContent(type="text", text=f"Error: command timeout after {timeout}s")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _read_file(args: dict) -> list[TextContent]:
    """Fájl olvasása."""
    path = args.get("path", "").strip()

    if not path:
        return [TextContent(type="text", text="Error: empty path")]

    try:
        p = Path(path).resolve()

        # Biztonsági ellenőrzés: ne lehessen /etc-t, /root-ot stb. olvasni
        # (Egyszerű check: ha /Users-ben van, OK; ha /tmp-ben, OK; egyébként kötött)
        allowed_roots = {Path.home(), Path("/tmp"), Path("/var/tmp")}
        if not any(str(p).startswith(str(root)) for root in allowed_roots):
            # Csak ha nem root-nál vagy rendszer dirban
            if str(p).startswith("/etc") or str(p).startswith("/root"):
                return [TextContent(type="text", text="Error: access denied")]

        content = p.read_text(encoding="utf-8")
        return [TextContent(type="text", text=content[:50000])]  # max 50KB

    except FileNotFoundError:
        return [TextContent(type="text", text=f"Error: file not found: {path}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _write_file(args: dict) -> list[TextContent]:
    """Fájl írása."""
    path = args.get("path", "").strip()
    content = args.get("content", "")

    if not path:
        return [TextContent(type="text", text="Error: empty path")]

    try:
        p = Path(path).resolve()

        # Biztonsági ellenőrzés: csak home dir-ben írható
        if not str(p).startswith(str(Path.home())):
            return [TextContent(type="text", text="Error: can only write in home directory")]

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return [TextContent(type="text", text=f"OK: written {len(content)} bytes to {p}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _list_directory(args: dict) -> list[TextContent]:
    """Könyvtár listázása."""
    path = args.get("path", ".").strip()

    try:
        p = Path(path).resolve()

        if not p.is_dir():
            return [TextContent(type="text", text=f"Error: not a directory: {path}")]

        items = sorted(p.iterdir())
        lines = []
        for item in items:
            if item.is_dir():
                lines.append(f"📁 {item.name}/")
            else:
                lines.append(f"📄 {item.name}")

        return [TextContent(type="text", text="\n".join(lines))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def main():
    """MCP server indítása."""
    async with server:
        print("Franz Terminal MCP Server running on stdio", file=sys.stderr)
        await server.wait_forever()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
