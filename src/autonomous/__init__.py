"""Franz Autonomous Agent Framework"""

from src.autonomous.context_manager import (
    ContextManager,
    FileContext,
    FileState,
    GitSnapshot,
    SessionMemory,
    context_manager,
)
from src.autonomous.code_validator import (
    CodeValidator,
    ValidationResult,
    ValidationIssue,
    ValidationLevel,
    TestResult,
    code_validator,
)
from src.autonomous.error_recovery import (
    ErrorRecovery,
    ErrorAnalysis,
    ErrorType,
    RecoveryAction,
    create_error_recovery,
)
from src.autonomous.dependency_manager import (
    DependencyManager,
    Dependency,
    DependencyType,
    RequirementsFile,
    VirtualEnv,
    dependency_manager,
)
from src.autonomous.strategy_selector import (
    StrategySelector,
    Strategy,
    StrategyPriority,
    StrategyAttempt,
    StrategySequence,
    strategy_selector,
)
from src.autonomous.progress_tracker import (
    ProgressTracker,
    TaskProgress,
    TaskPhase,
    PhaseMetrics,
    ProgressCheckpoint,
    progress_tracker,
)
from src.autonomous.execution_engine import (
    AutonomousExecutionEngine,
    ExecutionStatus,
    ExecutionResult,
    execution_engine,
)

__all__ = [
    # Context Manager
    "ContextManager",
    "FileContext",
    "FileState",
    "GitSnapshot",
    "SessionMemory",
    "context_manager",
    # Code Validator
    "CodeValidator",
    "ValidationResult",
    "ValidationIssue",
    "ValidationLevel",
    "TestResult",
    "code_validator",
    # Error Recovery
    "ErrorRecovery",
    "ErrorAnalysis",
    "ErrorType",
    "RecoveryAction",
    "create_error_recovery",
    # Dependency Manager
    "DependencyManager",
    "Dependency",
    "DependencyType",
    "RequirementsFile",
    "VirtualEnv",
    "dependency_manager",
    # Strategy Selector
    "StrategySelector",
    "Strategy",
    "StrategyPriority",
    "StrategyAttempt",
    "StrategySequence",
    "strategy_selector",
    # Progress Tracker
    "ProgressTracker",
    "TaskProgress",
    "TaskPhase",
    "PhaseMetrics",
    "ProgressCheckpoint",
    "progress_tracker",
    # Execution Engine
    "AutonomousExecutionEngine",
    "ExecutionStatus",
    "ExecutionResult",
    "execution_engine",
]
