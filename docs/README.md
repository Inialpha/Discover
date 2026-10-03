# Documentation Index

[`../REQUIREMENTS.md`](../REQUIREMENTS.md) is the **canonical** specification. Everything here elaborates it and defers to it (ADR-014).

| Folder | Document | Read it for |
|---|---|---|
| `01-decisions/` | `decision-records.md` | Why each major decision was made (ADR-001..016) |
| `02-architecture/` | `system-architecture.md` | Layers, runtime and lifecycle |
| `03-backend/` | `backend-architecture.md` | Backend structure and conventions |
| `04-database/` | `database-architecture.md` | Table-level schema |
| `05-frontend/` | `frontend-architecture.md` | Frontend structure and components |
| `06-discovery-modes/` | `discovery-state-and-agent-tools.md` | State models, tools, prompts |
| `07-qloo/` | `qloo-integration.md` | Qloo adapter detail (wire formats provisional until recorded) |
| `08-api/` | `api-contract.md` | Request/response schemas and SSE examples |
| `09-deployment/` | `deployment-architecture.md` | Hosting, Docker, environments |
| `10-testing/` | `testing-strategy.md` | Test layers and profile mechanics |
| `11-hackathon/` | `hackathon-strategy.md` | Submission mapping and demo narrative |

## Rules of the road
1. Change `REQUIREMENTS.md` first, then the detail docs, then the code.
2. Reference requirement IDs (e.g. `STR-003`) instead of copying requirement text.
3. New decisions get a new ADR; superseded ADRs are marked, not deleted.
4. Never leave a detail doc contradicting the requirements, even temporarily.
