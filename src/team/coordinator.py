"""
Franz Developer Team Coordinator
Multi-agent orchestration and task dispatch system
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from enum import Enum

from src.team.agent_specs import DEVELOPER_TEAM, get_agent, list_agents
from src.classifier import classify, TaskType
from src.security import log_event

# ════════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ════════════════════════════════════════════════════════════════════════════════

class AgentStatus(Enum):
    """Agent státusz"""
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentResponse:
    """Egy ágent válasza"""
    agent_id: str
    agent_name: str
    status: AgentStatus
    output: str
    confidence: float = 0.0
    reasoning: str = ""
    time_ms: float = 0.0


@dataclass
class TeamDecision:
    """Csapat döntése"""
    task: str
    primary_agent: str
    supporting_agents: List[str]
    reasoning: str
    priority: int


@dataclass
class TeamReport:
    """Csapat riport"""
    task: str
    decision: TeamDecision
    responses: List[AgentResponse]
    synthesis: str
    overall_confidence: float
    total_time_ms: float


# ════════════════════════════════════════════════════════════════════════════════
# TEAM COORDINATOR
# ════════════════════════════════════════════════════════════════════════════════

class DeveloperTeamCoordinator:
    """
    Franz Developer Team Manager — koordinálja a 6 ágent csapatot.

    Workflow:
    1. Classify task → determine primary agent
    2. Dispatch to primary + supporting agents
    3. Collect responses
    4. Synthesize & validate
    5. Generate team report
    """

    def __init__(self):
        self.team = DEVELOPER_TEAM
        self.team_size = len(self.team)
        self.total_tasks = 0
        self.agent_workload: Dict[str, int] = {aid: 0 for aid in self.team.keys()}

    def _classify_for_team(self, task: str) -> TeamDecision:
        """
        Feladat osztályozása csapat szemszögéből.
        Kiválaszt primary + supporting agenteket.
        """
        classification = classify(task)
        task_lower = task.lower()

        # Agent selection logic
        agents_by_type = {
            "code": ["llm-engineer", "backend-expert", "frontend-designer"],
            "backend": ["backend-expert", "devops-specialist", "agent-researcher"],
            "frontend": ["frontend-designer", "ui-programmer", "llm-engineer"],
            "ui": ["ui-programmer", "frontend-designer"],
            "api": ["backend-expert", "devops-specialist"],
            "deploy": ["devops-specialist", "backend-expert"],
            "research": ["agent-researcher", "llm-engineer"],
            "optimize": ["llm-engineer", "frontend-designer", "backend-expert"],
            "test": ["agent-researcher", "frontend-designer", "backend-expert"],
            "architecture": ["agent-researcher", "backend-expert", "devops-specialist"],
        }

        # Keywords for agent detection
        keywords = {
            "llm": ["model", "prompt", "fine-tune", "token", "optimization"],
            "ui": ["design", "component", "interface", "ux", "layout"],
            "backend": ["api", "database", "schema", "query", "microservice"],
            "frontend": ["react", "component", "performance", "javascript"],
            "agent": ["agent", "workflow", "autonomous", "multi-step", "orchestration"],
            "devops": ["deploy", "docker", "kubernetes", "ci/cd", "monitoring"],
        }

        # Score each agent
        agent_scores: Dict[str, int] = {aid: 0 for aid in self.team.keys()}

        for agent_type, keyword_list in keywords.items():
            for keyword in keyword_list:
                if keyword in task_lower:
                    for aid in self.team.keys():
                        if agent_type in aid:
                            agent_scores[aid] += 2

        # Task-specific routing
        if classification.type == "code":
            agent_scores["llm-engineer"] += 5
            agent_scores["backend-expert"] += 3
        elif classification.type == "agentic":
            agent_scores["agent-researcher"] += 5
        elif classification.type == "research":
            agent_scores["llm-engineer"] += 3
            agent_scores["agent-researcher"] += 2

        # Select primary + supporting
        sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_agents[0][0] if sorted_agents[0][1] > 0 else "agent-researcher"
        supporting = [
            aid for aid, score in sorted_agents[1:3]
            if score > 0 and aid != primary
        ]

        return TeamDecision(
            task=task[:200],
            primary_agent=primary,
            supporting_agents=supporting,
            reasoning=f"Classified as '{classification.type}', routed to {primary} + {supporting}",
            priority=classification.confidence * 10
        )

    def dispatch_to_agent(
        self,
        agent_id: str,
        task: str,
        context: str = "",
        model: str = "ollama",
    ) -> AgentResponse:
        """
        Egy ágenthez feladatot delegálni.
        (Mock implementation — valós rendszerben LLM hívás)
        """
        agent = get_agent(agent_id)
        if not agent:
            return AgentResponse(
                agent_id=agent_id,
                agent_name="Unknown",
                status=AgentStatus.ERROR,
                output=f"Agent '{agent_id}' not found",
                confidence=0.0
            )

        self.agent_workload[agent_id] += 1
        start_time = time.time()

        try:
            log_event("AGENT_DISPATCH", f"{agent.name} ← {task[:50]}...")

            # Rendszerprompt + task
            system_msg = agent.system_prompt
            user_msg = f"Feladat: {task}"
            if context:
                user_msg += f"\n\nKontextus:\n{context}"

            # Mock LLM response (real system would call gateway)
            output = self._mock_agent_response(agent, task)

            elapsed_ms = (time.time() - start_time) * 1000

            response = AgentResponse(
                agent_id=agent_id,
                agent_name=agent.name,
                status=AgentStatus.DONE,
                output=output,
                confidence=0.75,
                reasoning=f"Processed via {agent.role}",
                time_ms=elapsed_ms
            )

            log_event("AGENT_DONE", f"{agent.name}: {len(output)} chars in {elapsed_ms:.0f}ms")
            return response

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            log_event("AGENT_ERROR", f"{agent.name}: {str(e)}")
            return AgentResponse(
                agent_id=agent_id,
                agent_name=agent.name,
                status=AgentStatus.ERROR,
                output=f"Error: {str(e)}",
                confidence=0.0,
                time_ms=elapsed_ms
            )

    def _mock_agent_response(self, agent, task: str) -> str:
        """
        Mock agent válasz — valós rendszerben LLM hívás történne.
        Ez a demo céljából szimulál egy szakértő választ.
        """
        task_lower = task.lower()

        # Agent-specific response templates
        if agent.id == "backend-expert":
            if "api" in task_lower:
                return (
                    "## API Design Recommendation\n\n"
                    "### Endpoint Definition\n"
                    "```\nGET    /api/v1/resource/{id}\n"
                    "POST   /api/v1/resource\n"
                    "PUT    /api/v1/resource/{id}\n"
                    "DELETE /api/v1/resource/{id}\n"
                    "```\n\n"
                    "### Schema Design\n"
                    "- Primary keys (UUID)\n"
                    "- Foreign key relationships\n"
                    "- Appropriate indexing for query performance\n"
                    "- Consider denormalization for high-read workloads\n\n"
                    "### Security Considerations\n"
                    "- Authentication (OAuth2/JWT)\n"
                    "- Rate limiting\n"
                    "- Input validation & sanitization"
                )
        elif agent.id == "llm-engineer":
            if "model" in task_lower or "prompt" in task_lower:
                return (
                    "## LLM Optimization Recommendation\n\n"
                    "### Model Selection\n"
                    "- Task: code generation → qwen2.5-coder:7b (high quality)\n"
                    "- Task: fast inference → qwen2.5-coder:1.5b (speed)\n"
                    "- Temperature tuning: 0.2 (precise), 0.4 (creative)\n\n"
                    "### Prompt Engineering\n"
                    "- Add chain-of-thought reasoning\n"
                    "- Provide clear instructions\n"
                    "- Include examples (few-shot prompting)\n"
                    "- Structure output with explicit format\n\n"
                    "### Token Efficiency\n"
                    "- Compress context to relevant info only\n"
                    "- Use summarization for long documents"
                )
        elif agent.id == "frontend-designer":
            if "react" in task_lower or "component" in task_lower:
                return (
                    "## React Component Design\n\n"
                    "```jsx\nfunction TodoList() {\n"
                    "  const [todos, setTodos] = useState([]);\n\n"
                    "  useEffect(() => {\n"
                    "    const saved = localStorage.getItem('todos');\n"
                    "    if (saved) setTodos(JSON.parse(saved));\n"
                    "  }, []);\n\n"
                    "  const addTodo = (text) => {\n"
                    "    const updated = [...todos, { id: Date.now(), text }];\n"
                    "    setTodos(updated);\n"
                    "    localStorage.setItem('todos', JSON.stringify(updated));\n"
                    "  };\n\n"
                    "  return (\n"
                    "    <div className='todo-list'>\n"
                    "      {todos.map(t => <TodoItem key={t.id} todo={t} />)}\n"
                    "    </div>\n"
                    "  );\n}\n```\n\n"
                    "### Performance Tips\n"
                    "- Memoize expensive computations\n"
                    "- Lazy load components\n"
                    "- Use React.memo for PureComponent behavior"
                )
        elif agent.id == "ui-programmer":
            if "ui" in task_lower or "design" in task_lower:
                return (
                    "## UI Component System\n\n"
                    "### Design Tokens\n"
                    "- Colors: primary (#0066cc), secondary (#f0f0f0)\n"
                    "- Spacing: 4px base unit (4, 8, 16, 24, 32)\n"
                    "- Typography: sans-serif, sizes 12px-24px\n\n"
                    "### Reusable Components\n"
                    "- Button (primary, secondary, disabled states)\n"
                    "- Input (text, email, password)\n"
                    "- Card (with header, body, footer)\n"
                    "- Modal (with overlay, animations)\n\n"
                    "### Accessibility Checklist\n"
                    "- WCAG 2.1 AA compliance\n"
                    "- Keyboard navigation\n"
                    "- Screen reader support"
                )
        elif agent.id == "agent-researcher":
            if "workflow" in task_lower or "autonomous" in task_lower:
                return (
                    "## Agentic Workflow Design\n\n"
                    "### Task Decomposition\n"
                    "1. Parse input → understand requirements\n"
                    "2. Generate plan → identify subgoals\n"
                    "3. Execute steps → call appropriate tools\n"
                    "4. Validate → check progress\n"
                    "5. Synthesize → generate final output\n\n"
                    "### Tool Orchestration\n"
                    "- Define tool dependencies\n"
                    "- Handle conditional branching\n"
                    "- Implement retry logic for failures\n\n"
                    "### Autonomy Metrics\n"
                    "- Completion rate: % tasks finished without help\n"
                    "- Success rate: % solutions valid/correct\n"
                    "- Efficiency: steps/task ratio"
                )
        else:  # devops-specialist
            if "deploy" in task_lower or "docker" in task_lower:
                return (
                    "## Deployment Pipeline\n\n"
                    "```dockerfile\nFROM python:3.11-slim\n"
                    "WORKDIR /app\n"
                    "COPY requirements.txt .\n"
                    "RUN pip install -r requirements.txt\n"
                    "COPY . .\n"
                    "CMD [\"python\", \"-m\", \"src.cli\"]\n"
                    "```\n\n"
                    "### CI/CD Pipeline\n"
                    "- Build: Docker image, run tests\n"
                    "- Push: Registry upload\n"
                    "- Deploy: Kubernetes rollout\n"
                    "- Monitor: Health checks, metrics\n\n"
                    "### Infrastructure as Code\n"
                    "- Terraform for cloud resources\n"
                    "- Helm charts for Kubernetes"
                )

        return f"Response from {agent.name} regarding: {task[:60]}..."

    def run_team_task(
        self,
        task: str,
        context: str = "",
        include_supporting: bool = True,
        model: str = "ollama",
    ) -> TeamReport:
        """
        Futtat csapat feladatot.
        1. Classify
        2. Dispatch
        3. Collect responses
        4. Synthesize
        """
        log_event("TEAM_TASK", f"Starting: {task[:60]}...")
        self.total_tasks += 1
        start_time = time.time()

        # Step 1: Classify & decide
        decision = self._classify_for_team(task)
        log_event("TEAM_DISPATCH", f"Primary: {decision.primary_agent}, Supporting: {decision.supporting_agents}")

        # Step 2: Dispatch to agents
        responses: List[AgentResponse] = []

        # Primary agent
        primary_response = self.dispatch_to_agent(
            decision.primary_agent,
            task,
            context,
            model
        )
        responses.append(primary_response)

        # Supporting agents
        if include_supporting:
            for agent_id in decision.supporting_agents[:2]:  # Max 2 supporting
                support_response = self.dispatch_to_agent(
                    agent_id,
                    task,
                    context,
                    model
                )
                responses.append(support_response)

        # Step 3: Synthesize responses
        synthesis = self._synthesize_responses(task, decision, responses)

        # Step 4: Calculate metrics
        total_time = (time.time() - start_time) * 1000
        avg_confidence = sum(r.confidence for r in responses) / len(responses) if responses else 0.0

        report = TeamReport(
            task=task,
            decision=decision,
            responses=responses,
            synthesis=synthesis,
            overall_confidence=avg_confidence,
            total_time_ms=total_time
        )

        log_event("TEAM_DONE", f"Task complete in {total_time:.0f}ms, confidence={avg_confidence:.2f}")
        return report

    def _synthesize_responses(self, task: str, decision: TeamDecision, responses: List[AgentResponse]) -> str:
        """Szintetizáld az ágent válaszait egy unified reportba"""
        lines = [
            "# 👥 FRANZ DEVELOPER TEAM REPORT\n",
            f"## Task\n{task}\n",
            f"## Decision\n"
            f"- **Primary Agent**: {decision.primary_agent}\n"
            f"- **Supporting Agents**: {', '.join(decision.supporting_agents) or 'None'}\n"
            f"- **Reasoning**: {decision.reasoning}\n",
        ]

        for i, resp in enumerate(responses, 1):
            lines.append(f"\n## Response {i}: {resp.agent_name}\n")
            lines.append(f"- **Status**: {resp.status.value}\n")
            lines.append(f"- **Confidence**: {resp.confidence:.0%}\n")
            lines.append(f"- **Time**: {resp.time_ms:.0f}ms\n")
            lines.append(f"\n{resp.output}\n")

        return "\n".join(lines)

    def team_status(self) -> Dict[str, Any]:
        """Csapat státusza"""
        return {
            "team_size": self.team_size,
            "total_tasks": self.total_tasks,
            "agents": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "role": agent.role,
                    "tasks": self.agent_workload[agent.id],
                }
                for agent in list_agents()
            ],
            "total_workload": sum(self.agent_workload.values()),
        }


# Singleton
developer_team = DeveloperTeamCoordinator()
