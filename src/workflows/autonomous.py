"""Autonóm loop vezérlő — szokás tanulás és önfejlődés."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from src.learn import bake, list_knowledge
from src.security import log_event
from src.workflows.auto_learn import auto_learn


class AutonomousLoop:
    """
    Háttér thread autonóm tanulásra.

    Periodikusan:
    1. Kiválaszt egy témát
    2. auto_learn() hívás
    3. Ha új tények > 3: bake() hívás (Modelfile frissítés)
    """

    def __init__(
        self,
        state_file: str = "memory/autonomous_state.json",
        interval_sec: int = 3600,  # 1 óra
    ) -> None:
        self._state_file = Path(state_file)
        self._interval_sec = interval_sec
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._load_state()

    # ── Állapot ───────────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        """Tölti az autonóm loop állapotát."""
        if self._state_file.is_file():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                self._iterations_today = data.get("iterations_today", 0)
                self._api_calls_today = data.get("api_calls_today", 0)
                self._last_update = data.get("last_update", 0)
                self._topics_learned = data.get("topics_learned", [])
            except Exception:
                self._init_state()
        else:
            self._init_state()

    def _init_state(self) -> None:
        self._iterations_today = 0
        self._api_calls_today = 0
        self._last_update = time.time()
        self._topics_learned = []

    def _save_state(self) -> None:
        """Mentés az állapotfájlba."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "iterations_today": self._iterations_today,
            "api_calls_today": self._api_calls_today,
            "last_update": self._last_update,
            "topics_learned": self._topics_learned,
        }
        try:
            self._state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _reset_daily(self) -> None:
        """Napi limit reset."""
        today = time.time() // 86400
        last_day = self._last_update // 86400
        if today != last_day:
            self._iterations_today = 0
            self._api_calls_today = 0
            self._last_update = time.time()

    # ── Loop logika ────────────────────────────────────────────────────────────

    def _tick(self) -> bool:
        """
        Egy iteráció: topic kiválasztás → auto_learn → bake ha új tények.
        Visszaadás: True ha sikeres volt, False ha hiba vagy limit.
        """
        with self._lock:
            self._reset_daily()

            # Limit ellenőrzés
            if self._iterations_today >= 10:
                log_event("AUTONOMOUS_DAILY_LIMIT", "10 iter/nap limit")
                return False
            if self._api_calls_today >= 50:
                log_event("AUTONOMOUS_API_LIMIT", "50 hívás/nap limit")
                return False

            # Téma kiválasztás: a tudásbázisból véletlenül vagy a legrégebben frissített
            try:
                knowledge = list_knowledge()
                if not knowledge:
                    log_event("AUTONOMOUS_NO_KNOWLEDGE", "Üres KB")
                    return False

                # Egyszerű stratégia: utolsó tény
                topic = knowledge[-1]["key"] if knowledge else "python"
            except Exception as exc:
                log_event("AUTONOMOUS_KB_ERROR", str(exc))
                return False

            # auto_learn hívás
            try:
                stored = auto_learn(topic)
                self._api_calls_today += 1

                if stored > 3:
                    # Bake: Modelfile frissítés
                    try:
                        bake(max_facts=10)
                        log_event("AUTONOMOUS_BAKED", f"{topic}: {stored} új tény")
                    except Exception as exc:
                        log_event("AUTONOMOUS_BAKE_ERROR", str(exc))

                self._iterations_today += 1
                self._topics_learned.append({"topic": topic, "facts": stored})
                self._save_state()
                log_event("AUTONOMOUS_TICK", f"{topic} → {stored} facts")
                return True

            except Exception as exc:
                log_event("AUTONOMOUS_LEARN_ERROR", str(exc))
                self._api_calls_today += 1
                return False

    def _run(self) -> None:
        """Háttér thread main loop."""
        log_event("AUTONOMOUS_STARTED", f"interval={self._interval_sec}s")
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                log_event("AUTONOMOUS_TICK_CRASH", str(exc))
            time.sleep(self._interval_sec)
        log_event("AUTONOMOUS_STOPPED", "")

    # ── Vezérlés ───────────────────────────────────────────────────────────────

    def start(self, interval_sec: int | None = None) -> None:
        """Háttér thread indítása."""
        with self._lock:
            if self._running:
                log_event("AUTONOMOUS_ALREADY_RUNNING", "")
                return
            if interval_sec:
                self._interval_sec = interval_sec
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Háttér thread leállítása."""
        with self._lock:
            self._running = False
            self._save_state()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def status(self) -> dict[str, Any]:
        """Állapot query."""
        with self._lock:
            self._reset_daily()
            return {
                "running": self._running,
                "iterations_today": self._iterations_today,
                "api_calls_today": self._api_calls_today,
                "topics_learned": len(self._topics_learned),
                "last_topics": self._topics_learned[-5:],
            }

    def __del__(self) -> None:
        """Cleanup: szálat le kell állítani."""
        if self._running:
            self.stop()


# Singleton instance
_autonomous: AutonomousLoop | None = None


def get_autonomous() -> AutonomousLoop:
    """Singleton getter."""
    global _autonomous
    if _autonomous is None:
        _autonomous = AutonomousLoop()
    return _autonomous
