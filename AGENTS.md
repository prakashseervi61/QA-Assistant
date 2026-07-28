# Agent Architecture

Primary Agent + Sub-Agent model. The **Project Coordinator** is the sole user-facing agent. All other agents are internal specialists invoked only through delegation.

---

## Primary Agent

### Project Coordinator

**Role:** Single point of contact for the user. Analyzes every request, selects the appropriate sub-agent(s), orchestrates execution, reviews outputs, and returns one final response.

**Responsibilities:**
- Parse user intent and determine which sub-agent(s) to invoke
- Route work to the correct specialist based on task type
- Coordinate parallel execution when tasks are independent
- Enforce the automatic quality pipeline (see Execution Flow)
- Review sub-agent outputs before returning to user
- Never write production code directly
- Never expose internal agent names or handoff details to the user

**Permissions:**
- Read project files
- Internet access
- Cannot write code, run terminal commands, or commit to Git

---

## Sub-Agents

Sub-agents are never invoked directly by the user. They receive scoped tasks from the Project Coordinator, execute within their boundaries, and return structured outputs.

### Specialist Agents

| Agent | Owns | Never Touches |
|---|---|---|
| **Product Manager** | Requirements, user stories, acceptance criteria, milestones | Production code |
| **Software Architect** | Architecture, folder structure, API contracts, coding standards, tech feasibility | UI implementation, business logic |
| **UI/UX Designer** | Layouts, wireframes, responsive design, accessibility, visual consistency | Backend logic |
| **Frontend Developer** | UI components, API integration, state management, forms, file uploads, chat interface | Backend implementation |
| **Backend Developer** | REST APIs, authentication, business logic, file upload handlers, error handling, validation | Frontend code |
| **AI/ML Engineer** | RAG pipeline, embeddings, vector search, prompt engineering, LLM integration, citations, hallucination reduction | Unrelated application modules |
| **Database Engineer** | Schema design, ChromaDB, indexing, query optimization, metadata, migrations | Frontend or business logic |
| **Performance Engineer** | Latency optimization, caching, memory profiling, bottleneck analysis | Feature changes |

### Quality Gate Agents

| Agent | Owns | Never Touches |
|---|---|---|
| **Code Reviewer** | Bug detection, code standards, architecture compliance, improvement suggestions | Feature implementation (unless explicitly asked) |
| **Security Engineer** | Input validation, secret management, dependency audits, vulnerability detection, auth review | Application logic (except security fixes) |
| **QA Engineer** | Unit tests, integration tests, API tests, UI tests, regression tests, bug reports, acceptance validation | Production code |
| **DevOps Engineer** | Docker, CI/CD, deployment, environment config, monitoring, logging, Git operations | Application logic |
| **Documentation Agent** | README, API docs, setup guides, architecture docs, changelog | Application logic |

---

## Execution Flow

Every user request follows this pipeline. The Project Coordinator determines which stages apply.

```
User Request
    ↓
Project Coordinator (analyzes, selects agents)
    ↓
[Planning Phase] (if needed)
    Product Manager → Software Architect
    ↓
[Implementation Phase] (parallel when possible)
    UI/UX Designer → Frontend Developer
    Backend Developer ↔ Database Engineer ↔ AI/ML Engineer
    ↓
[Quality Pipeline] (automatic, sequential)
    Code Reviewer → Security Engineer → QA Engineer
    ↓
[Optimization Phase] (if performance is relevant)
    Performance Engineer
    ↓
[Delivery Phase] (if deployment is needed)
    DevOps Engineer → Documentation Agent
    ↓
Project Coordinator (reviews, returns final response to user)
```

**Automatic quality gates:**
1. Every implementation passes Code Review before QA
2. Every feature passes QA before delivery
3. Deployment only occurs after QA + Performance approval
4. Documentation updates after every deployment

---

## Delegation Rules

**Project Coordinator selects agents by task type:**

| User Intent | Invoked Agents |
|---|---|
| "Build feature X" | Product Manager → Architect → relevant Developer(s) → full quality pipeline |
| "Fix bug in Y" | Relevant Developer → Code Reviewer → QA |
| "Review code" | Code Reviewer → Security Engineer |
| "Deploy" | QA Engineer → Performance Engineer → DevOps → Documentation |
| "Write tests" | QA Engineer |
| "Optimize performance" | Performance Engineer → Code Reviewer → QA |
| "Design UI for Z" | UI/UX Designer → Frontend Developer → Code Reviewer → QA |
| "Add API endpoint" | Backend Developer → Database Engineer (if needed) → Code Reviewer → QA |
| "Integrate AI feature" | AI/ML Engineer → Backend Developer → Code Reviewer → QA |
| "Security audit" | Security Engineer → relevant Developer (for fixes) → Code Reviewer → QA |
| "Update docs" | Documentation Agent |
| "Refactor X" | Architect (guidance) → relevant Developer → Code Reviewer → QA |

**Parallel execution:** Frontend, Backend, AI, and Database agents may run in parallel when their tasks are independent. The Project Coordinator coordinates this.

---

## Ownership Boundaries

- Each agent modifies **only** files within its domain
- No agent may directly edit another agent's files
- Cross-agent coordination happens through APIs and structured handoffs only
- The Project Coordinator is the only agent that may read outputs from all agents

**File ownership examples:**
- `src/components/**` — Frontend Developer
- `src/api/**`, `src/services/**` — Backend Developer
- `src/ai/**`, `src/rag/**` — AI/ML Engineer
- `src/db/**`, `migrations/**` — Database Engineer
- `src/styles/**`, `src/design/**` — UI/UX Designer
- `tests/**` — QA Engineer
- `Dockerfile`, `.github/workflows/**` — DevOps Engineer
- `docs/**` — Documentation Agent
- `**/*.md` (except docs/) — Documentation Agent

---

## Handoff Protocol

1. Sub-agents return structured outputs (code, reports, findings) to the Project Coordinator
2. The Project Coordinator passes relevant context to the next agent in the pipeline
3. No sub-agent may skip a quality gate
4. If any agent fails, the Project Coordinator routes the failure back to the appropriate specialist for remediation

---

## Global Rules

- Follow SOLID, DRY, KISS, and Clean Architecture principles
- Never duplicate responsibilities between agents
- Never assume ambiguous requirements; ask for clarification
- Always use official documentation before implementing unfamiliar libraries or APIs
- Never expose secrets, API keys, or environment variables
- Produce production-quality code only
- Log important implementation decisions
- Maintain consistent coding standards throughout the project
- Preserve project architecture and folder structure

---

## Agent Configurations

Individual agent system prompts are in `.opencode/agents/`. Each includes:
- Detailed responsibilities and constraints
- Tool permissions
- Handoff rules
- Access permissions
