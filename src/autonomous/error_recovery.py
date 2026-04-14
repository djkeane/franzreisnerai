"""
Autonomous Agent Error Recovery
Parses exceptions, analyzes root causes, suggests fixes, triggers rollback
"""

from __future__ import annotations
import re
import traceback
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

from src.security import log_event
from src.autonomous.context_manager import ContextManager


class ErrorType(Enum):
    """Error classification"""
    SYNTAX_ERROR = "syntax"
    IMPORT_ERROR = "import"
    TYPE_ERROR = "type"
    RUNTIME_ERROR = "runtime"
    ASSERTION_ERROR = "assertion"
    TIMEOUT_ERROR = "timeout"
    RESOURCE_ERROR = "resource"
    PERMISSION_ERROR = "permission"
    UNKNOWN = "unknown"


@dataclass
class StackFrame:
    """Single frame in stack trace"""
    file: str
    line: int
    function: str
    code: str


@dataclass
class ErrorAnalysis:
    """Parsed and analyzed error"""
    error_type: ErrorType
    message: str
    stack_frames: List[StackFrame]
    root_file: str
    root_line: int
    root_function: str
    error_class: str
    suggestions: List[str]
    severity: int  # 1-10, 10 is critical


@dataclass
class RecoveryAction:
    """Suggested recovery action"""
    action_type: str  # "fix_code", "rollback", "retry", "adjust_params", "install_dep"
    description: str
    auto_applicable: bool  # Can be applied without user input
    code_fix: Optional[str] = None  # Suggested code change
    bash_command: Optional[str] = None  # Command to run
    confidence: float = 0.5  # 0-1


# ════════════════════════════════════════════════════════════════════════════════
# ERROR RECOVERY ENGINE
# ════════════════════════════════════════════════════════════════════════════════

