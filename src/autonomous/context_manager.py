"""
Autonomous Agent Context Manager
Manages code context, file caching, git state, and session memory
"""

from __future__ import annotations
import hashlib
import json
import pathlib
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

from src.security import log_event


class FileState(Enum):
    """File modification state"""
    ORIGINAL = "original"
    MODIFIED = "modified"
    CREATED = "created"
    DELETED = "deleted"


@dataclass
class FileContext:
    """File context snapshot"""
    path: str
    hash: str  # MD5 of content
    state: FileState
    size: int
    modified_time: float
    content_preview: str = ""  # First 500 chars


@dataclass
class GitSnapshot:
    """Git state snapshot"""
    branch: str
    current_commit: str
    uncommitted_changes: Dict[str, str]  # {path: status}
    staged_files: List[str]
    untracked_files: List[str]
    dirty: bool


@dataclass
class SessionMemory:
    """Session execution memory"""
    task_description: str
    iteration: int = 0
    total_iterations: int = 0
    successful_steps: List[str] = None
    failed_steps: List[Tuple[str, str]] = None  # (step, error)
    current_goal: str = ""
    attempted_strategies: List[str] = None

    def __post_init__(self):
        if self.successful_steps is None:
            self.successful_steps = []
        if self.failed_steps is None:
            self.failed_steps = []
        if self.attempted_strategies is None:
            self.attempted_strategies = []


# ════════════════════════════════════════════════════════════════════════════════
# CONTEXT MANAGER
# ════════════════════════════════════════════════════════════════════════════════

