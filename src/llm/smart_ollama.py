"""Smart Ollama Wrapper — timeout handling + intelligent fallback."""

from __future__ import annotations

import subprocess
import time
import json
from typing import Optional, Iterator
import threading

from src.model_router import (
    get_best_model,
    get_fallback_chain,
    check_model_timeout,
    record_model_response,
    report_model_failure,
)
from src.security import log_event

# ═══════════════════════════════════════════════════════════════════════════════
# SMART OLLAMA WRAPPER — Timeout + Intelligent Fallback
# ═══════════════════════════════════════════════════════════════════════════════

import os as _os
import configparser as _cp

def _load_ollama_config() -> tuple[list[str], int, int]:
    """franz.cfg [ollama] szekciójából olvassa az URL-eket és timeoutokat."""
    cfg = _cp.ConfigParser()
    _cfg_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "franz.cfg")
    cfg.read(_cfg_path)
    urls_raw = cfg.get("ollama", "url", fallback="http://localhost:11434")
    urls = [u.strip() for u in urls_raw.split(",") if u.strip()]
    timeout = cfg.getint("ollama", "timeout", fallback=180)
    first_token = cfg.getint("ollama", "first_token_timeout", fallback=60)
    return urls, timeout, first_token

_OLLAMA_URLS_CFG, _TIMEOUT_CFG, _FIRST_TOKEN_CFG = _load_ollama_config()

OLLAMA_URLS = _OLLAMA_URLS_CFG
DEFAULT_TIMEOUT = _TIMEOUT_CFG        # franz.cfg-ből: 180s
FIRST_TOKEN_TIMEOUT = _FIRST_TOKEN_CFG  # franz.cfg-ből: 60s


