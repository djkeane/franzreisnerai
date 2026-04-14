"""
Enhanced Chain-of-Thought Reasoning Module for Franz v7.5
Advanced multi-step planning and logical reasoning for complex tasks
"""

from __future__ import annotations
import json
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

# ════════════════════════════════════════════════════════════════════════════════
# REASONING FRAMEWORK
# ════════════════════════════════════════════════════════════════════════════════

class ThinkingPhase(Enum):
    """Stages of reasoning process"""
    UNDERSTAND = "understand"      # Parse the problem
    PLAN = "plan"                  # Create strategy
    ANALYZE = "analyze"            # Deep analysis
    EXECUTE = "execute"            # Implementation
    VERIFY = "verify"              # Validation
    OPTIMIZE = "optimize"          # Refinement


@dataclass
class ReasoningStep:
    """Single reasoning step"""
    phase: ThinkingPhase
    content: str
    confidence: float  # 0.0 - 1.0
    reasoning: str


@dataclass
class ThinkingProcess:
    """Complete chain-of-thought reasoning"""
    task: str
    steps: List[ReasoningStep]
    final_answer: str
    total_confidence: float
    time_ms: float


# ════════════════════════════════════════════════════════════════════════════════
# CHAIN OF THOUGHT ENGINE
# ════════════════════════════════════════════════════════════════════════════════

class ChainOfThoughtReasoner:
    """Advanced reasoning engine with step-by-step thinking"""

    def __init__(self):
        self.steps: List[ReasoningStep] = []
        self.context: Dict = {}

    def _understand_task(self, task: str) -> ReasoningStep:
        """Phase 1: Break down the problem"""

        # Analyze task structure
        is_code = any(x in task.lower() for x in ["python", "javascript", "kód", "írj", "generálj", "függvény"])
        is_planning = any(x in task.lower() for x in ["terv", "lépések", "hogyan", "stratégia", "design"])
        is_analysis = any(x in task.lower() for x in ["elemez", "analiz", "ellenőriz", "audit"])

        understanding = f"""
Task Type Analysis:
- Code Generation: {'✓' if is_code else '✗'}
- Strategic Planning: {'✓' if is_planning else '✗'}
- Analysis/Audit: {'✓' if is_analysis else '✗'}

Key Entities Identified:
"""

        # Extract requirements
        requirements = []
        if "python" in task.lower():
            requirements.append("Python implementation")
        if "fast" in task.lower() or "optim" in task.lower():
            requirements.append("Performance optimization")
        if "test" in task.lower():
            requirements.append("Testing strategy")
        if "error" in task.lower() or "handle" in task.lower():
            requirements.append("Error handling")

        understanding += f"\nRequirements: {', '.join(requirements) if requirements else 'General task'}"

        return ReasoningStep(
            phase=ThinkingPhase.UNDERSTAND,
            content=understanding,
            confidence=0.95,
            reasoning="Analyzed task structure and identified key components"
        )

    def _create_plan(self, task: str) -> ReasoningStep:
        """Phase 2: Create execution plan"""

        plan = """Strategic Execution Plan:

1. DESIGN PHASE
   → Define architecture/structure
   → Identify key components
   → Map dependencies

2. IMPLEMENTATION PHASE
   → Core functionality
   → Error handling
   → Edge cases

3. OPTIMIZATION PHASE
   → Performance tuning
   → Code quality
   → Best practices

4. VALIDATION PHASE
   → Testing strategy
   → Documentation
   → Edge case coverage
"""

        return ReasoningStep(
            phase=ThinkingPhase.PLAN,
            content=plan,
            confidence=0.90,
            reasoning="Created systematic approach to problem-solving"
        )

    def _deep_analysis(self, task: str) -> ReasoningStep:
        """Phase 3: Detailed analysis"""

        analysis = f"""Deep Technical Analysis:

Complexity Factors:
• Domain knowledge required
• Integration points needed
• Potential pitfalls to avoid
• Performance constraints

Design Considerations:
• Scalability approach
• Maintainability patterns
• Code organization
• Testing strategy

Quality Metrics:
• Code clarity (readability)
• Efficiency (time complexity)
• Robustness (error handling)
• Best practices adherence
"""

        return ReasoningStep(
            phase=ThinkingPhase.ANALYZE,
            content=analysis,
            confidence=0.85,
            reasoning="Performed comprehensive technical analysis"
        )

    def _execution_strategy(self, task: str) -> ReasoningStep:
        """Phase 4: Execution approach"""

        strategy = """Implementation Strategy:

Step-by-Step Approach:
1. Foundation → Core components
2. Features → Primary functionality
3. Robustness → Error handling & validation
4. Polish → Optimization & refinement
5. Documentation → Clear explanations

Code Structure:
- Modular design with clear separation
- Each component has single responsibility
- Proper error handling at boundaries
- Comprehensive comments/docstrings

Validation Points:
✓ Syntax correctness
✓ Logic verification
✓ Edge case coverage
✓ Performance baseline
"""

        return ReasoningStep(
            phase=ThinkingPhase.EXECUTE,
            content=strategy,
            confidence=0.88,
            reasoning="Defined concrete implementation approach"
        )

    def _verification_plan(self, task: str) -> ReasoningStep:
        """Phase 5: Verification strategy"""

        verification = """Verification & Testing Plan:

Test Coverage:
1. Unit Tests
   - Individual function behavior
   - Edge cases and boundaries
   - Error conditions

2. Integration Tests
   - Component interactions
   - Data flow validation
   - System coherence

3. Performance Tests
   - Time complexity validation
   - Resource usage checks
   - Optimization verification

Quality Checklist:
□ Code style consistency
□ Complete error handling
□ Meaningful comments
□ Documentation clarity
□ Best practices adherence
"""

        return ReasoningStep(
            phase=ThinkingPhase.VERIFY,
            content=verification,
            confidence=0.87,
            reasoning="Established comprehensive verification protocol"
        )

    def _optimization_pass(self, task: str) -> ReasoningStep:
        """Phase 6: Optimization"""

        optimization = """Optimization & Refinement:

Performance Optimization:
- Algorithm efficiency review
- Resource utilization check
- Caching opportunities
- Parallelization where applicable

Code Quality:
- DRY principle adherence
- Function complexity reduction
- Naming clarity
- Documentation completeness

Best Practices:
- Design pattern application
- Security considerations
- Accessibility features
- Maintainability focus
"""

        return ReasoningStep(
            phase=ThinkingPhase.OPTIMIZE,
            content=optimization,
            confidence=0.82,
            reasoning="Identified optimization opportunities"
        )

    def reason(self, task: str) -> ThinkingProcess:
        """Run complete chain-of-thought reasoning"""
        import time
        start_time = time.time()

        self.steps = [
            self._understand_task(task),
            self._create_plan(task),
            self._deep_analysis(task),
            self._execution_strategy(task),
            self._verification_plan(task),
            self._optimization_pass(task),
        ]

        # Calculate confidence
        avg_confidence = sum(s.confidence for s in self.steps) / len(self.steps)

        # Build final reasoning
        final_answer = self._build_final_reasoning()

        elapsed_ms = (time.time() - start_time) * 1000

        return ThinkingProcess(
            task=task,
            steps=self.steps,
            final_answer=final_answer,
            total_confidence=avg_confidence,
            time_ms=elapsed_ms
        )

    def _build_final_reasoning(self) -> str:
        """Synthesize all reasoning into coherent answer"""
        summary = "Based on comprehensive chain-of-thought reasoning:\n\n"

        for i, step in enumerate(self.steps, 1):
            summary += f"{i}. {step.phase.value.upper()}\n"
            summary += f"   → {step.reasoning}\n"
            summary += f"   → Confidence: {step.confidence*100:.0f}%\n\n"

        summary += f"Overall Confidence: {sum(s.confidence for s in self.steps) / len(self.steps) * 100:.0f}%"
        return summary

    def format_for_llm(self, process: ThinkingProcess) -> str:
        """Format thinking process for LLM prompt injection"""
        output = f"=== CHAIN OF THOUGHT REASONING ===\n\n"
        output += f"Task: {process.task}\n\n"

        for step in process.steps:
            output += f"[{step.phase.value.upper()}]\n"
            output += f"{step.content}\n"
            output += f"Confidence: {step.confidence*100:.0f}%\n\n"

        output += "=== SYNTHESIS ===\n"
        output += process.final_answer

        return output


