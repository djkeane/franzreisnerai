"""
Autonomous Agent Progress Tracker
Tracks task completion, estimates time remaining, monitors metrics
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

from src.security import log_event


class TaskPhase(Enum):
    """Task execution phases"""
    ANALYSIS = "analysis"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    DEBUGGING = "debugging"
    OPTIMIZATION = "optimization"
    COMPLETION = "completion"


@dataclass
class PhaseMetrics:
    """Metrics for a single phase"""
    phase: TaskPhase
    started_at: float
    completed_at: Optional[float] = None
    duration_ms: float = 0.0
    status: str = "pending"  # pending, in_progress, completed, failed
    subtasks_completed: int = 0
    subtasks_total: int = 0
    percentage: float = 0.0


@dataclass
class ProgressCheckpoint:
    """Point-in-time progress snapshot"""
    timestamp: float
    phase: TaskPhase
    completion_percent: float
    iterations_completed: int
    iterations_remaining: int
    estimated_time_remaining_ms: float
    files_modified: List[str] = field(default_factory=list)
    metrics: Dict = field(default_factory=dict)


@dataclass
class TaskProgress:
    """Overall task progress tracking"""
    task_id: str
    task_description: str
    started_at: float
    phases: Dict[TaskPhase, PhaseMetrics] = field(default_factory=dict)
    current_phase: Optional[TaskPhase] = None
    checkpoints: List[ProgressCheckpoint] = field(default_factory=list)
    overall_completion_percent: float = 0.0
    iterations: int = 0
    max_iterations: int = 10


# ════════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKER
# ════════════════════════════════════════════════════════════════════════════════

class ProgressTracker:
    """
    Track task progress:
    - Phase-based tracking
    - Completion estimation
    - Time remaining calculation
    - Milestone checkpoints
    """

    def __init__(self):
        self.tasks: Dict[str, TaskProgress] = {}
        self.current_task: Optional[str] = None
        self.phase_duration_history: Dict[TaskPhase, List[float]] = {
            phase: [] for phase in TaskPhase
        }

    # ── Task Initialization ────────────────────────────────────────

    def start_task(
        self,
        task_id: str,
        task_description: str,
        max_iterations: int = 10
    ) -> TaskProgress:
        """Start tracking a new task"""
        progress = TaskProgress(
            task_id=task_id,
            task_description=task_description,
            started_at=time.time(),
            max_iterations=max_iterations
        )

        self.tasks[task_id] = progress
        self.current_task = task_id

        # Initialize phases
        for phase in TaskPhase:
            progress.phases[phase] = PhaseMetrics(
                phase=phase,
                started_at=time.time()
            )

        log_event("TASK_START", f"{task_id}: {task_description[:50]}")
        return progress

    def get_task_progress(self, task_id: str) -> Optional[TaskProgress]:
        """Get progress for specific task"""
        return self.tasks.get(task_id)

    def get_current_task_progress(self) -> Optional[TaskProgress]:
        """Get progress for current task"""
        if self.current_task:
            return self.tasks.get(self.current_task)
        return None

    # ── Phase Management ───────────────────────────────────────────

    def start_phase(self, task_id: str, phase: TaskPhase) -> None:
        """Mark start of a task phase"""
        progress = self.tasks.get(task_id)
        if not progress:
            return

        progress.current_phase = phase
        phase_metrics = progress.phases[phase]
        phase_metrics.started_at = time.time()
        phase_metrics.status = "in_progress"

        log_event("PHASE_START", f"{task_id}: {phase.value}")

    def complete_phase(
        self,
        task_id: str,
        phase: TaskPhase,
        subtasks_completed: Optional[int] = None
    ) -> None:
        """Mark completion of a task phase"""
        progress = self.tasks.get(task_id)
        if not progress:
            return

        phase_metrics = progress.phases[phase]
        phase_metrics.completed_at = time.time()
        phase_metrics.status = "completed"
        phase_metrics.duration_ms = (phase_metrics.completed_at - phase_metrics.started_at) * 1000

        if subtasks_completed is not None:
            phase_metrics.subtasks_completed = subtasks_completed
            if phase_metrics.subtasks_total > 0:
                phase_metrics.percentage = (subtasks_completed / phase_metrics.subtasks_total) * 100

        # Record in history for future estimates
        self.phase_duration_history[phase].append(phase_metrics.duration_ms)

        log_event("PHASE_COMPLETE", f"{task_id}: {phase.value} ({phase_metrics.duration_ms:.0f}ms)")

    # ── Progress Updates ───────────────────────────────────────────

    def update_progress(
        self,
        task_id: str,
        completion_percent: float,
        files_modified: Optional[List[str]] = None,
        metrics: Optional[Dict] = None
    ) -> ProgressCheckpoint:
        """Record progress checkpoint"""
        progress = self.tasks.get(task_id)
        if not progress:
            return None

        progress.overall_completion_percent = completion_percent
        if files_modified:
            checkpoint = ProgressCheckpoint(
                timestamp=time.time(),
                phase=progress.current_phase or TaskPhase.ANALYSIS,
                completion_percent=completion_percent,
                iterations_completed=progress.iterations,
                iterations_remaining=max(0, progress.max_iterations - progress.iterations),
                estimated_time_remaining_ms=self._estimate_remaining_time(task_id),
                files_modified=files_modified,
                metrics=metrics or {}
            )
        else:
            checkpoint = ProgressCheckpoint(
                timestamp=time.time(),
                phase=progress.current_phase or TaskPhase.ANALYSIS,
                completion_percent=completion_percent,
                iterations_completed=progress.iterations,
                iterations_remaining=max(0, progress.max_iterations - progress.iterations),
                estimated_time_remaining_ms=self._estimate_remaining_time(task_id)
            )

        progress.checkpoints.append(checkpoint)

        log_event(
            "PROGRESS_UPDATE",
            f"{task_id}: {completion_percent:.0f}% (iter {progress.iterations})"
        )

        return checkpoint

    def increment_iteration(self, task_id: str) -> None:
        """Record completed iteration"""
        progress = self.tasks.get(task_id)
        if progress:
            progress.iterations += 1
            log_event("ITERATION_COMPLETE", f"{task_id}: iteration {progress.iterations}")

    # ── Time Estimation ────────────────────────────────────────────

    def _estimate_remaining_time(self, task_id: str) -> float:
        """Estimate time remaining based on current phase and history"""
        progress = self.tasks.get(task_id)
        if not progress:
            return 0.0

        if progress.current_phase is None:
            return 0.0

        # Average duration of current phase type
        phase_history = self.phase_duration_history.get(progress.current_phase, [])
        if not phase_history:
            return 0.0

        avg_phase_duration = sum(phase_history) / len(phase_history)

        # Phases still remaining
        phases_remaining = 0
        current_found = False
        for phase in TaskPhase:
            if phase == progress.current_phase:
                current_found = True
            elif current_found:
                phases_remaining += 1

        # Estimate: current phase + remaining phases
        current_phase_metrics = progress.phases[progress.current_phase]
        elapsed = (time.time() - current_phase_metrics.started_at) * 1000
        current_remaining = max(0, avg_phase_duration - elapsed)

        estimated_remaining = current_remaining + (phases_remaining * avg_phase_duration)
        return estimated_remaining

    def estimate_completion_time(self, task_id: str) -> float:
        """Estimate absolute time of task completion"""
        remaining_ms = self._estimate_remaining_time(task_id)
        return time.time() + (remaining_ms / 1000)

    # ── Reporting ──────────────────────────────────────────────────

    def get_progress_summary(self, task_id: str) -> str:
        """Get human-readable progress summary"""
        progress = self.tasks.get(task_id)
        if not progress:
            return "Task not found"

        elapsed = (time.time() - progress.started_at) * 1000
        remaining = self._estimate_remaining_time(task_id)
        completion = progress.overall_completion_percent

        lines = [
            f"📊 Task Progress: {progress.task_description[:50]}",
            f"   Status: {completion:.0f}% complete",
            f"   Time Elapsed: {elapsed/1000:.1f}s",
            f"   Estimated Remaining: {remaining/1000:.1f}s",
            f"   Iterations: {progress.iterations}/{progress.max_iterations}",
            f"\n   Phase Status:",
        ]

        for phase in TaskPhase:
            metrics = progress.phases[phase]
            if metrics.status == "completed":
                lines.append(
                    f"   ✓ {phase.value:<20} {metrics.duration_ms/1000:>6.1f}s "
                    f"({metrics.subtasks_completed}/{metrics.subtasks_total} subtasks)"
                )
            elif metrics.status == "in_progress":
                lines.append(f"   ⧖ {phase.value:<20} in progress...")
            else:
                lines.append(f"   ○ {phase.value:<20} pending")

        if progress.checkpoints:
            lines.append(f"\n   Recent Checkpoints:")
            for cp in progress.checkpoints[-3:]:
                lines.append(
                    f"   • {cp.phase.value}: {cp.completion_percent:.0f}% "
                    f"(+{len(cp.files_modified)} files)"
                )

        return "\n".join(lines)

    def get_detailed_metrics(self, task_id: str) -> Dict:
        """Get detailed metrics for task"""
        progress = self.tasks.get(task_id)
        if not progress:
            return {}

        total_duration = (time.time() - progress.started_at) * 1000
        completed_phases = sum(
            1 for p in progress.phases.values()
            if p.status == "completed"
        )

        return {
            "task_id": task_id,
            "completion_percent": progress.overall_completion_percent,
            "elapsed_ms": total_duration,
            "estimated_remaining_ms": self._estimate_remaining_time(task_id),
            "iterations": progress.iterations,
            "max_iterations": progress.max_iterations,
            "phases_completed": completed_phases,
            "total_phases": len(TaskPhase),
            "checkpoints": len(progress.checkpoints),
            "phase_breakdown": {
                phase.value: {
                    "duration_ms": metrics.duration_ms,
                    "status": metrics.status,
                    "subtasks": f"{metrics.subtasks_completed}/{metrics.subtasks_total}"
                }
                for phase, metrics in progress.phases.items()
            }
        }

    def get_all_tasks_summary(self) -> str:
        """Get summary of all tracked tasks"""
        if not self.tasks:
            return "No tasks being tracked"

        lines = [
            f"📊 All Tasks Summary",
            f"   Total Tasks: {len(self.tasks)}",
        ]

        completed = sum(1 for p in self.tasks.values() if p.overall_completion_percent >= 100)
        lines.append(f"   Completed: {completed}/{len(self.tasks)}\n")

        for task_id, progress in sorted(self.tasks.items(), key=lambda x: x[1].overall_completion_percent, reverse=True):
            status = "✓" if progress.overall_completion_percent >= 100 else "⧖"
            lines.append(
                f"   {status} {progress.task_id:<30} "
                f"{progress.overall_completion_percent:>6.0f}% "
                f"({progress.iterations}/{progress.max_iterations} iter)"
            )

        return "\n".join(lines)


# Singleton
progress_tracker = ProgressTracker()