class SmartOllamaClient:
    """
    Okos Ollama kliens timeout kezeléssel és fallback logikával.

    Tulajdonságok:
    - 45 másodperces timeout limit
    - Automatikus fallback más modellekre
    - Válaszidő nyomon követése
    - Modellek teljesítménye alapján dinamikus választás
    """

    def __init__(self):
        self.timeout = DEFAULT_TIMEOUT
        self.current_model: Optional[str] = None
        self.current_url: Optional[str] = None

    def _find_available_url(self) -> Optional[str]:
        """Elérhető Ollama szerver keresése."""
        for url in OLLAMA_URLS:
            try:
                result = subprocess.run(
                    ["curl", "-s", f"{url}/api/tags"],
                    capture_output=True,
                    timeout=3,
                    text=True
                )
                if result.returncode == 0:
                    return url
            except Exception:
                continue
        return None

    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        task_type: str = "general",
        stream: bool = True,
        timeout: Optional[int] = None,
    ) -> Optional[str] | Iterator[str]:
        """
        Okos chat hívás timeout és fallback kezeléssel.

        Args:
            messages: Chat üzenetek
            model: Modell neve (ha None, automatikus választás)
            task_type: Feladat típusa ("code", "general", "hungarian", etc)
            stream: Streamelés engedélyezése
            timeout: Timeout másodpercben (alapértelmezés: 45s)

        Returns:
            Teljes válasz vagy stream iterator
        """
        timeout = timeout or self.timeout
        url = self._find_available_url()

        if not url:
            log_event("OLLAMA_ERROR", "Nincs elérhető Ollama szerver")
            return None

        # Automatikus modellválasztás
        if not model:
            model = get_best_model(task_type)
            log_event("MODEL_SELECT", f"{model} (task: {task_type})")

        # Fallback lánc
        fallback_models = get_fallback_chain(task_type)
        models_to_try = [model] + [m for m in fallback_models if m != model]

        for attempt, try_model in enumerate(models_to_try):
            log_event("MODEL_TRY", f"Attempt {attempt + 1}: {try_model}")

            start_time = time.time()
            try:
                if stream:
                    result = self._chat_stream_with_timeout(
                        url, try_model, messages, timeout
                    )
                    elapsed = time.time() - start_time

                    if check_model_timeout(try_model, elapsed):
                        log_event(
                            "MODEL_TIMEOUT",
                            f"{try_model}: {elapsed:.1f}s > {timeout}s"
                        )
                        report_model_failure(try_model)
                        continue  # Try next model

                    record_model_response(try_model, elapsed)
                    self.current_model = try_model
                    return result

                else:
                    result = self._chat_blocking(url, try_model, messages, timeout)
                    elapsed = time.time() - start_time

                    if check_model_timeout(try_model, elapsed):
                        log_event(
                            "MODEL_TIMEOUT",
                            f"{try_model}: {elapsed:.1f}s > {timeout}s"
                        )
                        report_model_failure(try_model)
                        continue

                    record_model_response(try_model, elapsed)
                    self.current_model = try_model
                    return result

            except subprocess.TimeoutExpired:
                elapsed = time.time() - start_time
                log_event("MODEL_TIMEOUT", f"{try_model}: hard timeout at {elapsed:.1f}s")
                report_model_failure(try_model)
                continue

            except Exception as exc:
                log_event("MODEL_ERROR", f"{try_model}: {exc}")
                report_model_failure(try_model)
                continue

        # Ha minden modell meghiúsult
        log_event("ALL_MODELS_FAILED", f"Fallback lánc kimerült: {models_to_try}")
        return None

    def _chat_blocking(
        self,
        url: str,
        model: str,
        messages: list[dict],
        timeout: int
    ) -> Optional[str]:
        """Blokkoló chat hívás timeout-tal."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        try:
            result = subprocess.run(
                [
                    "curl", "-s", "-X", "POST",
                    f"{url}/api/chat",
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(payload),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                response_data = json.loads(result.stdout)
                return response_data.get("message", {}).get("content", "")
            else:
                return None

        except subprocess.TimeoutExpired:
            raise
        except Exception as exc:
            raise

    def _chat_stream_with_timeout(
        self,
        url: str,
        model: str,
        messages: list[dict],
        timeout: int
    ) -> Iterator[str]:
        """Stream chat hívás timeout-tal."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        start_time = time.time()
        last_token_time = start_time
        first_token_timeout = FIRST_TOKEN_TIMEOUT  # franz.cfg-ből: 60s

        try:
            proc = subprocess.Popen(
                [
                    "curl", "-s", "-X", "POST",
                    f"{url}/api/chat",
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(payload),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            for line in iter(proc.stdout.readline, ""):
                current_time = time.time()

                # Timeout ellenőrzés
                if current_time - start_time > timeout:
                    proc.kill()
                    raise subprocess.TimeoutExpired("curl", timeout)

                # Első token timeout
                if line.strip() and current_time - start_time > first_token_timeout:
                    if current_time - last_token_time > 30:
                        proc.kill()
                        raise subprocess.TimeoutExpired("curl", 30)

                if line.strip():
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                            last_token_time = current_time
                    except json.JSONDecodeError:
                        continue

            proc.wait(timeout=5)

        except subprocess.TimeoutExpired:
            raise
        except Exception as exc:
            raise

    def get_model_status(self) -> str:
        """Modellek státusza."""
        from src.model_router import get_router_status
        return get_router_status()


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBÁLIS KLIENS INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

smart_ollama = SmartOllamaClient()


# ═══════════════════════════════════════════════════════════════════════════════
# NYILVÁNOS API
# ═══════════════════════════════════════════════════════════════════════════════

def smart_chat(
    messages: list[dict],
    model: Optional[str] = None,
    task_type: str = "general",
    stream: bool = True,
    timeout: Optional[int] = None,
) -> Optional[str] | Iterator[str]:
    """Okos chat hívás intelligens fallback-kal."""
    return smart_ollama.chat(messages, model, task_type, stream, timeout)


def get_smart_model_status() -> str:
    """Modellek és router státusza."""
    return smart_ollama.get_model_status()
