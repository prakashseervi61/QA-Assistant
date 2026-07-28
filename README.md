# QA Assistant - Multi-Agent System

## Overview

This project uses a multi-agent software engineering team for development. Each agent has clearly defined responsibilities, permissions, and collaboration rules.

## Project Structure

```
QA-assistant/
├── opencode.json          # Main agent configuration
├── AGENTS.md              # Agent system documentation
├── README.md              # This file
└── .opencode/
    └── agents/            # Individual agent configurations
        ├── project-coordinator.md
        ├── product-manager.md
        ├── software-architect.md
        ├── ui-designer.md
        ├── frontend-developer.md
        ├── backend-developer.md
        ├── ai-engineer.md
        ├── database-engineer.md
        ├── security-engineer.md
        ├── code-reviewer.md
        ├── qa-engineer.md
        ├── performance-engineer.md
        ├── devops-engineer.md
        └── documentation-agent.md
```

## Agent Team

| Agent | Role | Can Write Code | Can Execute Terminal | Git Access |
|-------|------|----------------|---------------------|------------|
| Project Coordinator | Workflow orchestration | ❌ | ❌ | ❌ |
| Product Manager | Requirements & planning | ❌ | ❌ | ❌ |
| Software Architect | Architecture design | ✅ | ❌ | ❌ |
| UI/UX Designer | Interface design | ✅ | ❌ | ❌ |
| Frontend Developer | UI implementation | ✅ | ✅ | ❌ |
| Backend Developer | API implementation | ✅ | ✅ | ❌ |
| AI/ML Engineer | AI features | ✅ | ✅ | ❌ |
| Database Engineer | Database management | ✅ | ✅ | ❌ |
| Security Engineer | Security review | ❌ | ✅ | ❌ |
| Code Reviewer | Code quality | ❌ | ❌ | ❌ |
| QA Engineer | Testing | ❌ | ✅ | ❌ |
| Performance Engineer | Optimization | ✅ | ✅ | ❌ |
| DevOps Engineer | Deployment | ✅ | ✅ | ✅ |
| Documentation Agent | Documentation | ❌ | ❌ | ❌ |

## Workflow

```
Project Coordinator
        ↓
Product Manager
        ↓
Software Architect
        ↓
UI/UX Designer
        ↓
Frontend Developer ←→ Backend Developer ←→ AI/ML Engineer ←→ Database Engineer
        ↓
Code Reviewer
        ↓
Security Engineer
        ↓
QA & Testing Engineer
        ↓
Performance Engineer
        ↓
DevOps Engineer
        ↓
Documentation Agent
```

## Handoff Rules

1. **Product Manager → Software Architect**: Requirements and user stories
2. **Software Architect → Implementation Teams**: Architecture and specifications
3. **UI Designer → Frontend Developer**: Design specifications
4. **Backend ↔ Database ↔ AI**: Coordinate through APIs only
5. **All Implementers → Code Reviewer**: Completed code
6. **Code Reviewer → Security Engineer**: Security review
7. **Security Engineer → QA Engineer**: Security approval
8. **QA Engineer → Performance Engineer**: Test approval
9. **Performance Engineer → DevOps Engineer**: Performance approval
10. **DevOps Engineer → Documentation Agent**: Deployment completion

## Global Rules

1. Follow SOLID, DRY, KISS, and Clean Architecture principles
2. Never duplicate responsibilities between agents
3. Only modify files within agent's responsibility
4. Never assume ambiguous requirements; ask for clarification
5. Use official documentation before implementing unfamiliar libraries
6. Every implementation must pass Code Review before QA
7. Every feature must pass QA before completion
8. Maintain consistent coding standards
9. Never expose secrets, API keys, or environment variables
10. Produce production-quality code only

## Usage

1. **Start a new feature**: Project Coordinator assigns work to Product Manager
2. **Requirements phase**: Product Manager creates user stories and acceptance criteria
3. **Architecture phase**: Software Architect designs the solution
4. **Implementation phase**: Development team implements features
5. **Review phase**: Code Reviewer ensures quality
6. **Security phase**: Security Engineer validates security
7. **Testing phase**: QA Engineer validates functionality
8. **Performance phase**: Performance Engineer optimizes
9. **Deployment phase**: DevOps Engineer deploys
10. **Documentation phase**: Documentation Agent updates docs

## Configuration

Agent configurations are stored in:
- `opencode.json`: Main configuration file
- `.opencode/agents/`: Individual agent system prompts

Each agent includes:
- Name and description
- System prompt with responsibilities
- Tool permissions
- Handoff rules
- Access permissions
