"""
Autonomous Agent Code Validator
Runs linting, type checking, tests, and code quality analysis
"""

from __future__ import annotations
import subprocess
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

from src.security import log_event


class ValidationLevel(Enum):
    """Validation severity levels"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Code validation issue"""
    tool: str  # "pylint", "mypy", "flake8", etc.
    level: ValidationLevel
    file: str
    line: int
    column: int
    code: str  # E501, W292, etc.
    message: str


@dataclass
class ValidationResult:
    """Complete validation result"""
    file_path: str
    valid: bool
    total_issues: int
    errors: List[ValidationIssue]
    warnings: List[ValidationIssue]
    infos: List[ValidationIssue]
    test_results: Optional[TestResult] = None
    quality_score: float = 0.0  # 0-100


@dataclass
class TestResult:
    """Test execution result"""
    passed: int
    failed: int
    errors: int
    skipped: int
    total: int
    duration_ms: float
    coverage_percent: Optional[float] = None
    failed_tests: List[str] = None

    def __post_init__(self):
        if self.failed_tests is None:
            self.failed_tests = []


# ════════════════════════════════════════════════════════════════════════════════
# CODE VALIDATOR
# ════════════════════════════════════════════════════════════════════════════════

class CodeValidator:
    """
    Comprehensive code validation:
    - Linting (pylint, flake8, black)
    - Type checking (mypy)
    - Tests (pytest)
    - Code quality analysis
    """

    def __init__(self, project_root: str = "."):
        self.project_root = pathlib.Path(project_root)
        self.validation_cache: Dict[str, ValidationResult] = {}

    # ── Linting ────────────────────────────────────────────────────

    def _run_pylint(self, file_path: str) -> List[ValidationIssue]:
        """Run pylint on a Python file"""
        try:
            result = subprocess.run(
                ["pylint", "--output-format=json", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 32:  # No module named
                return []

            issues = []
            try:
                messages = json.loads(result.stdout)
                for msg in messages:
                    level_map = {
                        "error": ValidationLevel.ERROR,
                        "warning": ValidationLevel.WARNING,
                        "convention": ValidationLevel.INFO,
                        "refactor": ValidationLevel.INFO,
                    }
                    issues.append(ValidationIssue(
                        tool="pylint",
                        level=level_map.get(msg.get("type", ""), ValidationLevel.WARNING),
                        file=msg.get("path", file_path),
                        line=msg.get("line", 0),
                        column=msg.get("column", 0),
                        code=msg.get("symbol", ""),
                        message=msg.get("message", "")
                    ))
            except json.JSONDecodeError:
                pass

            return issues

        except (subprocess.TimeoutExpired, FileNotFoundError):
            log_event("PYLINT_ERROR", f"{file_path}: timeout or not installed")
            return []

    def _run_flake8(self, file_path: str) -> List[ValidationIssue]:
        """Run flake8 on a Python file"""
        try:
            result = subprocess.run(
                ["flake8", "--format=json", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            issues = []
            try:
                messages = json.loads(result.stdout)
                for msg in messages:
                    level = ValidationLevel.ERROR if msg["code"].startswith("E") else ValidationLevel.WARNING
                    issues.append(ValidationIssue(
                        tool="flake8",
                        level=level,
                        file=msg.get("filename", file_path),
                        line=msg.get("line_number", 0),
                        column=msg.get("column_number", 0),
                        code=msg.get("code", ""),
                        message=msg.get("text", "")
                    ))
            except json.JSONDecodeError:
                pass

            return issues

        except (subprocess.TimeoutExpired, FileNotFoundError):
            log_event("FLAKE8_ERROR", f"{file_path}: timeout or not installed")
            return []

    def _run_mypy(self, file_path: str) -> List[ValidationIssue]:
        """Run mypy for type checking"""
        try:
            result = subprocess.run(
                ["mypy", "--json-report=/tmp/mypy_out", file_path],
                capture_output=True,
                text=True,
                timeout=15
            )

            issues = []
            # Parse mypy output (line:col: error: message)
            for line in result.stdout.split("\n"):
                if not line.strip():
                    continue
                match = re.match(r"^(.+):(\d+):(\d+):\s*(\w+):\s*(.+)$", line)
                if match:
                    path, line_no, col, severity, msg = match.groups()
                    level = ValidationLevel.ERROR if severity == "error" else ValidationLevel.WARNING
                    issues.append(ValidationIssue(
                        tool="mypy",
                        level=level,
                        file=path,
                        line=int(line_no),
                        column=int(col),
                        code=severity,
                        message=msg
                    ))

            return issues

        except (subprocess.TimeoutExpired, FileNotFoundError):
            log_event("MYPY_ERROR", f"{file_path}: timeout or not installed")
            return []

    def _check_black_formatting(self, file_path: str) -> List[ValidationIssue]:
        """Check if file matches black formatting"""
        try:
            result = subprocess.run(
                ["black", "--check", "--quiet", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return [ValidationIssue(
                    tool="black",
                    level=ValidationLevel.WARNING,
                    file=file_path,
                    line=1,
                    column=0,
                    code="format",
                    message="File does not match black formatting standards"
                )]
            return []

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    # ── Test Running ───────────────────────────────────────────────

    def _run_pytest(self, file_path: str) -> Optional[TestResult]:
        """Run pytest on a Python file or test directory"""
        try:
            result = subprocess.run(
                ["pytest", file_path, "--tb=short", "--json-report",
                 "--json-report-file=/tmp/pytest_report.json", "-v"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.project_root
            )

            # Try to parse JSON report
            try:
                report_path = pathlib.Path("/tmp/pytest_report.json")
                if report_path.exists():
                    report = json.loads(report_path.read_text())
                    summary = report.get("summary", {})
                    return TestResult(
                        passed=summary.get("passed", 0),
                        failed=summary.get("failed", 0),
                        errors=summary.get("error", 0),
                        skipped=summary.get("skipped", 0),
                        total=summary.get("total", 0),
                        duration_ms=int(report.get("duration", 0) * 1000)
                    )
            except (json.JSONDecodeError, KeyError):
                pass

            # Fallback: parse text output
            passed = len(re.findall(r"PASSED", result.stdout))
            failed = len(re.findall(r"FAILED", result.stdout))
            errors = len(re.findall(r"ERROR", result.stdout))

            return TestResult(
                passed=passed,
                failed=failed,
                errors=errors,
                skipped=0,
                total=passed + failed + errors,
                duration_ms=0
            )

        except (subprocess.TimeoutExpired, FileNotFoundError):
            log_event("PYTEST_ERROR", f"{file_path}: timeout or not installed")
            return None

    # ── Security Checks ────────────────────────────────────────────

    def _check_security(self, file_path: str) -> List[ValidationIssue]:
        """Check for common security issues"""
        try:
            result = subprocess.run(
                ["bandit", "-f", "json", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            issues = []
            try:
                data = json.loads(result.stdout)
                for issue in data.get("results", []):
                    issues.append(ValidationIssue(
                        tool="bandit",
                        level=ValidationLevel.WARNING,
                        file=file_path,
                        line=issue.get("line_number", 0),
                        column=0,
                        code=issue.get("test_id", ""),
                        message=issue.get("issue_text", "")
                    ))
            except json.JSONDecodeError:
                pass

            return issues

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    # ── Code Complexity ────────────────────────────────────────────

    def _check_complexity(self, file_path: str) -> List[ValidationIssue]:
        """Check code complexity (McCabe)"""
        try:
            result = subprocess.run(
                ["radon", "cc", "-j", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            issues = []
            try:
                data = json.loads(result.stdout)
                for func_key, metrics in data.items():
                    if isinstance(metrics, dict):
                        complexity = metrics.get("complexity", 0)
                        if complexity > 10:  # High complexity threshold
                            issues.append(ValidationIssue(
                                tool="radon",
                                level=ValidationLevel.WARNING,
                                file=file_path,
                                line=0,
                                column=0,
                                code="high-complexity",
                                message=f"{func_key} has complexity {complexity}"
                            ))
            except json.JSONDecodeError:
                pass

            return issues

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    # ── Quality Score ──────────────────────────────────────────────

    def _calculate_quality_score(self, result: ValidationResult) -> float:
        """Calculate overall code quality score (0-100)"""
        score = 100.0

        # Deduct for each issue type
        score -= result.total_issues * 0.5  # 0.5 per issue

        # Deduct for errors heavily
        score -= len(result.errors) * 5

        # Deduct for test failures
        if result.test_results:
            test_fail_rate = (result.test_results.failed + result.test_results.errors) / max(
                result.test_results.total, 1
            )
            score -= test_fail_rate * 20

        return max(score, 0.0)

    # ── Main Validation ────────────────────────────────────────────

    def validate_file(self, file_path: str, run_tests: bool = False) -> ValidationResult:
        """Validate a Python file comprehensively"""
        try:
            path = self.project_root / file_path
            if not path.exists():
                log_event("VALIDATION_ERROR", f"{file_path}: file not found")
                return ValidationResult(
                    file_path=file_path,
                    valid=False,
                    total_issues=1,
                    errors=[],
                    warnings=[],
                    infos=[]
                )

            issues = []

            # Run all linters
            issues.extend(self._run_pylint(str(path)))
            issues.extend(self._run_flake8(str(path)))
            issues.extend(self._run_mypy(str(path)))
            issues.extend(self._check_black_formatting(str(path)))
            issues.extend(self._check_security(str(path)))
            issues.extend(self._check_complexity(str(path)))

            # Separate by level
            errors = [i for i in issues if i.level == ValidationLevel.ERROR]
            warnings = [i for i in issues if i.level == ValidationLevel.WARNING]
            infos = [i for i in issues if i.level == ValidationLevel.INFO]

            # Run tests if requested
            test_result = None
            if run_tests:
                test_result = self._run_pytest(str(path))

            result = ValidationResult(
                file_path=file_path,
                valid=len(errors) == 0,
                total_issues=len(issues),
                errors=errors,
                warnings=warnings,
                infos=infos,
                test_results=test_result,
                quality_score=0.0
            )

            # Calculate quality score
            result.quality_score = self._calculate_quality_score(result)

            # Cache result
            self.validation_cache[file_path] = result

            log_event("VALIDATION_DONE", f"{file_path}: {len(errors)} errors, {len(warnings)} warnings")
            return result

        except Exception as e:
            log_event("VALIDATION_EXCEPTION", f"{file_path}: {str(e)}")
            return ValidationResult(
                file_path=file_path,
                valid=False,
                total_issues=1,
                errors=[],
                warnings=[],
                infos=[]
            )

    def get_validation_summary(self, result: ValidationResult) -> str:
        """Get human-readable validation summary"""
        lines = [
            f"📋 Validation: {result.file_path}",
            f"   Status: {'✓ VALID' if result.valid else '✗ INVALID'}",
            f"   Quality Score: {result.quality_score:.1f}/100",
            f"   Total Issues: {result.total_issues}",
            f"     • Errors: {len(result.errors)}",
            f"     • Warnings: {len(result.warnings)}",
            f"     • Infos: {len(result.infos)}",
        ]

        if result.test_results:
            tr = result.test_results
            lines.append(f"   Tests: {tr.passed}/{tr.total} passed")
            if tr.failed + tr.errors > 0:
                lines.append(f"     • Failed: {tr.failed}, Errors: {tr.errors}")

        if result.errors:
            lines.append("\n   🔴 Errors:")
            for err in result.errors[:5]:
                lines.append(f"     {err.file}:{err.line} [{err.code}] {err.message}")
            if len(result.errors) > 5:
                lines.append(f"     ... and {len(result.errors) - 5} more")

        return "\n".join(lines)

    def get_cached_result(self, file_path: str) -> Optional[ValidationResult]:
        """Get cached validation result"""
        return self.validation_cache.get(file_path)


# Singleton
code_validator = CodeValidator()
