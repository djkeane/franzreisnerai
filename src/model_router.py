"""Smart Model Router — Intelligent model selection with timeout & fallback logic."""

from __future__ import annotations
import subprocess
import time
import os
import pathlib
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════════════
# SMART MODEL ROUTER — v7.5
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ModelProfile:
    """Model profiljának leírása."""
    name: str
    category: str  # "small", "coding", "general", "research"
    speed: int  # 1-10 (10=fastest)
    quality: int  # 1-10 (10=best quality)
    timeout: int  # seconds
    suitable_for: List[str]  # task types
    last_response_time: Optional[float] = None
    failures: int = 0
    last_used: Optional[datetime] = None
    enabled: bool = True

    def get_score(self, task_type: str = "general") -> float:
        """Pontszám számítása a modellhez."""
        if not self.enabled:
            return 0.0

        # Alappontok
        score = (self.speed * 0.4) + (self.quality * 0.3)

        # Feladat-illeszkedés bonus
        if task_type in self.suitable_for:
            score += 20

        # Újabb használat preferencia (friss cache)
        if self.last_used:
            age_minutes = (datetime.now() - self.last_used).total_seconds() / 60
            if age_minutes < 5:
                score += 5
            elif age_minutes > 60:
                score -= 3

        # Hibák penalizálása
        score -= self.failures * 2

        return max(0, score)

# ───────────────────────────────────────────────────────────────────────────────
# MODELL ADATBÁZIS
# ───────────────────────────────────────────────────────────────────────────────

# Lokális modellek (Ollama)
LOCAL_MODELS = {
    "qwen2.5-coder:7b": ModelProfile(
        name="qwen2.5-coder:7b",
        category="coding",
        speed=6,
        quality=9,
        timeout=45,
        suitable_for=["code", "refactoring", "debugging", "optimization"],
    ),
    "qwen2.5-coder:1.5b": ModelProfile(
        name="qwen2.5-coder:1.5b",
        category="small",
        speed=9,
        quality=7,
        timeout=20,
        suitable_for=["code", "quick-fix", "refactoring"],
    ),
    "jarvis-hu-coder:latest": ModelProfile(
        name="jarvis-hu-coder:latest",
        category="coding",
        speed=5,
        quality=8,
        timeout=40,
        suitable_for=["hungarian", "code", "explain"],
    ),
    "cronic:latest": ModelProfile(
        name="cronic:latest",
        category="general",
        speed=7,
        quality=8,
        timeout=30,
        suitable_for=["general", "chat", "hungarian"],
    ),
    "gemma4:e2b-it-q4_K_M": ModelProfile(
        name="gemma4:e2b-it-q4_K_M",
        category="small",
        speed=8,
        quality=6,
        timeout=25,
        suitable_for=["quick", "simple", "chat"],
    ),
}

# Külső meghajtóról betöltendő modellek (Mac)
MAC_DRIVE_MODELS: Dict[str, ModelProfile] = {}

# ═══════════════════════════════════════════════════════════════════════════════
# SMART ROUTER LOGIKA
# ═══════════════════════════════════════════════════════════════════════════════

