# 👥 Franz Developer Team v8.0 — Comprehensive Guide

**Integration Date**: 2026-04-14  
**Status**: ✅ **FULLY INTEGRATED**  
**Team Size**: 6 Specialized Agents

---

## Overview

Franz now includes a **professional developer team** with 6 specialized agents that can be delegated tasks either individually or as a coordinated team. Each agent has distinct expertise, specialized system prompts, and optimized LLM parameters.

---

## The Developer Team

### 1. 🤖 **LLM Engineer**
**Role**: LLM optimization, model selection, prompt engineering

**Expertise**:
- Model architecture analysis
- Prompt optimization & engineering
- Fine-tuning strategies
- Token efficiency & cost optimization
- Model benchmarking & evaluation
- Context window management
- Temperature & parameter tuning

**System Prompt**: Specialized in technical model analysis and optimization
**Parameters**: `temp=0.2` (ultra-precise), `max_tokens=2500`

**Use Cases**:
- "Optimize the prompt for better code generation"
- "Which model should I use for this task?"
- "How can I reduce token usage?"

---

### 2. 🎨 **UI Programmer**
**Role**: Interface design, component architecture, design systems

**Expertise**:
- UI/UX design principles
- Component libraries & design systems
- Responsive layouts
- Accessibility standards (WCAG)
- Design tokens & theming
- UI testing strategies
- User interaction flows
- Terminal UI design

**System Prompt**: Specialized in design systems and interface implementation
**Parameters**: `temp=0.35` (creative), `max_tokens=2000`

**Use Cases**:
- "Design a responsive navbar component"
- "Create an accessible form layout"
- "Build a design system with tokens"

---

### 3. ⚙️ **Backend Expert**
**Role**: API design, database architecture, infrastructure

**Expertise**:
- REST/GraphQL API design
- Database schema design
- Query optimization
- Authentication & authorization
- Microservices architecture
- Caching strategies
- Performance optimization
- Infrastructure as Code

**System Prompt**: Specialized in scalable backend architecture
**Parameters**: `temp=0.25` (precise), `max_tokens=3000` (highest)

**Use Cases**:
- "Design a REST API for user management"
- "Create a PostgreSQL schema for e-commerce"
- "How should I structure microservices?"

---

### 4. 💎 **Frontend Designer**
**Role**: React components, performance optimization, UX implementation

**Expertise**:
- React & hooks (useState, useEffect, useContext)
- Component composition & reusability
- State management (Redux, Context, Zustand)
- Performance optimization (memoization, lazy loading)
- CSS-in-JS & styling
- Testing strategies (Jest, React Testing Library)
- Build optimization
- Web performance metrics

**System Prompt**: Specialized in high-performance React development
**Parameters**: `temp=0.3` (balanced), `max_tokens=2800`

**Use Cases**:
- "Build a Todo component with hooks"
- "Optimize React performance"
- "Write tests for this component"

---

### 5. 🔬 **Agent Researcher**
**Role**: Agentic workflows, multi-step reasoning, autonomous systems

**Expertise**:
- Agentic pattern design
- Tool use & orchestration
- Multi-step task decomposition
- Reasoning frameworks
- Autonomous loop design
- Agent evaluation metrics
- Human-in-the-loop systems
- Prompt-based planning

**System Prompt**: Specialized in autonomous workflow design
**Parameters**: `temp=0.4` (creative), `max_tokens=2800`

**Use Cases**:
- "Break down this complex task into steps"
- "Design an autonomous workflow"
- "How should agents collaborate?"

---

### 6. 🚀 **DevOps Specialist**
**Role**: Deployment, infrastructure, monitoring, CI/CD

**Expertise**:
- Docker & containerization
- Kubernetes orchestration
- CI/CD pipelines
- Infrastructure as Code (Terraform, CloudFormation)
- Monitoring & logging
- Security & compliance
- Database management
- Disaster recovery & backup

**System Prompt**: Specialized in deployment and infrastructure
**Parameters**: `temp=0.25` (precise), `max_tokens=2500`

**Use Cases**:
- "Create a Docker deployment"
- "Set up a CI/CD pipeline"
- "Configure Kubernetes"

---

## CLI Commands

### Team Status & Management

```bash
/team
# View team status, agent workload, total tasks executed
# Output: Team size, workload per agent, overall stats

/team-list
# List all agents with detailed expertise
# Output: Name, role, expertise areas

/team-task <task>
# Delegate task to entire team (primary + supporting agents)
# Automatically routes to most suitable agents
# Example: /team-task "Create a complete e-commerce platform"

/team <agent_id> <task>
# Delegate task to specific agent
# Agent IDs: llm-engineer, ui-programmer, backend-expert, 
#            frontend-designer, agent-researcher, devops-specialist
# Example: /team backend-expert "Design a REST API for users"
```

---

## How Team Dispatch Works

### 1. **Task Classification**
```
User Input → Task Type Detection
├── Code → backend-expert, frontend-designer
├── Design → ui-programmer, frontend-designer
├── Deployment → devops-specialist
├── LLM → llm-engineer
└── Agentic → agent-researcher
```

