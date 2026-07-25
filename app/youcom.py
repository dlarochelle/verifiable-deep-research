"""Thin client for the You.com APIs used at the hackathon.

Endpoints verified against docs.you.com on 2026-07-24. Re-confirm at the
10:20 AM API workshop; the Research API `source_control`/`output_schema`
fields were still marked beta.

Auth: X-API-Key header. Put your key in .env as YDC_API_KEY.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

# The official hackathon guide (YDC_hackathon_track PDF) shows
# api.ydc-index.io for Search; docs.you.com showed ydc-index.io.
# Default to the guide's host; flip via env if one 404s at the venue.
SEARCH_URL = os.environ.get("YDC_SEARCH_URL", "https://api.ydc-index.io/v1/search")
RESEARCH_URL = "https://api.you.com/v1/research"
FINANCE_URL = "https://api.you.com/v1/finance_research"
AGENTS_URL = "https://api.you.com/v1/agents/runs"


def _key() -> str:
    key = os.environ.get("YDC_API_KEY")
    if not key:
        raise RuntimeError("YDC_API_KEY not set. Copy .env.example to .env and fill it in.")
    return key


@dataclass
class Source:
    url: str
    title: str = ""
    snippets: list[str] = field(default_factory=list)


@dataclass
class ResearchResult:
    content: str
    sources: list[Source]
    effort: str
    latency_s: float


def search(query: str, count: int = 5, livecrawl: bool = False, timeout: float = 30.0) -> list[Source]:
    """Web Search API. Fast, returns LLM-ready web results. Use for claim verification."""
    params = {"query": query, "count": count}
    if livecrawl:
        params["livecrawl"] = "all"
        params["livecrawl_formats"] = "markdown"
    with httpx.Client(timeout=timeout) as client:
        r = client.get(SEARCH_URL, headers={"X-API-Key": _key()}, params=params)
        r.raise_for_status()
        data = r.json()
    web = (data.get("results") or {}).get("web") or []
    return [
        Source(url=w.get("url", ""), title=w.get("title", ""), snippets=w.get("snippets", []) or [])
        for w in web
    ]


def research(question: str, effort: str = "standard", timeout: float = 300.0) -> ResearchResult:
    """Research API. effort in {lite, standard, deep, exhaustive, frontier}.

    Deep/exhaustive can take minutes. Keep the demo path on `standard` and
    show one `deep` run pre-baked so you never wait on stage.
    """
    import time

    body = {"input": question, "research_effort": effort}
    t0 = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            RESEARCH_URL,
            headers={"X-API-Key": _key(), "Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    latency = time.perf_counter() - t0
    out = data.get("output") or {}
    sources = [
        Source(url=s.get("url", ""), title=s.get("title", ""), snippets=s.get("snippets", []) or [])
        for s in (out.get("sources") or [])
    ]
    return ResearchResult(
        content=out.get("content", ""),
        sources=sources,
        effort=effort,
        latency_s=round(latency, 2),
    )


def agents_run(
    question: str,
    agent: str = "advanced",
    tools: tuple[str, ...] = ("research", "compute"),
    max_steps: int = 5,
    timeout: float = 300.0,
) -> ResearchResult:
    """Agents API — the one the hackathon guide pushes hardest.

    NOTE: unlike the other endpoints, this uses Bearer auth, not X-API-Key.
    Non-streaming call; the API also supports SSE via "stream": true.
    Response shape unverified against a live call. Confirm at the 10:20
    workshop and adjust the parsing below if needed.
    """
    import time

    body = {
        "agent": agent,
        "input": question,
        "stream": False,
        "tools": [{"type": t} for t in tools],
        "verbosity": "medium",
        "workflow_config": {"max_workflow_steps": max_steps},
    }
    t0 = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            AGENTS_URL,
            headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    latency = time.perf_counter() - t0
    out = data.get("output") or data
    raw_sources = out.get("sources") or data.get("sources") or []
    sources = [
        Source(url=s.get("url", ""), title=s.get("title", ""), snippets=s.get("snippets", []) or [])
        for s in raw_sources
    ]
    content = out.get("content") or out.get("answer") or ""
    return ResearchResult(content=content, sources=sources, effort=f"agents:{agent}", latency_s=round(latency, 2))
