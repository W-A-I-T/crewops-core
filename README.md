# crewops-core

`crewops-core` is a local-first agent runtime and control layer for building practical AI operations systems: routed tasks, reusable departments, compact context, persistent memory, dashboard APIs, and automation tools in one inspectable package.

W-A-I-T built this project to turn real internal orchestration work into a clean public foundation. It is both an open-source runtime for builders and a public proof point for clients who want to see the kind of AI infrastructure, automation discipline, and product engineering we can deliver.

## Who This Is For

`crewops-core` is for two audiences:

- builders who want a reusable starting point for agent routing, memory, and task execution
- clients evaluating W-A-I-T and looking for evidence of real AI systems work beyond prompt demos

If you are hiring for AI automation, internal tooling, research workflows, local-first agent infrastructure, or browser-assisted operations systems, this repo is meant to show the level and shape of work we can ship.

## What This Is

`crewops-core` is the reusable core behind AI systems that need more than a single prompt:

- task routing across named departments or execution lanes
- memory and context management for repeated work
- browser and local tooling integration
- a dashboard and API for task submission, health, and review
- extension hooks so private or client-specific layers can sit on top without forking the core

It is designed to stay small, auditable, and adaptable. The core owns the runtime. Product logic belongs in downstream repos.

## Why It Was Built

Most AI demos stop at chat. Real client systems need orchestration: they need tasks to be routed, state to be saved, context to be packed, services to be checked, and tools to be swapped without rewriting the whole app.

`crewops-core` exists to solve that problem in a public-safe way. W-A-I-T extracted the reusable runtime pieces from real multi-agent implementation work so the public repo could stand on its own:

- no private business workflows
- no customer-specific prompts or credentials
- no delivery-channel lock-in
- no dependence on private product repos

That makes the repo useful for builders and meaningful for clients evaluating what our team can actually ship.

## What It Demonstrates

This repo is a working example of the capabilities W-A-I-T can deliver for client engagements and internal platforms:

- multi-agent orchestration with explicit department routing
- local-first AI runtime design that can still plug into optional external services
- task execution, persistence, and recovery
- memory and context management for longer-running workflows
- browser and automation tooling for web-based work
- diagnostics, health checks, and service visibility
- packaging, CI, testing discipline, and release hygiene suitable for production engineering

## Typical Client Use Cases

The same runtime pattern can support projects like:

- AI operations dashboards for internal teams
- research and reporting workflows
- software delivery assistants for planning, QA, and release support
- browser-driven process automation
- internal agent platforms where teams register their own departments and tools
- local-first AI deployments where auditability and infrastructure control matter

## What Is In Scope

The public repo intentionally includes:

- reusable runtime primitives
- generic dashboard and API behavior
- generic tools and adapters
- local memory and task infrastructure
- extension hooks for downstream repos
- examples, tests, CI, and packaging

The public repo intentionally does not include:

- private product workflows
- customer prompts or business rules
- client credentials, internal URLs, or delivery secrets
- one-off automations that only make sense in a private deployment

## Architecture

```text
client, cron, webhook, or operator
              |
              v
      dashboard + task API
              |
      +-------+--------+------------------+
      |                |                  |
      v                v                  v
department registry  context packs   service health
      |                |                  |
      +---------> runtime dispatch <------+
                        |
                        v
               tools and agent adapters
                        |
                        v
                  memory spine
```

The execution loop stays intentionally simple:

1. register departments, seeded entities, and optional adapters
2. accept a task from the CLI, API, or downstream integration
3. persist state and build compact context
4. dispatch to the selected department or tool layer
5. record results and sync memory for later follow-up

## Technology Stack

| Technology | Role in the system |
| --- | --- |
| Python 3.11+ | Core runtime language and packaging target |
| FastAPI | Dashboard and JSON API surface |
| Pydantic | Request validation and config shaping |
| SQLite | Lightweight local persistence for the memory spine |
| CrewAI | Optional crew and agent execution primitives |
| Playwright | Browser automation and page interaction |
| Docker / Docker Compose | Local packaging and service orchestration |
| Ollama | Local model serving for local-first deployments |
| GitHub Actions | CI for audit, tests, coverage, and boot checks |
| pytest / pytest-cov | Unit, API, and coverage enforcement |

Optional integrations can layer on top for search, embeddings, cloud models, or local coding agents, but the public runtime stays usable without turning those into hard requirements.

## How It Works

The package gives you a few stable primitives instead of a giant framework:

- `RuntimeRegistry` for department registration and delivery adapter registration
- task state persistence for active work
- context pack generation for grounded execution
- memory ingestion, review, and suggestion scaffolding
- a dashboard shell and API for synchronous task execution and runtime inspection
- generic tools for diagnostics, browser work, local coding flows, and search

The main rule is simple: generic runtime behavior belongs in `crewops-core`; product logic belongs outside it.

## Repository Layout

The repo is organized so the public runtime stays easy to reason about:

| Path | Purpose |
| --- | --- |
| `crewops_core/` | Public package with runtime, app, config, memory, and tools |
| `crewops_core/lib/` | Shared orchestration primitives and persistence helpers |
| `crewops_core/tools/` | Generic tool adapters for browser work, diagnostics, search, and local coding flows |
| `crewops_core/static/` | Dashboard UI assets |
| `examples/` | Small reference integrations and extension patterns |
| `tests/` | Public unit and API test suite |
| `.github/workflows/` | CI for audit, tests, coverage, and dashboard boot validation |

This layout is deliberate: reusable runtime code lives in the package, while demos and downstream patterns stay outside the core package boundary.

## Installation

### Clone and install

```bash
git clone https://github.com/W-A-I-T/crewops-core.git
cd crewops-core
cp .env.example .env
./install.sh
```

### Editable package install

```bash
pip install -e .
```

### Local runtime prerequisites

The base package works without every optional integration enabled. For a fuller local-first setup, the common path is:

- Python 3.11+
- Playwright Chromium installed through `install.sh`
- optional Ollama for local model serving
- optional API keys only for the services you actually enable

## CLI and Dashboard Usage

Run the dashboard:

```bash
crewops-core-dashboard
```

Then open `http://localhost:8080`.

Run the CLI:

```bash
crewops-core --request "Draft a rollout checklist"
crewops-core --dept research --request "Summarize local deployment options"
crewops-core --list-depts
```

The built-in API exposes a compact runtime surface:

- `GET /`
- `GET /api/status`
- `GET /api/services/health`
- `POST /api/task`
- `GET /api/task/{task_id}`
- `GET /api/jarvis/overview`
- `GET /api/jarvis/memories`
- `GET /api/jarvis/suggestions`

Example task request:

```bash
curl -X POST http://localhost:8080/api/task \
  -H "Content-Type: application/json" \
  -d '{"dept":"software","request":"Draft a deploy checklist"}'
```

## How To Extend This Repo

The intended extension model is additive, not invasive.

### 1. Register a department

```python
from crewops_core import register_department

register_department("support", lambda request: f"support handled: {request}")
```

### 2. Register seeded entities

```python
from crewops_core import register_seed_entities

register_seed_entities(
    {
        "entity_project_support": ("project", "Support", ["support", "service desk"]),
    }
)
```

### 3. Register delivery adapters

```python
from crewops_core import register_delivery_adapter

register_delivery_adapter("webhook", lambda payload: {"delivered": True, "payload": payload})
```

### 4. Keep product logic outside core

Use downstream repos or private packages for:

- client workflows
- domain prompts
- customer integrations
- proprietary business logic

### 5. Add tests and pass the public gates

Before merge, run:

```bash
pytest
pytest --cov=crewops_core --cov-report=term-missing --cov-fail-under=95
python scripts/audit_forbidden_strings.py .
```

See [`examples/`](examples) for small reference extensions.

## How To Add To This Repo

If you want to contribute new functionality, the safest path is:

1. decide whether the feature is truly generic or belongs in a downstream product layer
2. add or extend runtime behavior inside `crewops_core/` only if it is reusable across domains
3. prefer registration hooks and small adapters over hardcoded assumptions
4. add or update tests in `tests/`
5. run audit, tests, and coverage locally
6. update the README or examples if the public extension story changed

Good additions usually make the public core more reusable. Bad additions usually smuggle in one product's workflow, naming, or integration assumptions.

## Contribution Rules

Public contributions to `crewops-core` should follow a few hard rules:

- do not commit secrets, customer data, private URLs, or internal credentials
- do not move product-specific business logic into the public core
- keep exported names, examples, and docs neutral and public-safe
- extend through registration hooks instead of patching core assumptions where possible
- keep tests current and preserve the `95%` coverage gate
- make CI pass before merge, including audit, tests, coverage, and dashboard boot checks

If a change only makes sense for one customer, one product, or one private delivery channel, it belongs downstream rather than in this repo.

A good rule of thumb: if the change improves routing, memory, task handling, generic tools, extension points, or developer ergonomics for many use cases, it probably belongs here. If it introduces business context, customer-specific flows, or branded delivery behavior, it probably does not.

## Engineering Rules

The repo follows a few practical engineering rules:

- keep the public surface provider-neutral and client-safe
- prefer small, inspectable modules over hidden magic
- treat local-first execution as the default, with external services as optional layers
- preserve backward-compatible command entrypoints where practical
- do not lower the coverage bar to make a change easier to merge
- document new public extension points when they are introduced

## Testing and Coverage

The public CI enforces:

- forbidden-name audit for banned external or private references
- unit and API tests
- dashboard boot and endpoint checks
- minimum `95%` line coverage on the `crewops_core` package

Run the local suite:

```bash
pytest
```

Run the coverage gate:

```bash
pytest --cov=crewops_core --cov-report=term-missing --cov-report=xml --cov-fail-under=95
```

Run the audit:

```bash
python scripts/audit_forbidden_strings.py .
```

## Release Expectations

Public releases should keep the runtime easy to adopt and safe to extend:

- preserve stable package-owned entrypoints
- keep the dashboard and API generic
- maintain public-safe naming and examples
- prefer extension hooks over one-off hardcoding
- keep tests and coverage healthy as the runtime grows

## License

Apache-2.0