class ErrorRecovery:
    """
    Sophisticated error recovery:
    - Parse and analyze stack traces
    - Identify root causes
    - Suggest fixes
    - Trigger rollback if needed
    """

    def __init__(self, context_manager: ContextManager):
        self.context = context_manager
        self.error_patterns: Dict[str, ErrorType] = {
            r"SyntaxError": ErrorType.SYNTAX_ERROR,
            r"ImportError|ModuleNotFoundError": ErrorType.IMPORT_ERROR,
            r"TypeError": ErrorType.TYPE_ERROR,
            r"RuntimeError|ValueError|AttributeError|KeyError|IndexError": ErrorType.RUNTIME_ERROR,
            r"AssertionError": ErrorType.ASSERTION_ERROR,
            r"TimeoutError": ErrorType.TIMEOUT_ERROR,
            r"MemoryError|OSError": ErrorType.RESOURCE_ERROR,
            r"PermissionError": ErrorType.PERMISSION_ERROR,
        }
        self.fix_templates: Dict[ErrorType, List[str]] = {
            ErrorType.IMPORT_ERROR: [
                "Install missing package with pip",
                "Check package name spelling",
                "Add __init__.py to package directory",
                "Update Python path or PYTHONPATH",
            ],
            ErrorType.TYPE_ERROR: [
                "Add type hints to function parameters",
                "Convert value to correct type",
                "Check None values before using",
                "Use isinstance() for type checking",
            ],
            ErrorType.RUNTIME_ERROR: [
                "Check array/dict indices exist",
                "Verify variable is initialized before use",
                "Handle edge cases (empty lists, None values)",
                "Add error handling with try/except",
            ],
            ErrorType.SYNTAX_ERROR: [
                "Fix indentation (use 4 spaces)",
                "Check closing brackets/parentheses",
                "Verify correct Python syntax",
                "Use linter to find syntax issues",
            ],
            ErrorType.RESOURCE_ERROR: [
                "Check available disk space and memory",
                "Optimize memory usage",
                "Close unused file handles",
                "Reduce data processing batch size",
            ],
            ErrorType.PERMISSION_ERROR: [
                "Fix file/directory permissions with chmod",
                "Run with elevated privileges if needed",
                "Check file ownership",
                "Ensure write permissions on output directory",
            ],
        }

    # ── Stack Trace Parsing ─────────────────────────────────────────

    def _parse_stack_trace(self, trace_text: str) -> Tuple[List[StackFrame], str, str]:
        """Parse Python stack trace into structured frames"""
        frames = []
        error_line = ""
        error_class = ""

        lines = trace_text.split("\n")
        for i, line in enumerate(lines):
            # Extract error class and message
            match = re.match(r"^(\w+(?:Error|Exception)):\s*(.+)$", line)
            if match:
                error_class = match.group(1)
                error_line = match.group(2)
                continue

            # Extract frame info
            match = re.match(r'^\s+File "(.+?)", line (\d+), in (.+?)$', line)
            if match:
                file_path = match.group(1)
                line_no = int(match.group(2))
                function = match.group(3)

                # Get code snippet (next line)
                code = ""
                if i + 1 < len(lines):
                    code = lines[i + 1].strip()

                frames.append(StackFrame(
                    file=file_path,
                    line=line_no,
                    function=function,
                    code=code
                ))

        return frames, error_class, error_line

    # ── Error Classification ────────────────────────────────────────

    def _classify_error(self, error_class: str, message: str) -> ErrorType:
        """Classify error by type"""
        full_text = f"{error_class} {message}".lower()

        for pattern, error_type in self.error_patterns.items():
            if re.search(pattern, full_text, re.IGNORECASE):
                return error_type

        return ErrorType.UNKNOWN

    def _estimate_severity(self, error_type: ErrorType, frames_count: int) -> int:
        """Estimate error severity (1-10)"""
        severity_base = {
            ErrorType.SYNTAX_ERROR: 8,
            ErrorType.IMPORT_ERROR: 7,
            ErrorType.TYPE_ERROR: 6,
            ErrorType.PERMISSION_ERROR: 7,
            ErrorType.RESOURCE_ERROR: 8,
            ErrorType.TIMEOUT_ERROR: 6,
            ErrorType.RUNTIME_ERROR: 5,
            ErrorType.ASSERTION_ERROR: 4,
            ErrorType.UNKNOWN: 5,
        }

        severity = severity_base.get(error_type, 5)
        # Stack depth indicates complexity
        severity += min(frames_count // 3, 2)
        return min(severity, 10)

    # ── Suggestion Generation ───────────────────────────────────────

    def _generate_suggestions(self, analysis: ErrorAnalysis) -> List[str]:
        """Generate fix suggestions based on error type"""
        suggestions = self.fix_templates.get(analysis.error_type, [])

        # Add context-specific suggestions
        if "module" in analysis.message.lower() or "import" in analysis.message.lower():
            module = re.search(r"module '([^']+)'", analysis.message)
            if module:
                suggestions.insert(0, f"Install or check package: {module.group(1)}")

        if "none" in analysis.message.lower():
            suggestions.insert(0, "Check for None values and add null checks")

        if "index" in analysis.message.lower():
            suggestions.insert(0, "Verify array bounds and index values")

        return suggestions

    # ── Root Cause Analysis ─────────────────────────────────────────

    def _find_root_cause(self, frames: List[StackFrame]) -> StackFrame:
        """Find root cause frame (deepest application code frame)"""
        if not frames:
            return StackFrame("unknown", 0, "unknown", "")

        # Prefer deepest frame, exclude standard library
        for frame in reversed(frames):
            if "site-packages" not in frame.file and "lib/python" not in frame.file:
                return frame

        return frames[-1]

    # ── Main Analysis ──────────────────────────────────────────────

    def analyze_error(self, exception_text: str) -> ErrorAnalysis:
        """Analyze an exception and return structured analysis"""
        frames, error_class, error_message = self._parse_stack_trace(exception_text)
        error_type = self._classify_error(error_class, error_message)
        root_frame = self._find_root_cause(frames)
        severity = self._estimate_severity(error_type, len(frames))

        analysis = ErrorAnalysis(
            error_type=error_type,
            message=error_message,
            stack_frames=frames,
            root_file=root_frame.file,
            root_line=root_frame.line,
            root_function=root_frame.function,
            error_class=error_class,
            suggestions=[],
            severity=severity
        )

        analysis.suggestions = self._generate_suggestions(analysis)
        log_event("ERROR_ANALYZED", f"{error_class}: severity={severity}, type={error_type.value}")
        return analysis

    # ── Recovery Decision Making ────────────────────────────────────

    def suggest_recovery(self, analysis: ErrorAnalysis) -> List[RecoveryAction]:
        """Suggest recovery actions"""
        actions = []

        # Syntax errors → try to fix automatically
        if analysis.error_type == ErrorType.SYNTAX_ERROR:
            actions.append(RecoveryAction(
                action_type="fix_code",
                description="Fix indentation or syntax issues automatically",
                auto_applicable=True,
                confidence=0.6
            ))

        # Import errors → try to install missing package
        if analysis.error_type == ErrorType.IMPORT_ERROR:
            match = re.search(r"module '([^']+)'", analysis.message)
            if match:
                package = match.group(1).split(".")[0]
                actions.append(RecoveryAction(
                    action_type="install_dep",
                    description=f"Install missing package: {package}",
                    bash_command=f"pip install {package}",
                    auto_applicable=False,
                    confidence=0.8
                ))

        # Runtime errors with test failures → adjust parameters
        if analysis.error_type == ErrorType.RUNTIME_ERROR:
            actions.append(RecoveryAction(
                action_type="adjust_params",
                description="Try with adjusted parameters or smaller data",
                auto_applicable=False,
                confidence=0.5
            ))

        # Resource errors → rollback and retry
        if analysis.error_type == ErrorType.RESOURCE_ERROR:
            actions.append(RecoveryAction(
                action_type="rollback",
                description="Rollback to previous stable state",
                auto_applicable=True,
                confidence=0.7
            ))

        # Timeout → retry with increased timeout
        if analysis.error_type == ErrorType.TIMEOUT_ERROR:
            actions.append(RecoveryAction(
                action_type="retry",
                description="Retry with increased timeout or reduced scope",
                auto_applicable=False,
                confidence=0.6
            ))

        # If severity is high and no other actions, suggest rollback
        if not actions and analysis.severity >= 8:
            actions.append(RecoveryAction(
                action_type="rollback",
                description="Rollback to previous state due to severity",
                auto_applicable=True,
                confidence=0.5
            ))

        return actions

    # ── Recovery Execution ─────────────────────────────────────────

    def execute_auto_recovery(self, analysis: ErrorAnalysis, actions: List[RecoveryAction]) -> bool:
        """Execute auto-applicable recovery actions"""
        for action in actions:
            if not action.auto_applicable:
                continue

            if action.action_type == "rollback":
                if self.context.can_rollback():
                    log_event("AUTO_RECOVERY", "Triggering rollback")
                    self.context.rollback_to_previous()
                    return True

        return False

    def get_recovery_summary(self, analysis: ErrorAnalysis, actions: List[RecoveryAction]) -> str:
        """Get human-readable recovery summary"""
        lines = [
            f"🔍 Error Analysis",
            f"   Type: {analysis.error_type.value.upper()}",
            f"   Class: {analysis.error_class}",
            f"   Message: {analysis.message}",
            f"   Severity: {'🔴' * (analysis.severity // 3)} ({analysis.severity}/10)",
            f"\n📍 Root Cause",
            f"   File: {analysis.root_file}:{analysis.root_line}",
            f"   Function: {analysis.root_function}",
            f"   Code: {analysis.stack_frames[-1].code if analysis.stack_frames else 'N/A'}",
            f"\n💡 Suggestions",
        ]

        for suggestion in analysis.suggestions[:3]:
            lines.append(f"   • {suggestion}")

        lines.append(f"\n🔧 Recovery Actions")
        for action in actions:
            auto_str = "AUTO" if action.auto_applicable else "MANUAL"
            lines.append(f"   • [{auto_str}] {action.description}")
            if action.bash_command:
                lines.append(f"     $ {action.bash_command}")

        return "\n".join(lines)


# Singleton
def create_error_recovery(context_manager: Optional[ContextManager] = None) -> ErrorRecovery:
    """Create error recovery with context manager"""
    if context_manager is None:
        from src.autonomous.context_manager import context_manager as default_context
        context_manager = default_context
    return ErrorRecovery(context_manager)