class SmartModelRouter:
    """Intelligens modellválasztó."""

    def __init__(self):
        self.models: Dict[str, ModelProfile] = LOCAL_MODELS.copy()
        self.current_model: Optional[str] = None
        self.timeout_threshold = 45  # másodperc
        self.response_history: Dict[str, List[float]] = {}
        self._load_mac_drive_models()

    def _load_mac_drive_models(self) -> None:
        """Modellek betöltése a Mac meghajtóról."""
        mac_paths = [
            pathlib.Path("/Volumes/Mac"),
            pathlib.Path("/media/mac"),
            pathlib.Path.home() / "Mac",
            pathlib.Path("/mnt/mac"),
        ]

        for mac_path in mac_paths:
            if mac_path.exists():
                self._scan_mac_models(mac_path)
                break

    def _scan_mac_models(self, mac_path: pathlib.Path) -> None:
        """Mac meghajtó modelleinek keresése."""
        try:
            # Keresés a tipikus Ollama könyvtárban
            ollama_dir = mac_path / ".ollama" / "models" / "blobs"
            if ollama_dir.exists():
                for model_file in ollama_dir.glob("*"):
                    model_name = model_file.name
                    # Heurisztikus kategorizálás az alapján, hogy milyen a modell neve
                    if "coder" in model_name or "code" in model_name:
                        category = "coding"
                        speed = 5
                        quality = 8
                    elif "small" in model_name or "mini" in model_name or "1.5b" in model_name:
                        category = "small"
                        speed = 9
                        quality = 6
                    else:
                        category = "general"
                        speed = 6
                        quality = 7

                    self.models[model_name] = ModelProfile(
                        name=model_name,
                        category=category,
                        speed=speed,
                        quality=quality,
                        timeout=40,
                        suitable_for=["general", "chat"],
                    )

            # Keresés más helyen
            for item in mac_path.iterdir():
                if item.is_dir() and "model" in item.name.lower():
                    for model_file in item.iterdir():
                        if model_file.suffix in [".gguf", ".bin"]:
                            model_name = f"mac-{model_file.stem}"
                            self.models[model_name] = ModelProfile(
                                name=model_name,
                                category="external",
                                speed=4,
                                quality=8,
                                timeout=45,
                                suitable_for=["general"],
                            )

        except Exception as e:
            print(f"[WARNING] Mac meghajtó modellek betöltési hiba: {e}")

    def select_model(self, task_type: str = "general", prefer_fast: bool = False) -> str:
        """
        Intelligens modellválasztás a feladat típusa alapján.

        Args:
            task_type: "code", "general", "hungarian", "quick", "research"
            prefer_fast: Ha True, a gyors modelleket előnyben részesíti

        Returns:
            Kiválasztott modell neve
        """
        available = [m for m in self.models.values() if m.enabled]

        if not available:
            return "qwen2.5-coder:7b"  # Fallback

        if prefer_fast:
            # Gyors modellekre szűrés
            available = [m for m in available if m.speed >= 7]

        # Pontszám szerinti rendezés
        ranked = sorted(
            available,
            key=lambda m: m.get_score(task_type),
            reverse=True
        )

        selected = ranked[0]
        self.current_model = selected.name
        selected.last_used = datetime.now()

        return selected.name

    def select_with_fallback(
        self,
        task_type: str = "general",
        max_attempts: int = 3
    ) -> List[str]:
        """
        Fallback stratégia: visszalépések modellek között.

        Returns:
            Modellnevek sorrend (1. elsőszámú, 2. fallback, 3. végszükség)
        """
        available = [m for m in self.models.values() if m.enabled]
        available_sorted = sorted(
            available,
            key=lambda m: m.get_score(task_type),
            reverse=True
        )

        return [m.name for m in available_sorted[:max_attempts]]

    def check_timeout(self, model: str, elapsed_time: float) -> bool:
        """
        Timeout ellenőrzése. Ha túllépte, True.

        Args:
            model: Modell neve
            elapsed_time: Eltelt idő másodpercben
        """
        if model not in self.models:
            return elapsed_time > self.timeout_threshold

        model_profile = self.models[model]
        threshold = min(model_profile.timeout, self.timeout_threshold)

        # Eltelt időt rögzítjük
        if model not in self.response_history:
            self.response_history[model] = []
        self.response_history[model].append(elapsed_time)

        # Ha túl hosszú, kiírjuk a figyelmeztető
        if elapsed_time > threshold:
            avg_time = sum(self.response_history[model]) / len(self.response_history[model])
            if avg_time > threshold * 0.9:
                # A modell általában lassú
                model_profile.failures += 1
            return True

        return False

    def record_response_time(self, model: str, elapsed_time: float) -> None:
        """Válasz időt rögzítjük."""
        if model not in self.response_history:
            self.response_history[model] = []
        self.response_history[model].append(elapsed_time)

        # Последние 10 választ tárolunk
        if len(self.response_history[model]) > 10:
            self.response_history[model].pop(0)

        if model in self.models:
            self.models[model].last_response_time = elapsed_time

    def get_average_response_time(self, model: str) -> float:
        """Átlagos válaszidő."""
        if model not in self.response_history or not self.response_history[model]:
            return 0.0
        return sum(self.response_history[model]) / len(self.response_history[model])

    def list_models(self, category: str = None) -> Dict[str, Dict]:
        """Elérhető modellek listája."""
        result = {}
        for name, profile in self.models.items():
            if category and profile.category != category:
                continue

            result[name] = {
                "category": profile.category,
                "speed": f"{profile.speed}/10",
                "quality": f"{profile.quality}/10",
                "timeout": f"{profile.timeout}s",
                "suitable_for": profile.suitable_for,
                "enabled": profile.enabled,
                "failures": profile.failures,
                "avg_response_time": f"{self.get_average_response_time(name):.2f}s",
            }

        return result

    def report_failure(self, model: str) -> None:
        """Modell hibájának rögzítése. 10 perc után automatikusan visszaengedélyez."""
        if model in self.models:
            self.models[model].failures += 1
            if self.models[model].failures >= 3:
                self.models[model].enabled = False
                print(f"⚠️  {model} letiltva (túl sok hiba) — 10 perc múlva visszaáll")
                import threading as _t
                def _reenable():
                    self.models[model].failures = 0
                    self.models[model].enabled = True
                    print(f"✅ {model} visszaengedélyezve (auto-reset)")
                _t.Timer(600, _reenable).start()

    def reset_model_stats(self, model: str = None) -> None:
        """Modell statisztikájának alaphelyzetbe állítása."""
        if model:
            if model in self.models:
                self.models[model].failures = 0
                self.models[model].enabled = True
        else:
            for m in self.models.values():
                m.failures = 0
                m.enabled = True

    def get_status_report(self) -> str:
        """Rendszer-státusz jelentés."""
        report = """
╔══════════════════════════════════════════════════════════════════════════════╗
║ 🤖 SMART MODEL ROUTER — STÁTUSZ JELENTÉS
╚══════════════════════════════════════════════════════════════════════════════╝

📊 MODELLEK ÁTTEKINTÉSE:
"""
        by_category = {}
        for name, profile in self.models.items():
            cat = profile.category
            if cat not in by_category:
                by_category[cat] = []
            avg_time = self.get_average_response_time(name)
            status = "✅" if profile.enabled else "❌"
            by_category[cat].append(f"  {status} {name:30} [{profile.speed}/10 speed, {avg_time:.1f}s avg]")

        for cat in sorted(by_category.keys()):
            report += f"\n🏷️  {cat.upper()}\n"
            for line in by_category[cat]:
                report += line + "\n"

        report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏱️  TIMEOUT BEÁLLÍTÁS: {self.timeout_threshold}s
