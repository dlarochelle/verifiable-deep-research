# Verifiable Deep Research

A FastAPI research agent that answers questions with citations **and audits itself**. It decomposes reports into atomic claims and grades each one for groundedness.

## How to run

The workflow **Start application** runs the server:

```
uv run uvicorn app.main:app --host 0.0.0.0 --port 5000
```

Open the preview pane to use the single-page UI.

## Required secrets

Set via Replit Secrets (already configured):

| Secret | Purpose |
|---|---|
| `YDC_API_KEY` | You.com Research + Search API |
| `PARASAIL_API_KEY` | LLM judge (primary) |
| `ANTHROPIC_API_KEY` | LLM judge (fallback) |
| `YDC_SEARCH_URL` | Set to `https://ydc-index.io/v1/search`. The default Search host returns 403 for this key |

## Non-secret config (set as env vars)

| Variable | Value |
|---|---|
| `LLM_PROVIDER` | `parasail` (or `anthropic`) |
| `PARASAIL_BASE_URL` | `https://api.parasail.io/v1` |
| `PARASAIL_MODEL` | `parasail-qwen3-235b-a22b-instruct-2507` |

## Stack

- Python 3.11, FastAPI, uvicorn
- `uv` for dependency management (`uv sync` to install)
- You.com Research API for retrieval
- Parasail (primary) / Anthropic (fallback) for claim extraction + judging

## Project layout

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI app + single-page UI |
| `app/agent.py` | Pipeline: extract → judge → corroborate → scorecard |
| `app/llm.py` | Claim extraction + groundedness judge (Parasail/Anthropic) |
| `app/youcom.py` | You.com Search + Research clients |
| `eval/run_eval.py` | Batch eval harness with effort sweep |

## User preferences

- Keep existing project structure and stack
