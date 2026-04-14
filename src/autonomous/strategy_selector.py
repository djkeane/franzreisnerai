"""
Autonomous Agent Strategy Selector
Tries alternative approaches when primary strategy fails
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

from src.security import log_event


class StrategyPriority(Enum):
    """Strategy execution priority"""
    PRIMARY = "primary"  # Try first
    FALLBACK = "fallback"  # Try if primary fails
    EXPERIMENTAL = "experimental"  # Try if others fail
    LAST_RESORT = "last_resort"  # Only try if critical


@dataclass
class Strategy:
    """Single approach/strategy"""
    name: str
    description: str
    priority: StrategyPriority
    executor: Optional[Callable] = None  # Function to execute
    params: Dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 1
    timeout_seconds: Optional[int] = None
    estimated_success_rate: float = 0.5  # 0-1 confidence
    dependencies: List[str] = field(default_factory=list)  # Other strategies this depends on
    incompatible_with: List[str] = field(default_factory=list)  # Strategies that conflict


@dataclass
class StrategyAttempt:
    """Result of executing a strategy"""
    strategy_name: str
    attempt_number: int
    success: bool
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    modified_files: List[str] = field(default_factory=list)


@dataclass
class StrategySequence:
    """Complete sequence of attempts"""
    task: str
    attempts: List[StrategyAttempt] = field(default_factory=list)
    final_success: bool = False
    total_duration_ms: float = 0.0
    strategies_tried: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════════
# STRATEGY SELECTOR
# ════════════════════════════════════════════════════════════════════════════════

class StrategySelector:
    """
    Intelligent strategy selection and execution:
    - Maintain library of strategies
    - Execute strategies in order
    - Learn from failures
    - Try alternatives automatically
    """

    def __init__(self):
        self.strategies: Dict[str, Strategy] = {}
        self.sequence: Optional[StrategySequence] = None
        self.execution_history: List[StrategySequence] = []
        self.strategy_success_rate: Dict[str, float] = {}

    # ── Strategy Registration ──────────────────────────────────────

    def register_strategy(self, strategy: Strategy) -> None:
        """Register a strategy"""
        self.strategies[strategy.name] = strategy
        if strategy.name not in self.strategy_success_rate:
            self.strategy_success_rate[strategy.name] = strategy.estimated_success_rate
        log_event("STRATEGY_REGISTERED", strategy.name)

    def register_strategies(self, strategies: List[Strategy]) -> None:
        """Register multiple strategies"""
        for strategy in strategies:
            self.register_strategy(strategy)

    def get_strategy(self, name: str) -> Optional[Strategy]:
        """Get strategy by name"""
        return self.strategies.get(name)

    def list_strategies(self) -> List[Strategy]:
        """Get all registered strategies"""
        return list(self.strategies.values())

    # ── Strategy Sequencing ────────────────────────────────────────

    def _sort_by_priority(self, strategies: List[Strategy]) -> List[Strategy]:
        """Sort strategies by priority"""
        priority_order = {
            StrategyPriority.PRIMARY: 0,
            StrategyPriority.FALLBACK: 1,
            StrategyPriority.EXPERIMENTAL: 2,
            StrategyPriority.LAST_RESORT: 3,
        }
        return sorted(
            strategies,
            key=lambda s: (priority_order.get(s.priority, 999), -self.strategy_success_rate.get(s.name, 0))
        )

    def _check_dependencies(self, strategy: Strategy, attempted: List[str]) -> bool:
        """Check if strategy dependencies are met"""
        for dep in strategy.dependencies:
            if dep not in attempted:
                return False
        return True

    def _check_conflicts(self, strategy: Strategy, attempted: List[str]) -> bool:
        """Check if strategy conflicts with already-attempted strategies"""
        for conflict in strategy.incompatible_with:
            if conflict in attempted:
                return False
        return True

    # ── Execution ──────────────────────────────────────────────────

    def execute_strategy(
        self,
        strategy: Strategy,
        attempt_num: int = 1
    ) -> StrategyAttempt:
        """Execute a single strategy"""
        attempt = StrategyAttempt(
            strategy_name=strategy.name,
            attempt_number=attempt_num,
            success=False
        )

        try:
            if not strategy.executor:
                attempt.error = "No executor function defined"
                return attempt

            # Execute with timeout
            import time
            start = time.time()

            result = strategy.executor(**strategy.params)
            duration = (time.time() - start) * 1000

            # Interpret result
            if isinstance(result, dict):
                attempt.success = result.get("success", False)
                attempt.output = result.get("output", "")
                attempt.error = result.get("error", "")
                attempt.modified_files = result.get("modified_files", [])
            else:
                attempt.success = bool(result)
                attempt.output = str(result)

            attempt.duration_ms = duration
            log_event("STRATEGY_EXECUTED", f"{strategy.name}: {attempt.success}")

        except Exception as e:
            attempt.success = False
            attempt.error = str(e)
            log_event("STRATEGY_EXCEPTION", f"{strategy.name}: {str(e)}")

        return attempt

    def try_strategies(
        self,
        task: str,
        applicable_strategies: Optional[List[str]] = None,
        max_total_attempts: int = 10
    ) -> StrategySequence:
        """Try strategies in sequence until success"""
        self.sequence = StrategySequence(task=task)

        # Get applicable strategies
        all_strategies = self.list_strategies()
        if applicable_strategies:
            all_strategies = [
                s for s in all_strategies
                if s.name in applicable_strategies
            ]

        # Sort by priority
        all_strategies = self._sort_by_priority(all_strategies)

        attempted = []
        total_attempts = 0
        start_time = time.time() if 'time' in dir() else None

        for strategy in all_strategies:
            if total_attempts >= max_total_attempts:
                break

            # Check dependencies and conflicts
            if not self._check_dependencies(strategy, attempted):
                continue
            if not self._check_conflicts(strategy, attempted):
                continue

            # Execute strategy (possibly multiple times)
            for attempt_num in range(1, strategy.max_attempts + 1):
                if total_attempts >= max_total_attempts:
                    break

                attempt = self.execute_strategy(strategy, attempt_num)
                self.sequence.attempts.append(attempt)
                self.sequence.strategies_tried.append(strategy.name)

                total_attempts += 1

                if attempt.success:
                    self.sequence.final_success = True
                    attempted.append(strategy.name)
                    # Update success rate
                    self.strategy_success_rate[strategy.name] = \
                        self.strategy_success_rate.get(strategy.name, 0.5) * 0.9 + 0.1
                    break
            else:
                # All attempts failed, mark as tried but unsuccessful
                attempted.append(strategy.name)
                # Decrease success rate
                self.strategy_success_rate[strategy.name] = \
                    max(0.1, self.strategy_success_rate.get(strategy.name, 0.5) * 0.7)

            if self.sequence.final_success:
                break

        # Calculate total duration
        import time
        self.sequence.total_duration_ms = 0  # TODO: calculate from attempts

        # Log result
        log_event(
            "STRATEGIES_TRIED",
            f"Task: {task[:40]}, Success: {self.sequence.final_success}, "
            f"Attempts: {len(self.sequence.attempts)}"
        )

        # Store in history
        self.execution_history.append(self.sequence)

        return self.sequence

    # ── Reporting ──────────────────────────────────────────────────

    def get_sequence_summary(self, sequence: Optional[StrategySequence] = None) -> str:
        """Get human-readable sequence summary"""
        if sequence is None:
            sequence = self.sequence
        if sequence is None:
            return "No strategy sequence to report"

        lines = [
            f"🎯 Strategy Execution Summary",
            f"   Task: {sequence.task[:60]}",
            f"   Result: {'✓ SUCCESS' if sequence.final_success else '✗ FAILED'}",
            f"   Total Attempts: {len(sequence.attempts)}",
            f"   Duration: {sequence.total_duration_ms:.0f}ms",
            f"\n   Strategies Tried:",
        ]

        for attempt in sequence.attempts:
            status = "✓" if attempt.success else "✗"
            lines.append(
                f"   {status} {attempt.strategy_name} "
                f"(attempt {attempt.attempt_number}, {attempt.duration_ms:.0f}ms)"
            )
            if attempt.error:
                lines.append(f"      Error: {attempt.error[:80]}")
            if attempt.modified_files:
                lines.append(f"      Modified: {', '.join(attempt.modified_files[:3])}")

        lines.append(f"\n   Success Rates (updated):")
        for name, rate in sorted(self.strategy_success_rate.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"   • {name}: {rate:.0%}")

        return "\n".join(lines)

    def get_execution_history_summary(self) -> str:
        """Get summary of all executions"""
        if not self.execution_history:
            return "No execution history"

        successful = sum(1 for s in self.execution_history if s.final_success)
        total = len(self.execution_history)
        total_attempts = sum(len(s.attempts) for s in self.execution_history)

        lines = [
            f"📊 Strategy Execution History",
            f"   Total Sequences: {total}",
            f"   Successful: {successful}/{total} ({successful/total*100:.0f}%)",
            f"   Total Attempts: {total_attempts}",
            f"\n   Recent Sequences:",
        ]

        for seq in self.execution_history[-5:]:
            status = "✓" if seq.final_success else "✗"
            lines.append(f"   {status} {seq.task[:50]}... ({len(seq.attempts)} attempts)")

        return "\n".join(lines)


# Singleton
strategy_selector = StrategySelector()

# ── Built-in Strategies ────────────────────────────────────────────────────────

def register_builtin_strategies() -> None:
    """Register built-in strategies for common tasks"""

    # Code fixing strategies
    strategy_selector.register_strategy(Strategy(
        name="format_with_black",
        description="Format code with black formatter",
        priority=StrategyPriority.PRIMARY,
        estimated_success_rate=0.95
    ))

    strategy_selector.register_strategy(Strategy(
        name="fix_with_pylint",
        description="Fix issues using pylint suggestions",
        priority=StrategyPriority.FALLBACK,
        estimated_success_rate=0.65
    ))

    strategy_selector.register_strategy(Strategy(
        name="simplify_implementation",
        description="Simplify code to reduce complexity",
        priority=StrategyPriority.FALLBACK,
        estimated_success_rate=0.6
    ))

    strategy_selector.register_strategy(Strategy(
        name="refactor_with_type_hints",
        description="Add type hints to improve type safety",
        priority=StrategyPriority.FALLBACK,
        estimated_success_rate=0.7
    ))

    strategy_selector.register_strategy(Strategy(
        name="try_alternative_algorithm",
        description="Try alternative algorithm or approach",
        priority=StrategyPriority.EXPERIMENTAL,
        estimated_success_rate=0.4
    ))

    strategy_selector.register_strategy(Strategy(
        name="reduce_complexity",
        description="Break down complex function into smaller parts",
        priority=StrategyPriority.EXPERIMENTAL,
        estimated_success_rate=0.5
    ))

    strategy_selector.register_strategy(Strategy(
        name="rollback_and_replan",
        description="Rollback changes and try completely different approach",
        priority=StrategyPriority.LAST_RESORT,
        estimated_success_rate=0.3
    ))


# Register built-ins on import
register_builtin_strategies()