### 2. **Agent Selection**
```
Decision Process:
1. Analyze keywords in task
2. Score each agent by relevance
3. Select PRIMARY agent (highest score)
4. Select SUPPORTING agents (2 max, high relevance)
5. Dispatch to primary first, then supporting in parallel
```

### 3. **Response Synthesis**
```
Multi-Agent Responses → Unified Report
├── Task description
├── Team decision & reasoning
├── Individual agent responses
│   ├── Status (done/error)
│   ├── Confidence score
│   └── Time taken
├── Overall confidence
└── Total execution time
```

---

## Integration with LLM Gateway

The Developer Team integrates seamlessly with Franz's LLM Gateway:

```python
# Gateway automatically routes based on task type
task_type = "code" → Backend Expert + Frontend Designer
task_type = "deploy" → DevOps Specialist
task_type = "research" → Agent Researcher + LLM Engineer
task_type = "design" → UI Programmer + Frontend Designer
```

---

## Example Workflows

### Workflow 1: Full-Stack Application

```
User: /team-task "Build a complete chat application"

Team Dispatch:
├─ Primary: Agent Researcher (orchestrates workflow)
├─ Supporting:
│  ├─ Backend Expert (API design)
│  ├─ Frontend Designer (React UI)
│  ├─ DevOps Specialist (deployment)
│  └─ UI Programmer (design system)

Result:
✓ Architecture breakdown
✓ API endpoint specifications
✓ React component structure
✓ Deployment pipeline
✓ Design system
```

### Workflow 2: Performance Optimization

```
User: /team-task "Optimize React app performance"

Team Dispatch:
├─ Primary: Frontend Designer
├─ Supporting:
│  ├─ LLM Engineer (model optimization)
│  └─ Backend Expert (caching strategy)

Result:
✓ Code splitting strategy
✓ Component memoization
✓ Bundle size analysis
✓ Caching recommendations
```

### Workflow 3: Microservices Architecture

```
User: /team-task "Design microservices for IoT platform"

Team Dispatch:
├─ Primary: Agent Researcher
├─ Supporting:
│  ├─ Backend Expert (service design)
│  ├─ DevOps Specialist (infrastructure)
│  └─ LLM Engineer (optimization)

Result:
✓ Service decomposition
✓ API contracts
✓ Kubernetes manifests
✓ Performance tuning
```

---

## Agent Workload Tracking

```bash
/team
# Output example:
# 
# Team Size: 6 agents
# Total Tasks: 127
# Total Workload: 312 tasks
# 
# Agent Workload:
# • Backend Expert         → 78 tasks
# • LLM Engineer           → 45 tasks
# • DevOps Specialist      → 63 tasks
# • UI Programmer          → 52 tasks
# • Agent Researcher       → 48 tasks
# • Frontend Designer       → 26 tasks
```

This helps identify:
- Which agents are most utilized
- Load balancing across team
- Agent specialization effectiveness
- Performance trends

---

## Configuration

Each agent has optimized parameters:

| Agent | Temperature | Max Tokens | Focus |
|-------|-------------|------------|-------|
| Backend Expert | 0.25 | 3000 | Precision |
| LLM Engineer | 0.20 | 2500 | Optimization |
| DevOps Specialist | 0.25 | 2500 | Infrastructure |
| UI Programmer | 0.35 | 2000 | Design |
| Agent Researcher | 0.40 | 2800 | Creativity |
| Frontend Designer | 0.30 | 2800 | Implementation |

---

## Performance Metrics

Each team dispatch provides:

```json
{
  "overall_confidence": 0.75,      // 0.0-1.0 confidence in solution
  "total_time_ms": 1234,           // Total execution time
  "responses": [
    {
      "agent_name": "Backend Expert",
      "status": "done",
      "confidence": 0.85,
      "time_ms": 234
    },
    ...
  ]
}
```

---

## Future Enhancements

Planned for Franz v8.1+:

1. **Agent Collaboration**
   - Agents can request help from other agents
   - Cross-agent validation

2. **Knowledge Sharing**
   - Shared knowledge base across agents
   - Learned patterns and best practices

3. **Performance Tuning**
   - Dynamic parameter adjustment
   - Per-task optimization

4. **Quality Assurance**
   - Agent response validation
   - Confidence scoring improvements

5. **Specialized Tools**
   - Code analyzer per agent type
   - Domain-specific validation

---

## Usage Tips

### For Code Generation
```
/team backend-expert "Create a user authentication endpoint"
# Better than: just asking LLM
# Why: Specialized in API design, error handling, security
```

### For Architecture
```
/team-task "Plan the architecture for a SaaS platform"
# Better than: /team agent-researcher "..."
# Why: Multiple perspectives = better design
```

### For Quick Tasks
```
/team ui-programmer "Design a button component"
# Better than: /team-task (faster, targeted)
# Why: Single agent faster for focused tasks
```

---

## Status

✅ **Version 8.0 Implementation Complete**

- [x] 6 specialized agents defined
- [x] Agent coordinator implemented
- [x] Task dispatch system
- [x] CLI integration (/team commands)
- [x] Response synthesis
- [x] Workload tracking
- [x] Integration tests passing
- [x] Documentation complete

---

**Franz Developer Team v8.0 is ready for production use!** 🚀