class ContextManager:
    """
    Manages complete context for autonomous agent:
    - File tracking & caching
    - Git state monitoring
    - Session memory & progress
    - Dependency tracking
    """

    def __init__(self, project_root: str = "."):
        self.project_root = pathlib.Path(project_root)
        self.file_cache: Dict[str, FileContext] = {}
        self.git_snapshots: List[GitSnapshot] = []
        self.session: Optional[SessionMemory] = None
        self.dependencies: Set[str] = set()
        self.modified_files: Set[str] = set()
        self.created_files: Set[str] = set()

    # ── File Context Management ────────────────────────────────

    def snapshot_file(self, file_path: str) -> FileContext:
        """Create a file context snapshot"""
        try:
            path = self.project_root / file_path
            if not path.exists():
                return FileContext(
                    path=file_path,
                    hash="",
                    state=FileState.DELETED,
                    size=0,
                    modified_time=0
                )

            content = path.read_text(encoding="utf-8", errors="ignore")
            file_hash = hashlib.md5(content.encode()).hexdigest()
            stat = path.stat()

            context = FileContext(
                path=file_path,
                hash=file_hash,
                state=FileState.ORIGINAL,  # Will be updated based on git
                size=stat.st_size,
                modified_time=stat.st_mtime,
                content_preview=content[:500]
            )

            self.file_cache[file_path] = context
            return context

        except Exception as e:
            log_event("FILE_SNAPSHOT_ERROR", f"{file_path}: {e}")
            return FileContext(
                path=file_path,
                hash="",
                state=FileState.ORIGINAL,
                size=0,
                modified_time=0
            )

    def detect_file_changes(self) -> Dict[str, FileState]:
        """Detect which files have changed since last snapshot"""
        changes = {}

        for file_path, old_context in self.file_cache.items():
            new_context = self.snapshot_file(file_path)

            if old_context.hash != new_context.hash:
                changes[file_path] = FileState.MODIFIED
                self.modified_files.add(file_path)
            elif old_context.state == FileState.DELETED and new_context.state != FileState.DELETED:
                changes[file_path] = FileState.CREATED
                self.created_files.add(file_path)
            elif old_context.state != FileState.DELETED and new_context.state == FileState.DELETED:
                changes[file_path] = FileState.DELETED

        return changes

    # ── Git State Management ───────────────────────────────────

    def snapshot_git_state(self) -> GitSnapshot:
        """Capture current git state"""
        try:
            # Current branch
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=5
            ).stdout.strip()

            # Current commit
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=5
            ).stdout.strip()

            # Status
            status_output = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=5
            ).stdout

            uncommitted = {}
            staged = []
            untracked = []

            for line in status_output.split("\n"):
                if not line:
                    continue
                status_code = line[:2]
                file_path = line[3:]

                if status_code[0] == "?":
                    untracked.append(file_path)
                elif status_code[0] in "AM":
                    staged.append(file_path)
                else:
                    uncommitted[file_path] = status_code

            snapshot = GitSnapshot(
                branch=branch,
                current_commit=commit,
                uncommitted_changes=uncommitted,
                staged_files=staged,
                untracked_files=untracked,
                dirty=bool(uncommitted or staged or untracked)
            )

            self.git_snapshots.append(snapshot)
            return snapshot

        except Exception as e:
            log_event("GIT_SNAPSHOT_ERROR", str(e))
            return GitSnapshot(
                branch="unknown",
                current_commit="unknown",
                uncommitted_changes={},
                staged_files=[],
                untracked_files=[],
                dirty=False
            )

    def can_rollback(self) -> bool:
        """Check if we can rollback to previous git state"""
        return len(self.git_snapshots) >= 2

    def rollback_to_previous(self) -> bool:
        """Rollback to previous git snapshot"""
        try:
            if not self.can_rollback():
                return False

            prev_snapshot = self.git_snapshots[-2]

            # Checkout previous commit
            subprocess.run(
                ["git", "reset", "--hard", prev_snapshot.current_commit],
                cwd=self.project_root,
                timeout=10
            )

            log_event("GIT_ROLLBACK", f"Rolled back to {prev_snapshot.current_commit[:8]}")
            return True

        except Exception as e:
            log_event("ROLLBACK_ERROR", str(e))
            return False

    # ── Session Memory ────────────────────────────────────────

    def start_session(self, task: str, max_iterations: int = 10) -> SessionMemory:
        """Start a new session"""
        self.session = SessionMemory(
            task_description=task,
            iteration=0,
            total_iterations=max_iterations,
        )
        log_event("SESSION_START", f"task={task[:60]}")
        return self.session

    def record_success(self, step: str) -> None:
        """Record a successful step"""
        if self.session:
            self.session.successful_steps.append(step)
            log_event("STEP_SUCCESS", step[:80])

    def record_failure(self, step: str, error: str) -> None:
        """Record a failed step"""
        if self.session:
            self.session.failed_steps.append((step, error))
            log_event("STEP_FAILURE", f"{step[:40]}: {error[:50]}")

    def next_iteration(self) -> None:
        """Move to next iteration"""
        if self.session:
            self.session.iteration += 1

    def get_session_summary(self) -> str:
        """Get current session summary"""
        if not self.session:
            return "No active session"

        lines = [
            f"Task: {self.session.task_description[:60]}",
            f"Iteration: {self.session.iteration}/{self.session.total_iterations}",
            f"Successful steps: {len(self.session.successful_steps)}",
            f"Failed steps: {len(self.session.failed_steps)}",
            f"Attempted strategies: {len(self.session.attempted_strategies)}",
        ]

        if self.session.successful_steps:
            lines.append(f"\nSuccessful: {', '.join(self.session.successful_steps[:3])}")

        if self.session.failed_steps:
            lines.append(f"\nFailed: {', '.join([s for s, _ in self.session.failed_steps[:3]])}")

        return "\n".join(lines)

    # ── Dependency Tracking ────────────────────────────────────

    def add_dependency(self, dep: str) -> None:
        """Track a code dependency"""
        self.dependencies.add(dep)

    def get_dependencies(self) -> List[str]:
        """Get all tracked dependencies"""
        return sorted(list(self.dependencies))

    # ── Context Summary ────────────────────────────────────────

    def get_context_summary(self) -> Dict:
        """Get complete context summary"""
        return {
            "files_tracked": len(self.file_cache),
            "files_modified": len(self.modified_files),
            "files_created": len(self.created_files),
            "git_snapshots": len(self.git_snapshots),
            "dependencies": len(self.dependencies),
            "current_iteration": self.session.iteration if self.session else 0,
            "modified_files": list(self.modified_files),
            "created_files": list(self.created_files),
            "session_summary": self.get_session_summary(),
        }


# Singleton
context_manager = ContextManager()
