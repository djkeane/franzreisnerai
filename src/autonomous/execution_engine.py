"""
Autonomous Agent Execution Engine
Coordinates all autonomous agent systems: context, validation, error recovery, dependency management, strategies, progress tracking
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Dict, Optional, List, Callable, Any
from enum import Enum

from src.security import log_event
from src.autonomous.context_manager import ContextManager, context_manager
from src.autonomous.code_validator import CodeValidator, code_validator
from src.autonomous.error_recovery import ErrorRecovery, ErrorAnalysis, create_error_recovery
from src.autonomous.dependency_manager import DependencyManager, dependency_manager
from src.autonomous.strategy_selector import StrategySelector, strategy_selector
from src.autonomous.progress_tracker import ProgressTracker, TaskPhase, progress_tracker


class ExecutionStatus(Enum):
    """Execution status"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    TIMEOUT = "timeout"


@dataclass
class ExecutionResult:
    """Final execution result"""
    status: ExecutionStatus
    task_id: str
    task_description: str
    success: bool
    output: str
    errors: List[ErrorAnalysis]
    files_modified: List[str]
    duration_ms: float
    iterations_used: int
    max_iterations: int
    validation_issues: int
    recovery_actions_taken: int


# ════════════════════════════════════════════════════════════════════════════════
# EXECUTION ENGINE
# ════════════════════════════════════════════════════════════════════════════════

