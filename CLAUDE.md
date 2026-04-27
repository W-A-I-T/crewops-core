# crewops-core

Standalone local-first agent runtime. Provides the CrewAI department crews dashboard and reasoning engine for the nanocrew WhatsApp OS.

**GitHub:** `gh repo view W-A-I-T/crewops-core`
**Part of nanocrew stack** — see W-A-I-T/nanocrew for full architecture.

## Stack
Python 3.12 · CrewAI · FastAPI · Ollama (Qwen 2.5 14B / Llama 3.1 8B) · Docker

## How to run
See `W-A-I-T/nanocrew` docker-compose.

## Key env vars
```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b
ANTHROPIC_API_KEY=...    # fallback only
GOOGLE_API_KEY=...       # Gemini fallback
```
