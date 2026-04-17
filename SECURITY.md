# Security Policy

## Reporting a vulnerability

Please do not open public GitHub issues for security-sensitive reports.

Use GitHub's private vulnerability reporting flow for this repository if it is enabled. If private reporting is unavailable, contact the repository owner directly through GitHub before disclosing technical details publicly.

When reporting a vulnerability, include:

- a short description of the issue
- affected files, endpoints, or commands
- reproduction steps if they can be shared safely
- impact and any suggested mitigation

## What not to disclose publicly

Do not post these details in a public issue:

- secrets, tokens, or credentials
- internal service URLs
- customer-specific prompts or workflow details
- exploit steps that would put live systems at risk

## Supported posture

`crewops-core` is maintained as a public reusable runtime. Security fixes should preserve the public-safe boundary of the repo and avoid leaking private downstream implementation details during triage.
