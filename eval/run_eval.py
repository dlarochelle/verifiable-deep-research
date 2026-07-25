"""Batch eval harness — the thing that wins the evaluation workshop.

Runs the agent across a question set and (optionally) across effort levels,
then prints an aggregate table: groundedness, unsupported rate, citation
density, and latency per effort. This is your "we measured it" slide.

Usage:
  python -m eval.run_eval                      # standard effort, all questions
  python -m eval.run_eval --effort deep
  python -m eval.run_eval --sweep lite,standard,deep --limit 3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics

from dotenv import load_dotenv

load_dotenv()

from app import agent

QFILE = pathlib.Path(__file__).parent / "questions.jsonl"


def load_questions(limit: int | None) -> list[dict]:
    rows = [json.loads(l) for l in QFILE.read_text().splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def run_effort(questions: list[dict], effort: str) -> dict:
    cards = []
    for q in questions:
        rep = agent.run(q["question"], effort=effort)
        s = rep.scorecard
        cards.append(s)
        print(f"  [{q['id']:>10}] grade {s['grade']}  "
              f"grounded {s['groundedness']:.0%}  "
              f"unsupported {s['unsupported']}/{s['total_claims']}  "
              f"{s['latency_s']}s")

    def avg(k):
        return round(statistics.mean(c[k] for c in cards), 3)

    return {
        "effort": effort,
        "n": len(cards),
        "avg_groundedness": avg("groundedness"),
        "avg_citation_density": avg("citation_density"),
        "avg_latency_s": avg("latency_s"),
        "total_unsupported": sum(c["unsupported"] for c in cards),
        "total_claims": sum(c["total_claims"] for c in cards),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--effort", default="standard")
    ap.add_argument("--sweep", default="", help="comma list of efforts to compare")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    questions = load_questions(args.limit)
    efforts = args.sweep.split(",") if args.sweep else [args.effort]

    summaries = []
    for effort in efforts:
        print(f"\n=== effort: {effort} ({len(questions)} questions) ===")
        summaries.append(run_effort(questions, effort.strip()))

    print("\n=== SUMMARY ===")
    print(f"{'effort':>10} {'grounded':>9} {'src/claim':>10} {'latency':>8} {'unsupported':>12}")
    for s in summaries:
        print(f"{s['effort']:>10} {s['avg_groundedness']:>8.0%} "
              f"{s['avg_citation_density']:>10} {s['avg_latency_s']:>7}s "
              f"{s['total_unsupported']:>6}/{s['total_claims']}")


if __name__ == "__main__":
    main()
