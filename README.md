# crewops-core

`crewops-core` is a local-first agent runtime package for building reusable automation systems around a small set of primitives:

- department registration and task dispatch
- compact context packs
- a lightweight memory spine backed by SQLite
- a generic FastAPI dashboard and task API
- reusable browser, search, diagnostics, and local-agent tool adapters

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

## Quick start

```bash
git clone https://github.com/W-A-I-T/crewops-core
cd crewops-core
cp .env.example .env
./install.sh
crewops-core-dashboard
```

Then open `http://localhost:8080`.

## CLI

```bash
crewops-core --request "Draft a rollout checklist"
crewops-core --dept research --request "Summarize local agent deployment options"
```

## Extension hooks

Register custom departments, seed entities, or delivery adapters:

```python
from crewops_core import register_department, register_seed_entities

register_department("support", lambda request: f"support handled: {request}")
register_seed_entities(
    {
        "entity_project_support": ("project", "Support", ["support", "service desk"]),
    }
)
```

Examples live in [`examples/`](examples).

## Public surface

The public package is intentionally neutral:

- no product-specific crews
- no business-specific prompts or docs
- no messaging-platform coupling
- no inherited repository history from the private product repo

## License

Apache-2.0
