# Contributing to crewops-core

Thanks for contributing to `crewops-core`.

This repo is the public, reusable runtime layer. It should stay clean, generic, and safe to build on. Private business logic, customer flows, and branded delivery behavior belong downstream, not in this repository.

`crewops-core` does not require the private `crewops` repo in order to run. `crewops` is one downstream consumer, not a runtime dependency. Other similar repos can consume this package in the same way.

## What belongs here

Good contributions usually improve one of these:

- runtime routing and department registration
- context packing and memory behavior
- generic dashboard or CLI workflows
- generic tool adapters and diagnostics
- developer ergonomics for downstream extension
- public examples, tests, and documentation

Changes usually do not belong here if they introduce:

- client-specific prompts or workflows
- private URLs, credentials, or service assumptions
- hardcoded business logic for one product or one deployment
- branded integrations that cannot be reused outside a private stack

## Local setup

```bash
git clone https://github.com/W-A-I-T/crewops-core.git
cd crewops-core
cp .env.example .env
./install.sh
```

If you are modifying the package itself, editable install is the normal workflow:

```bash
pip install -e .
```

If you are consuming the package from another repo, install it there as a dependency:

```bash
pip install git+https://github.com/W-A-I-T/crewops-core.git
```

Useful local commands:

```bash
crewops-core-dashboard
crewops-core --list-depts
```

## Before opening a pull request

Run the public checks locally:

```bash
python scripts/audit_forbidden_strings.py .
pytest
pytest --cov=crewops_core --cov-report=term-missing --cov-fail-under=95
```

If your change affects examples, onboarding, or extension behavior, update the README or `examples/` as part of the same pull request.

## Pull request expectations

A strong pull request should:

- describe the problem and the public-safe solution
- stay scoped to reusable runtime behavior
- include tests or explain why tests were not needed
- preserve or improve the `95%` coverage gate
- keep naming neutral and exported interfaces stable where practical
- avoid introducing banned private or provider-branded references

## Naming and public-safety rules

This repo is audited to stay public-safe.

- do not commit secrets, private prompts, customer data, or internal URLs
- do not introduce branded private workflow names into the public core
- keep exported names generic and downstream-friendly
- prefer extension hooks over one-off hardcoding
- do not lower CI requirements to make a change easier to merge

If you are unsure whether something belongs here, default to keeping the core generic and moving product-specific logic to a downstream layer.
