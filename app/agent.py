"""Verifiable Deep Research agent.

Pipeline:
  1. You.com Research API produces a cited report.
  2. Extract atomic claims from the report (LLM).
  3. For each claim, judge groundedness against the cited sources (LLM).
     Unsupported claims trigger a corroboration search (You.com Search API).
  4. Emit a report annotated with per-claim verdicts + a scorecard.

The scorecard is the demo. It turns "trust me" into a measurable number.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import llm, youcom

CLAIM_SYS = (
    "You extract atomic, independently checkable factual claims from a research "
    "report. Skip opinions, hedges, and transitions. Return JSON: "
    '{"claims": ["claim 1", "claim 2", ...]}. Keep each claim to one sentence. '
    "If the sentence a claim comes from carries inline citation markers like "
    "[[1, 2]], append those markers verbatim to the end of the claim."
)

# Inline citation markers in Research API reports: [[1]] or [[1, 2]], 1-indexed
# into the report's source list.
_MARKER_RE = re.compile(r"\[\[([\d,\s]+)\]\]")


def _cited_indices(text: str, n_sources: int) -> list[int]:
    idx: list[int] = []
    for m in _MARKER_RE.finditer(text):
        for part in m.group(1).split(","):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= n_sources and int(part) not in idx:
                idx.append(int(part))
    return idx

JUDGE_SYS = (
    "You are a strict groundedness judge. Given a CLAIM and SOURCE EXCERPTS, decide "
    "if the excerpts directly support the claim. Return JSON: "
    '{"verdict": "supported" | "partial" | "unsupported", '
    '"confidence": 0.0-1.0, "reason": "one sentence"}. '
    "Do not use outside knowledge; judge only against the excerpts."
)


@dataclass
class ClaimVerdict:
    claim: str
    verdict: str
    confidence: float
    reason: str
    cited_sources: list[int] = field(default_factory=list)


@dataclass
class Scorecard:
    total_claims: int
    supported: int
    partial: int
    unsupported: int
    groundedness: float          # supported / total
    citation_density: float      # sources per claim
    effort: str
    latency_s: float

    @property
    def grade(self) -> str:
        g = self.groundedness
        return "A" if g >= 0.9 else "B" if g >= 0.75 else "C" if g >= 0.6 else "D"


@dataclass
class Report:
    question: str
    content: str
    sources: list[dict]
    verdicts: list[dict] = field(default_factory=list)
    scorecard: dict = field(default_factory=dict)


def _excerpts(
    sources: list[youcom.Source], limit: int = 8, indices: list[int] | None = None
) -> str:
    # indices are 1-based source numbers; keep them so the judge and the UI
    # talk about the same source [n] the report cited.
    if indices:
        pairs = [(i, sources[i - 1]) for i in indices[:limit]]
    else:
        pairs = list(enumerate(sources[:limit], 1))
    lines = []
    for i, s in pairs:
        snip = " ".join(s.snippets)[:600] if s.snippets else s.title
        lines.append(f"[{i}] {s.title} ({s.url})\n{snip}")
    return "\n\n".join(lines)


def run(question: str, effort: str = "standard", max_claims: int = 12) -> Report:
    res = youcom.research(question, effort=effort)
    src_block = _excerpts(res.sources)

    claims = llm.complete_json(CLAIM_SYS, f"REPORT:\n{res.content}").get("claims", [])[:max_claims]

    verdicts: list[ClaimVerdict] = []
    for claim in claims:
        cited = _cited_indices(claim, len(res.sources))
        block = _excerpts(res.sources, indices=cited) if cited else src_block
        j = llm.complete_json(
            JUDGE_SYS, f"CLAIM:\n{claim}\n\nSOURCE EXCERPTS:\n{block}"
        )
        v = ClaimVerdict(
            claim=claim,
            verdict=j.get("verdict", "unsupported"),
            confidence=float(j.get("confidence", 0.0)),
            reason=j.get("reason", ""),
            cited_sources=cited,
        )
        # Second chance: corroborate an unsupported claim with a live search.
        # Best-effort: a search or judge failure here must not kill the run;
        # the claim just stays unsupported.
        if v.verdict == "unsupported":
            try:
                extra = youcom.search(claim, count=3)
                if extra:
                    j2 = llm.complete_json(
                        JUDGE_SYS, f"CLAIM:\n{claim}\n\nSOURCE EXCERPTS:\n{_excerpts(extra)}"
                    )
                    if j2.get("verdict") != "unsupported":
                        v.verdict = j2.get("verdict", v.verdict)
                        v.confidence = float(j2.get("confidence", v.confidence))
                        v.reason = "corroborated via live search: " + j2.get("reason", "")
            except Exception as exc:
                print(f"[agent] corroboration search failed, claim stays unsupported: {type(exc).__name__}: {exc}")
        verdicts.append(v)

    total = len(verdicts) or 1
    supported = sum(1 for v in verdicts if v.verdict == "supported")
    partial = sum(1 for v in verdicts if v.verdict == "partial")
    unsupported = sum(1 for v in verdicts if v.verdict == "unsupported")
    card = Scorecard(
        total_claims=len(verdicts),
        supported=supported,
        partial=partial,
        unsupported=unsupported,
        groundedness=round(supported / total, 3),
        citation_density=round(len(res.sources) / total, 2),
        effort=effort,
        latency_s=res.latency_s,
    )

    return Report(
        question=question,
        content=res.content,
        sources=[asdict(s) for s in res.sources],
        verdicts=[asdict(v) for v in verdicts],
        scorecard={**asdict(card), "grade": card.grade},
    )
