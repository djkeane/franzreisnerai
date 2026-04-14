"""
LLM Gateway — intelligens routing, failover, cache, token számláló.

Prioritás:
  1. Groq        (gyors, kód)
  2. Gemini      (HU szöveg, hosszú kontextus)
  3. OpenRouter  (fallback)
  4. Ollama      (offline fallback)
"""

from __future__ import annotations

import os
import time
from typing import Iterator

from src.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from src.llm.cache import LLMCache
from src.llm.gemini import GeminiClient
from src.llm.groq_client import GroqClient
from src.llm.openrouter import OpenRouterClient
from src.security import log_event
from src.reasoning.chain_of_thought import enhance_prompt_with_reasoning

# Napi token számláló (memóriában — újraindításkor reset)
_daily_tokens: dict[str, int] = {"total": 0, "date": ""}


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _count_tokens(text: str) -> int:
    """Durva token becslés: ~4 karakter = 1 token."""
    return max(len(text) // 4, 1)


class LLMGateway:
    """
    Egységes belépési pont minden LLM híváshoz.

    Routing stratégia feladat típus szerint:
      code     → Groq → OpenRouter → Ollama
      hungarian → Gemini → OpenRouter → Ollama
      research  → OpenRouter → Gemini → Ollama
      general   → Gemini → Groq → OpenRouter → Ollama
    """

    # Feladattípus → preferált provider sorrend
    _ROUTING: dict[str, list[str]] = {
        "code":      ["groq", "openrouter", "ollama"],
        "hungarian": ["gemini", "openrouter", "ollama"],
        "research":  ["openrouter", "gemini", "ollama"],
        "planner":   ["gemini", "openrouter", "ollama"],
        "verifier":  ["groq", "ollama"],
        "general":   ["gemini", "groq", "openrouter", "ollama"],
        "system":    ["groq", "gemini", "ollama"],
    }

    def _classify_task(self, messages: list[dict]) -> str:
        """
        Intelligens feladat-osztályozás a prompt alapján.
        Multi-signal heurisztika: szavak, karakterek, pattern-ek.
        """
        if not messages:
            return "general"

        last_msg = messages[-1].get("content", "").lower()
        combined_context = " ".join([m.get("content", "").lower() for m in messages[-3:]])

        # Kiterjesztett kódolás kulcsszavak (verifikáció, tesztelés nélkül)
        code_keywords = [
            "python", "javascript", "typescript", "rust", "go", "java", "c++", "c#",
            "kód ", " kód", "függvény", "class ", "class:", "api ", "script", "refaktor",
            "fix bug", "hiba javítás", "import ", "def ", "return ", "async", "await",
            "docker", "kubernetes", "sql", "database", "api endpoint", "algoritmus"
        ]
        # Kutatás/Elemzés
        research_keywords = [
            "keress", "research", "browse", "github", "reddit", "elemzés", "audit",
            "dokumentáció", "összehasonlít", "analiz", "tanulmány", "cikk", "forrás"
        ]
        # Tervezés/Architektúra
        planner_keywords = [
            "terv", "lépések", "hogyan kezdjem", "architektúra", "design", "workflow",
            "stratégia", "folyamat", "megközelítés", "módszer", "fázis"
        ]
        # Ellenőrzés/Verifikáció
        verifier_keywords = [
            "tesztelj", "ellenőrizd", "működik", "verify", "check", "hiba?", "audit",
            "tesztel", "unit test", "validiráció", "működésképes"
        ]

        # Pontozás per kategória
        score = {
            "verifier": sum(1 for kw in verifier_keywords if kw in last_msg),
            "planner": sum(1 for kw in planner_keywords if kw in last_msg),
            "code": sum(1 for kw in code_keywords if kw in last_msg),
            "research": sum(1 for kw in research_keywords if kw in last_msg),
        }

        # Legmagasabb pontszám nyer
        best_match = max(score.items(), key=lambda x: x[1])
        if best_match[1] >= 2:
            return best_match[0]

        # Magyar nyelv detektálás — fallback
        hu_chars = "áéíóöőúüű"
        hu_count = sum(1 for char in last_msg if char in hu_chars)
        is_hungarian = hu_count > 3 or any(kw in last_msg for kw in ["szia", "hogy vagy", "segíts", "szükségem van"])

        if is_hungarian:
            return "hungarian"

        return "general"

    def __init__(self) -> None:
        # .env betöltése ha még nem történt meg
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self._clients: dict[str, BaseLLMClient] = {}
        self._cache = LLMCache(
            cache_dir=os.getenv("CACHE_DIR", ".cache"),
            ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
        )
        self._max_daily_tokens = int(os.getenv("MAX_TOKENS_PER_DAY", "100000"))
        self._init_clients()

    def _init_clients(self) -> None:
        """Elérhető kliensek inicializálása."""
        candidates = {
            "groq":        GroqClient(),
            "gemini":      GeminiClient(),
            "openrouter":  OpenRouterClient(),
        }
        for name, client in candidates.items():
            if client.is_available():
                self._clients[name] = client
                log_event("LLM_READY", f"{name} ✓")
            else:
                log_event("LLM_SKIP", f"{name} — nincs API kulcs")

        # Ollama mindig elérhető (helyi)
        try:
            from src.llm.ollama_adapter import OllamaClient
            self._clients["ollama"] = OllamaClient()
            log_event("LLM_READY", "ollama ✓ (offline)")
        except Exception:
            pass

        if not self._clients:
            log_event("LLM_WARN", "Nincs elérhető LLM! Ellenőrizd a .env fájlt.")

    def _check_daily_limit(self, estimated_tokens: int) -> bool:
        """Napi token limit ellenőrzése."""
        global _daily_tokens
        today = _today()
        if _daily_tokens["date"] != today:
            _daily_tokens = {"total": 0, "date": today}
        if _daily_tokens["total"] + estimated_tokens > self._max_daily_tokens:
            log_event("TOKEN_LIMIT", f"Napi limit elérve: {_daily_tokens['total']}")
            return False
        return True

    def _update_token_count(self, tokens: int) -> None:
        global _daily_tokens
        _daily_tokens["total"] = _daily_tokens.get("total", 0) + tokens

    def chat(
        self,
        messages: list[dict],
        task_type: str = "auto",
        system: str = "",
        temperature: float = None,
        max_tokens: int = None,
        use_cache: bool = True,
    ) -> str:
        """
        Fő belépési pont — routing + failover + cache + reasoning.
        Visszaadja a szöveges választ.
        """
        # Automatikus routing ha nincs explicit megadva
        if task_type == "auto":
            task_type = self._classify_task(messages)
            log_event("SMART_ROUTING", f"Classified as: {task_type}")

        # Feladat-specifikus paraméter tuning
        if temperature is None:
            temperature = {
                "code": 0.2,          # Pontosság: kód deterministikus
                "verifier": 0.1,      # Ultra pontosság: ellenőrzés
                "planner": 0.4,       # Kreativitás: tervezéshez
                "research": 0.3,      # Kiegyensúlyozott: kutatás
                "hungarian": 0.35,    # Normál: magyar szöveg
                "general": 0.4,       # Normál: általános chat
                "system": 0.1,        # Ultra pontosság: rendszer
            }.get(task_type, 0.3)

        if max_tokens is None:
            max_tokens = {
                "code": 3000,         # Bővebb kódhoz
                "verifier": 1024,     # Rövid validáció
                "planner": 2048,      # Részletes terv
                "research": 2500,     # Hosszú kutatás
                "hungarian": 2048,    # Normál
                "general": 2048,      # Normál
                "system": 1024,       # Rövid
            }.get(task_type, 2048)

        # Cache ellenőrzés
        if use_cache:
            cached = self._cache.get(messages, task_type)
            if cached:
                log_event("CACHE_HIT", f"{task_type}")
                return cached

        # Érvelési motor integrálása kód-feladatokhoz
        if task_type == "code" and messages:
            user_content = messages[-1].get("content", "")
            # Csak ha nem kér már explicit érvelést
            if "gondolkozz" not in user_content.lower() and "reason" not in user_content.lower():
                enhanced = enhance_prompt_with_reasoning(user_content, include_reasoning=True)
                messages = messages[:-1] + [{"role": "user", "content": enhanced}]
                log_event("REASONING_INJECTED", f"Code task enhanced with chain-of-thought")

        request = LLMRequest(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            task_type=task_type,
        )

        # Token limit
        est = _count_tokens(system + " ".join(m.get("content", "") for m in messages))
        if not self._check_daily_limit(est):
            return "[KORLÁT] Napi token limit elérve. Holnap folytatódik."

        # Provider sorrend a feladattípus alapján
        providers = self._ROUTING.get(task_type, self._ROUTING["general"])

        last_error: Exception | None = None
        for provider in providers:
            client = self._clients.get(provider)
            if client is None:
                continue
            try:
                resp = client.chat(request)
                self._update_token_count(resp.total_tokens)
                if use_cache:
                    self._cache.set(messages, task_type, resp.text)
                log_event("GATEWAY_OK", f"{provider} → {resp.total_tokens}t, {resp.latency_ms:.0f}ms")
                return resp.text
            except Exception as exc:
                log_event("GATEWAY_FAIL", f"{provider}: {exc}")
                last_error = exc
                continue

        # Minden provider megbukott
        err_msg = f"[HIBA] Minden LLM elérhetetlen. Utolsó hiba: {last_error}"
        log_event("GATEWAY_DEAD", err_msg)
        return err_msg

    def stream(
        self,
        messages: list[dict],
        task_type: str = "auto",
        system: str = "",
        temperature: float = None,
        max_tokens: int = None,
    ) -> Iterator[str]:
        """Streaming chat — szövegrészleteket yield-el + érvelés."""
        if task_type == "auto":
            task_type = self._classify_task(messages)
            log_event("SMART_ROUTING", f"Stream classified as: {task_type}")

        # Paraméter tuning (azonos, mint chat)
        if temperature is None:
            temperature = {
                "code": 0.2, "verifier": 0.1, "planner": 0.4, "research": 0.3,
                "hungarian": 0.35, "general": 0.4, "system": 0.1,
            }.get(task_type, 0.3)

        if max_tokens is None:
            max_tokens = {
                "code": 3000, "verifier": 1024, "planner": 2048, "research": 2500,
                "hungarian": 2048, "general": 2048, "system": 1024,
            }.get(task_type, 2048)

        # Érvelés injektálása kód-taskokhoz
        if task_type == "code" and messages:
            user_content = messages[-1].get("content", "")
            if "gondolkozz" not in user_content.lower():
                enhanced = enhance_prompt_with_reasoning(user_content, include_reasoning=True)
                messages = messages[:-1] + [{"role": "user", "content": enhanced}]

        request = LLMRequest(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            task_type=task_type,
            stream=True,
        )

        providers = self._ROUTING.get(task_type, self._ROUTING["general"])
        for provider in providers:
            client = self._clients.get(provider)
            if client is None:
                continue
            try:
                yield from client.stream(request)
                return
            except Exception as exc:
                log_event("STREAM_FAIL", f"{provider}: {exc}")
                continue

        yield "[HIBA] Nincs elérhető streaming LLM."

    def available_providers(self) -> list[str]:
        """Elérhető LLM providerek listája."""
        return list(self._clients.keys())

    def token_usage(self) -> dict:
        """Mai token felhasználás."""
        return {
            "mai_tokenek": _daily_tokens.get("total", 0),
            "napi_limit": self._max_daily_tokens,
            "maradék": self._max_daily_tokens - _daily_tokens.get("total", 0),
            "cache": self._cache.stats(),
        }


# Singleton — az egész Franz ezt használja
llm_gateway = LLMGateway()
