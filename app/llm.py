"""LLM layer for claim extraction and groundedness judging.

Live config: LLM_PROVIDER=parasail (hackathon partner, OpenAI-compatible)
with Anthropic as the fallback judge when Parasail is overloaded. Unset
LLM_PROVIDER or set it to anything else to run on Anthropic directly.
"""
from __future__ import annotations

import json
import os
import time

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def _anthropic_complete(system: str, user: str, max_tokens: int = 2000) -> str:
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY
    # No temperature param: claude-sonnet-5 rejects it as deprecated (400).
    # The temp-0 controlled comparison only holds on the Parasail side now.
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


def _parasail_complete(system: str, user: str, max_tokens: int = 2000) -> str:
    from openai import OpenAI

    client = OpenAI(
        base_url=os.environ.get("PARASAIL_BASE_URL", "https://api.parasail.io/v1"),
        api_key=os.environ["PARASAIL_API_KEY"],
        # Event-day load: 429s here retried for minutes and stalled whole runs.
        max_retries=1,
        timeout=60.0,
    )
    resp = client.chat.completions.create(
        # Roster: GET /v1/models with the same bearer token.
        model=os.environ.get("PARASAIL_MODEL", "parasail-deepseek-r1"),
        max_tokens=max_tokens,
        temperature=0,  # controlled comparison: same pipeline, same prompt, temp 0
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def _have_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def complete(system: str, user: str, max_tokens: int = 2000) -> str:
    if PROVIDER != "parasail":
        return _anthropic_complete(system, user, max_tokens)

    # Partner endpoint returns 429 "engine is currently overloaded" under event
    # load. Observed to be transient, so back off and retry before giving up.
    # With a Claude fallback configured, fail over after one retry instead of
    # stalling the demo through the full backoff ladder.
    attempts = 2 if _have_anthropic_key() else 4
    delay = 2.0
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _parasail_complete(system, user, max_tokens)
        except Exception as exc:
            last = exc
            if attempt < attempts:
                print(f"[llm] parasail {type(exc).__name__}, retry {attempt}/{attempts - 1} in {delay:.0f}s")
                time.sleep(delay)
                delay *= 2

    # Anthropic is a real fallback only when a key is actually configured.
    if _have_anthropic_key():
        print("[llm] parasail exhausted, judging on anthropic")
        return _anthropic_complete(system, user, max_tokens)
    raise RuntimeError(
        "Parasail unavailable after 4 attempts and ANTHROPIC_API_KEY is not set, "
        f"so there is no judge to fall back to. Last error: {type(last).__name__}: {last}"
    )


def complete_json(system: str, user: str, max_tokens: int = 2000) -> dict:
    """Ask for JSON, tolerate fenced code blocks."""
    raw = complete(system + "\nRespond with valid JSON only.", user, max_tokens).strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