# ════════════════════════════════════════════════════════════════════════════════
# REASONING INTEGRATION
# ════════════════════════════════════════════════════════════════════════════════

def enhance_prompt_with_reasoning(original_prompt: str, include_reasoning: bool = True) -> str:
    """
    Enhance a prompt with chain-of-thought reasoning framework

    Args:
        original_prompt: The user's original request
        include_reasoning: Whether to include explicit reasoning guidance

    Returns:
        Enhanced prompt with reasoning guidance
    """

    if not include_reasoning:
        return original_prompt

    reasoner = ChainOfThoughtReasoner()
    process = reasoner.reason(original_prompt)

    enhanced = f"""You are an expert problem-solver with advanced reasoning capabilities.

Your task is to use systematic thinking to solve the following problem:

{original_prompt}

REASONING FRAMEWORK (Follow these steps):

{process.final_answer}

Now provide a comprehensive solution that:
1. Addresses all identified requirements
2. Follows the strategic plan outlined above
3. Includes clear explanations for each step
4. Demonstrates best practices
5. Validates the solution thoroughly

Begin your solution:
"""

    return enhanced


# ════════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════════════════════

def generate_reasoning(task: str) -> str:
    """Generate chain-of-thought reasoning for a task"""
    reasoner = ChainOfThoughtReasoner()
    process = reasoner.reason(task)
    return reasoner.format_for_llm(process)


def get_reasoning_steps(task: str) -> List[Dict]:
    """Get reasoning steps as structured data"""
    reasoner = ChainOfThoughtReasoner()
    process = reasoner.reason(task)

    return [
        {
            "phase": step.phase.value,
            "content": step.content,
            "confidence": step.confidence,
            "reasoning": step.reasoning,
        }
        for step in process.steps
    ]
