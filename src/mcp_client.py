"""
Franz MCP Client — hívja a coding és hungarian MCP szervereket.
Egyszerű JSON-RPC over stdio kliens, mcp csomag nélkül is működik.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from typing import Any

from src.security import log_event

# MCP szerver elérési utak
_SERVERS: dict[str, list[str]] = {
    "coding": [sys.executable, "mcp/coding_server.py"],
    "hungarian": [sys.executable, "mcp/hungarian_server.py"],
}


class McpClient:
    """Egyszerű MCP stdio kliens — egy eszköz meghívásához nyit egy subprocess-t."""

    def __init__(self, server_name: str):
        if server_name not in _SERVERS:
            raise ValueError(f"Ismeretlen MCP szerver: {server_name}. Elérhető: {list(_SERVERS)}")
        self.server_name = server_name
        self.cmd = _SERVERS[server_name]
        self._proc: subprocess.Popen | None = None
        self._req_id = 0

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send(self, method: str, params: dict | None = None) -> dict:
        """JSON-RPC kérés küldése és válasz olvasása."""
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        line = json.dumps(msg) + "\n"
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(line.encode())
        self._proc.stdin.flush()

        # Válasz olvasása
        assert self._proc.stdout
        raw = self._proc.stdout.readline()
        if not raw:
            raise ConnectionError(f"MCP szerver ({self.server_name}) nem válaszolt.")
        return json.loads(raw)

    def __enter__(self) -> "McpClient":
        self._proc = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=__import__("pathlib").Path(__file__).parent.parent,
        )
        # Initialize handshake
        resp = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "franz", "version": "5.0"},
        })
        if "error" in resp:
            raise RuntimeError(f"MCP init hiba: {resp['error']}")
        # initialized notification
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        assert self._proc.stdin
        self._proc.stdin.write((json.dumps(notif) + "\n").encode())
        self._proc.stdin.flush()
        log_event("MCP_CONNECT", self.server_name)
        return self

    def __exit__(self, *_: Any) -> None:
        if self._proc:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
        self._proc = None

    def call(self, tool_name: str, arguments: dict) -> str:
        """Egy MCP eszköz meghívása. Visszaadja a szöveges eredményt."""
        resp = self._send("tools/call", {"name": tool_name, "arguments": arguments})
        if "error" in resp:
            return f"[MCP HIBA] {resp['error'].get('message', resp['error'])}"
        content = resp.get("result", {}).get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts) or "(üres válasz)"

    def list_tools(self) -> list[dict]:
        """Elérhető eszközök listája."""
        resp = self._send("tools/list", {})
        if "error" in resp:
            return []
        return resp.get("result", {}).get("tools", [])


def call_mcp(server: str, tool: str, **kwargs: Any) -> str:
    """
    Gyors egyszerű hívás: kontextusmenedzser nélkül.

    Példa:
        result = call_mcp("coding", "syntax_check", code="def foo(:\n  pass")
        result = call_mcp("hungarian", "spell_check", text="Ez egy mondat")
    """
    try:
        with McpClient(server) as client:
            return client.call(tool, kwargs)
    except Exception as e:
        log_event("MCP_ERROR", f"{server}.{tool}: {e}")
        return f"[MCP HIBA] {e}"
