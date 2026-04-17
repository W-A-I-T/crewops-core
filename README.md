# crewops-core

`crewops-core` is a local-first agent runtime for building reusable automation systems around a small, inspectable core:

- department registration and task dispatch
- compact context packs for grounded execution
- a lightweight SQLite-backed memory spine
- a generic FastAPI dashboard and task API
- optional adapters for local coding agents, browser automation, diagnostics, and search

It is meant to be extended. The core stays neutral and reusable; downstream repos add product-specific departments, seeded entities, delivery adapters, and domain workflows on top.

## What it provides

`crewops-core` gives you a few stable primitives instead of a giant monolith:

- `RuntimeRegistry` for registering departments and delivery adapters
- task persistence and compact context generation
- memory ingestion, promotion, and suggestion scaffolding
- a thin dashboard and JSON API for task execution and review
- generic tools for browser work, diagnostics, search, and local agent delegation

## Architecture

```text
client or event source
        |
        v
dashboard + task API
        |
        +--> department registry
        +--> context pack builder
        +--> memory spine
        +--> optional local agent adapters
```

The package keeps the core loop small:

1. register departments
2. accept a task
3. persist task state
4. enrich with compact context
5. execute through the selected department or adapter
6. sync artifacts and recent events into the memory spine

## Install

### Local editable install

```bash
git clone <repo-url>
cd crewops-core
cp .env.example .env
./install.sh
```

That installs the package in editable mode and prepares the default local environment.

### Package install

```bash
pip install -e .
```

## Quick start

Run the dashboard:

```bash
crewops-core-dashboard
```

Then open `http://localhost:8080`.

Run the CLI:

```bash
crewops-core --request "Draft a rollout checklist"
crewops-core --dept research --request "Summarize local agent deployment options"
crewops-core --list-depts
```

## Dashboard and API

The built-in app exposes a small generic surface:

- `GET /` for the dashboard shell
- `GET /api/status` for runtime status and registered departments
- `GET /api/services/health` for local service health
- `POST /api/task` for synchronous task execution
- `GET /api/task/{task_id}` for stored task state
- `GET /api/jarvis/overview` for memory sync summary
- `GET /api/jarvis/memories` for stored memories
- `GET /api/jarvis/suggestions` for suggested follow-ups

Example task request:

```bash
curl -X POST http://localhost:8080/api/task \
  -H "Content-Type: application/json" \
  -d '{"dept":"software","request":"Draft a deploy checklist"}'
```

## Extending the runtime

### Register departments

```python
from crewops_core import register_department

register_department("support", lambda request: f"support handled: {request}")
```

### Register seeded entities

```python
from crewops_core import register_seed_entities

register_seed_entities(
    {
        "entity_project_support": ("project", "Support", ["support", "service desk"]),
    }
)
```

### Register delivery adapters

```python
from crewops_core import register_delivery_adapter

register_delivery_adapter("webhook", lambda payload: {"delivered": True, "payload": payload})
```

See [`examples/`](examples) for small reference integrations.

## Configuration

Copy `.env.example` to `.env` and fill in only what you need.

Most useful settings:

| Variable | Purpose |
| --- | --- |
| `DEMO_MODE` | Prefer a local-first setup |
| `OLLAMA_BASE_URL` | Override the local model endpoint |
| `GEMINI_API_KEY` | Optional cloud fallback and embeddings |
| `NVIDIA_API_KEY` | Optional asymmetric embedding backend |
| `SERPER_API_KEY` | Optional structured web search |
| `LOCAL_CODING_AGENT_URL` | Local coding agent endpoint |
| `CODING_AGENT_BIN` | Optional coding agent CLI binary |
| `RESEARCH_AGENT_BIN` | Optional research agent CLI binary |
| `CREWAI_STORAGE_DIR` | Override memory storage path |
| `JARVIS_SPINE_DB_PATH` | Override the SQLite memory spine location |

## Examples

The repo includes simple examples for:

- software delivery
- research and content
- operations
- private downstream extension

These are intentionally small and meant to show the registration pattern, not to act as full product templates.

## Testing and coverage

The public repo enforces a strict CI bar:

- forbidden-name audit for banned external/product references
- unit and API tests
- dashboard boot and endpoint checks
- minimum `95%` line coverage on the `crewops_core` package

Run the local test suite:

```bash
pytest
```

Run the coverage gate locally:

```bash
pytest --cov=crewops_core --cov-report=term-missing --cov-fail-under=95
```

Run the forbidden-string audit:

```bash
python scripts/audit_forbidden_strings.py .
```

## Release expectations

`crewops-core` is intended to be published as a standalone reusable foundation. Public changes should:

- keep the exported surface neutral
- avoid product-specific prompts, URLs, and business logic
- preserve extension hooks for downstream repos
- maintain the 95% coverage threshold

## License

Apache-2.0