🔄 AKTÍV MODELLEK: {sum(1 for m in self.models.values() if m.enabled)}/{len(self.models)}
🎯 AKTUÁLIS MODELL: {self.current_model or '(nincs kiválasztva)'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBÁLIS ROUTER INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

router = SmartModelRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# NYILVÁNOS FUNKCIÓK
# ═══════════════════════════════════════════════════════════════════════════════

def get_best_model(task_type: str = "general", prefer_fast: bool = False) -> str:
    """Legjobb modell kiválasztása."""
    return router.select_model(task_type, prefer_fast)


def get_fallback_chain(task_type: str = "general") -> List[str]:
    """Fallback modellsorrend."""
    return router.select_with_fallback(task_type)


def check_model_timeout(model: str, elapsed_seconds: float) -> bool:
    """Timeout ellenőrzése."""
    return router.check_timeout(model, elapsed_seconds)


def record_model_response(model: str, elapsed_seconds: float) -> None:
    """Válaszidő rögzítése."""
    router.record_response_time(model, elapsed_seconds)


def report_model_failure(model: str) -> None:
    """Hiba rögzítése."""
    router.report_failure(model)


def list_all_models(category: str = None) -> Dict:
    """Modellek listázása."""
    return router.list_models(category)


def get_router_status() -> str:
    """Státusz jelentés."""
    return router.get_status_report()
