# -*- coding: utf-8 -*-
"""Franz Agent base class – önálló, körkörös import nélkül."""

import os
import configparser
import requests
from typing import List, Dict

_FRANZ_DIR = os.path.expanduser("~/Franz")
_CFG_PATH = os.path.join(_FRANZ_DIR, "franz.cfg")
_config = configparser.ConfigParser()
_config.read(_CFG_PATH)

def _build_url(raw: str) -> str:
    u = raw.strip().rstrip("/")
    return u if u.endswith("/api/chat") else u + "/api/chat"

_OLLAMA_URLS = [
    _build_url(u)
    for u in _config.get("ollama", "url", fallback="http://localhost:11434").split(",")
    if u.strip()
]
_OLLAMA_TIMEOUT = _config.getint("ollama", "timeout", fallback=15)


class BaseAgent:
    def __init__(self, cfg_section: str):
        self.name = cfg_section
        self.display_name = _config.get(cfg_section, "display_name", fallback=cfg_section)
        self.description  = _config.get(cfg_section, "description",  fallback="")
        self.topic_prefix = _config.get(cfg_section, "topic_prefix", fallback=cfg_section.lower() + "_")
        self.model        = _config.get(cfg_section, "model",        fallback="jarvis-hu-coder:latest")
        self.temperature  = _config.getfloat(cfg_section, "temperature", fallback=0.2)

    def system_prompt(self, task: str) -> str:
        raise NotImplementedError

    def chat(self, messages: List[Dict]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        last_err = None
        for url in _OLLAMA_URLS:
            try:
                r = requests.post(url, json=payload, timeout=_OLLAMA_TIMEOUT)
                r.raise_for_status()
                return r.json().get("message", {}).get("content", "[NO RESPONSE]")
            except Exception as e:
                last_err = e
        return f"[AGENT_ERROR] {last_err}"