class AutonomousExecutionEngine:
    """
    Central orchestrator for autonomous agent execution:
    - Manages complete execution lifecycle
    - Coordinates all subsystems (context, validation, recovery, strategies)
    - Handles error recovery and rollback
    - Tracks progress and provides detailed reporting
    """

    def __init__(
        self,
        context_mgr: Optional[ContextManager] = None,
        validator: Optional[CodeValidator] = None,
        dependency_mgr: Optional[DependencyManager] = None,
        error_recovery: Optional[ErrorRecovery] = None,
        strategy_sel: Optional[StrategySelector] = None,
        progress_trk: Optional[ProgressTracker] = None,
    ):
        self.context = context_mgr or context_manager
        self.validator = validator or code_validator
        self.dependencies = dependency_mgr or dependency_manager
        self.error_recovery = error_recovery or create_error_recovery(self.context)
        self.strategies = strategy_sel or strategy_selector
        self.progress = progress_trk or progress_tracker

        self.status = ExecutionStatus.IDLE
        self.current_task_id: Optional[str] = None
        self.execution_results: Dict[str, ExecutionResult] = {}

    # ── Execution Control ──────────────────────────────────────────

    def execute_task(
        self,
        task_id: str,
        task_description: str,
        executor_fn: Callable,
        max_iterations: int = 10,
        timeout_seconds: Optional[int] = None,
        auto_recover: bool = True
    ) -> ExecutionResult:
        """
        Execute a coding task with full autonomous capabilities:
        - Context tracking (files, git state, session memory)
        - Validation (linting, tests, code quality)
        - Error detection and recovery
        - Dependency management
        - Strategy alternatives
        - Progress tracking and reporting
        """
        self.current_task_id = task_id
        self.status = ExecutionStatus.RUNNING

        start_time = time.time()
        errors = []
        recovery_count = 0
        total_validation_issues = 0

        # Initialize tracking systems
        self.context.start_session(task_description, max_iterations)
        self.progress.start_task(task_id, task_description, max_iterations)

        # Take initial git snapshot
        git_snapshot = self.context.snapshot_git_state()

        log_event("EXECUTION_START", f"{task_id}: {task_description[:60]}")

        try:
            # ── ANALYSIS PHASE ─────────────────────────────────────
            self.progress.start_phase(task_id, TaskPhase.ANALYSIS)

            missing_deps = self.dependencies.find_missing_dependencies()
            if missing_deps:
                self.progress.update_progress(
                    task_id, 5.0,
                    metrics={"missing_dependencies": missing_deps}
                )
                for dep in missing_deps:
                    self.dependencies.install_package(dep)
                self.context.record_success("Installed missing dependencies")

            self.progress.complete_phase(task_id, TaskPhase.ANALYSIS)

            # ── PLANNING PHASE ─────────────────────────────────────
            self.progress.start_phase(task_id, TaskPhase.PLANNING)
            self.progress.update_progress(task_id, 10.0)
            self.progress.complete_phase(task_id, TaskPhase.PLANNING)

            # ── MAIN EXECUTION LOOP ────────────────────────────────
            self.progress.start_phase(task_id, TaskPhase.IMPLEMENTATION)

            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                self.progress.increment_iteration(task_id)

                try:
                    # Execute task step
                    result = executor_fn(iteration)

                    if isinstance(result, dict):
                        if result.get("success"):
                            completion = result.get("completion_percent", 50.0)
                            self.progress.update_progress(
                                task_id, completion,
                                files_modified=result.get("modified_files", [])
                            )
                            self.context.record_success(result.get("step", ""))

                            if result.get("done"):
                                self.progress.update_progress(task_id, 100.0)
                                break
                        else:
                            error_msg = result.get("error", "Unknown error")
                            self.context.record_failure(
                                f"Iteration {iteration}", error_msg
                            )

                    # Validate modified files
                    modified_files = self.context.modified_files
                    validation_errors = 0

                    for file_path in list(modified_files)[:5]:  # Validate recent files
                        validation = self.validator.validate_file(file_path)
                        validation_errors += len(validation.errors)
                        total_validation_issues += len(validation.errors)

                        if len(validation.errors) > 0:
                            self.context.record_failure(
                                f"Validation of {file_path}",
                                f"{len(validation.errors)} errors found"
                            )

                    # Update progress
                    progress_pct = min(10.0 + (iteration / max_iterations * 70.0), 99.0)
                    self.progress.update_progress(task_id, progress_pct)

                except Exception as step_error:
                    error_text = f"{type(step_error).__name__}: {str(step_error)}"
                    self.context.record_failure(f"Step {iteration}", error_text)

                    if auto_recover:
                        analysis = self.error_recovery.analyze_error(error_text)
                        errors.append(analysis)

                        recovery_actions = self.error_recovery.suggest_recovery(analysis)
                        executed = self.error_recovery.execute_auto_recovery(analysis, recovery_actions)

                        if executed:
                            recovery_count += 1
                            self.context.record_success("Auto-recovery executed")
                        else:
                            # Try alternative strategies
                            strategies = [s for s in self.strategies.list_strategies()
                                        if s.priority.value in ["primary", "fallback"]]
                            seq = self.strategies.try_strategies(
                                task_description,
                                [s.name for s in strategies[:3]]
                            )

                            if seq.final_success:
                                self.context.record_success(f"Strategy succeeded: {seq.strategies_tried}")
                                recovery_count += 1
                            else:
                                # If auto-recovery fails and severity is high, rollback
                                if analysis.severity >= 8 and self.context.can_rollback():
                                    self.context.rollback_to_previous()
                                    self.status = ExecutionStatus.ROLLED_BACK
                                    recovery_count += 1

            self.progress.complete_phase(task_id, TaskPhase.IMPLEMENTATION)

            # ── TESTING PHASE ──────────────────────────────────────
            self.progress.start_phase(task_id, TaskPhase.TESTING)

            test_files = [str(f) for f in self.context.modified_files if "test" in str(f)]
            if test_files:
                for test_file in test_files[:3]:
                    test_result = self.validator.validate_file(test_file, run_tests=True)
                    if test_result and test_result.test_results:
                        tr = test_result.test_results
                        if tr.failed + tr.errors > 0:
                            self.context.record_failure(
                                f"Tests in {test_file}",
                                f"{tr.failed} failed, {tr.errors} errors"
                            )

            self.progress.complete_phase(task_id, TaskPhase.TESTING, subtasks_completed=len(test_files))

            # ── OPTIMIZATION PHASE ─────────────────────────────────
            self.progress.start_phase(task_id, TaskPhase.OPTIMIZATION)
            self.progress.complete_phase(task_id, TaskPhase.OPTIMIZATION)

            # ── COMPLETION ─────────────────────────────────────────
            self.progress.start_phase(task_id, TaskPhase.COMPLETION)
            self.progress.update_progress(task_id, 100.0)
            self.progress.complete_phase(task_id, TaskPhase.COMPLETION)

            # Determine final status
            if total_validation_issues > 0:
                self.status = ExecutionStatus.FAILED
            else:
                self.status = ExecutionStatus.SUCCESS

        except Exception as e:
            log_event("EXECUTION_ERROR", f"{task_id}: {str(e)}")
            self.status = ExecutionStatus.FAILED
            errors.append(self.error_recovery.analyze_error(str(e)))

        finally:
            # Calculate duration and create result
            duration_ms = (time.time() - start_time) * 1000

            # Get final state
            session = self.context.session
            modified_files = list(self.context.modified_files)

            result = ExecutionResult(
                status=self.status,
                task_id=task_id,
                task_description=task_description,
                success=self.status in [ExecutionStatus.SUCCESS],
                output=self.progress.get_progress_summary(task_id),
                errors=errors,
                files_modified=modified_files,
                duration_ms=duration_ms,
                iterations_used=iteration if session else 0,
                max_iterations=max_iterations,
                validation_issues=total_validation_issues,
                recovery_actions_taken=recovery_count
            )

            self.execution_results[task_id] = result
            self.status = ExecutionStatus.IDLE
            self.current_task_id = None

            log_event(
                "EXECUTION_COMPLETE",
                f"{task_id}: {self.status.value}, {duration_ms:.0f}ms, "
                f"{recovery_count} recoveries, {total_validation_issues} issues"
            )

        return result

    # ── Execution Reporting ────────────────────────────────────────

    def get_execution_summary(self, task_id: str) -> str:
        """Get human-readable execution summary"""
        result = self.execution_results.get(task_id)
        if not result:
            return "Execution not found"

        lines = [
            f"🎯 Execution Summary: {task_id}",
            f"   Status: {result.status.value.upper()}",
            f"   Task: {result.task_description}",
            f"   Result: {'✓ SUCCESS' if result.success else '✗ FAILED'}",
            f"\n   Metrics:",
            f"   • Duration: {result.duration_ms/1000:.1f}s",
            f"   • Iterations: {result.iterations_used}/{result.max_iterations}",
            f"   • Recoveries: {result.recovery_actions_taken}",
            f"   • Validation Issues: {result.validation_issues}",
            f"   • Files Modified: {len(result.files_modified)}",
            f"\n   Modified Files:",
        ]

        for file_path in result.files_modified[:5]:
            lines.append(f"   • {file_path}")

        if len(result.files_modified) > 5:
            lines.append(f"   ... and {len(result.files_modified) - 5} more")

        if result.errors:
            lines.append(f"\n   Errors Encountered: {len(result.errors)}")
            for error in result.errors[:3]:
                lines.append(f"   • {error.error_class}: {error.message[:60]}")

        return "\n".join(lines)

    def get_execution_stats(self) -> str:
        """Get statistics across all executions"""
        if not self.execution_results:
            return "No executions yet"

        successful = sum(1 for r in self.execution_results.values() if r.success)
        total = len(self.execution_results)
        total_time_ms = sum(r.duration_ms for r in self.execution_results.values())
        total_recoveries = sum(r.recovery_actions_taken for r in self.execution_results.values())

        lines = [
            f"📊 Execution Statistics",
            f"   Total Executions: {total}",
            f"   Successful: {successful}/{total} ({successful/total*100:.0f}%)",
            f"   Total Time: {total_time_ms/1000:.1f}s",
            f"   Avg Time/Task: {total_time_ms/total/1000:.1f}s",
            f"   Total Recoveries: {total_recoveries}",
        ]

        return "\n".join(lines)


# Singleton
execution_engine = AutonomousExecutionEngine()
