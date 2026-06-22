#!/usr/bin/env python3
"""Build deterministic judge prompts for Razorpay synthetic Q&A evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from validate_dataset import CRITICAL_FAILURES, SCORING_DIMENSIONS, load_jsonl, validate_rows


DEFAULT_DATASET_PATH = Path("data/synthetic_qa.jsonl")
DEFAULT_PROMPTS_PATH = Path("eval/judge_prompts.jsonl")
PROMPT_VERSION = "judge_rubric_v1"

CATEGORY_DEFINITIONS = {
    "clear_answer": (
        "The ToS explicitly and unambiguously answers the question. A good response gives a direct "
        "answer, cites relevant clauses, and avoids unnecessary follow-up questions."
    ),
    "clarification_required": (
        "The ToS contains a conditional rule, but the user omitted a fact that determines how the "
        "rule applies. A good response asks one targeted clarifying question and explains why that "
        "fact changes the answer."
    ),
    "genuine_ambiguity": (
        "The ToS is silent, vague, discretionary, or depends on external regulation in a way that "
        "prevents a reliable answer from the ToS alone. A good response flags the uncertainty, "
        "states what the ToS does say, and recommends a sensible next step."
    ),
}

RUBRIC = {
    "scale": {
        "1": "poor",
        "3": "acceptable but flawed",
        "5": "excellent",
    },
    "dimensions": {
        "category_correctness": (
            "Does the example belong in the labeled category? Clear-answer examples must be "
            "answerable from the ToS; clarification-required examples must depend on a missing "
            "fact; genuine-ambiguity examples must be unresolved by the ToS alone."
        ),
        "citation_support": (
            "Do the cited clauses actually support the response? Penalize hallucinated citations, "
            "weak citations, and responses that go beyond the cited clause text."
        ),
        "response_quality": (
            "Is the assistant response useful, concise, compliant, and commercially practical?"
        ),
        "clarification_quality": (
            "Only for clarification_required rows. Does the example ask a targeted clarifying "
            "question, and does why_clarification_matters explain the decision point? Return null "
            "for non-clarification rows."
        ),
        "ambiguity_handling": (
            "Only for genuine_ambiguity rows. Does the response honestly flag uncertainty, explain "
            "what is known, and recommend a sensible next step? Return null for non-ambiguity rows."
        ),
        "schema_consistency": (
            "Are the structured fields internally consistent? Examples: needs_clarification is true "
            "only for clarification_required; genuine_ambiguity has ambiguity_reason; clear_answer "
            "has no unnecessary clarifying question; missing_facts align with the response."
        ),
    },
}

JUDGE_OUTPUT_TEMPLATE = {
    "id": "rq-clear-answer-001",
    "scores": {
        "category_correctness": 5,
        "citation_support": 5,
        "response_quality": 4,
        "clarification_quality": None,
        "ambiguity_handling": None,
        "schema_consistency": 5,
    },
    "overall_score": 4.75,
    "passed": True,
    "critical_failures": [],
    "notes": "The response directly answers the question and the cited clause supports it.",
}


def cited_clause_payload(row: dict[str, Any]) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for citation in row["citations"]:
        clauses.append(
            {
                "source_url": citation["source_url"],
                "effective_date": citation["effective_date"],
                "part": citation["part"],
                "section": citation["section"],
                "clause_path": citation["clause_path"],
                "clause_label": citation["clause_label"],
                "evidence_summary": citation["evidence_summary"],
                "source_clause_text": citation["source_clause_text"],
            }
        )
    return clauses


def build_prompt(row: dict[str, Any]) -> str:
    prompt_payload = {
        "prompt_version": PROMPT_VERSION,
        "task": "Evaluate one synthetic Razorpay ToS compliance-assistant training row.",
        "instructions": [
            "Use only the dataset row and cited clause evidence provided here.",
            "Score each applicable dimension from 1 to 5.",
            "Return null for clarification_quality unless category is clarification_required.",
            "Return null for ambiguity_handling unless category is genuine_ambiguity.",
            "Compute overall_score as the average of applicable numeric scores, rounded to 2 decimal places.",
            "Set passed to true only when overall_score is at least 4.0 and critical_failures is empty.",
            "Critical failures override otherwise strong average scores.",
            "Return strict JSON only. Do not include markdown or explanatory prose outside the JSON object.",
        ],
        "assignment_category_definitions": CATEGORY_DEFINITIONS,
        "scoring_rubric": RUBRIC,
        "critical_failure_ids": sorted(CRITICAL_FAILURES),
        "judge_output_schema_example": JUDGE_OUTPUT_TEMPLATE,
        "dataset_row": row,
        "cited_clause_evidence": cited_clause_payload(row),
    }
    return json.dumps(prompt_payload, ensure_ascii=False, indent=2)


def prompt_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "prompt_version": PROMPT_VERSION,
            "prompt": build_prompt(row),
        }
        for row in rows
    ]


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output-prompts", type=Path, default=DEFAULT_PROMPTS_PATH)
    parser.add_argument("--print-prompt-id")
    parser.add_argument("--write-prompts", action="store_true")
    args = parser.parse_args()

    rows, errors = load_jsonl(args.dataset)
    errors.extend(validate_rows(rows))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.print_prompt_id:
        for row in rows:
            if row["id"] == args.print_prompt_id:
                print(build_prompt(row))
                return 0
        print(f"ERROR: no row found for id {args.print_prompt_id}", file=sys.stderr)
        return 1

    records = prompt_records(rows)
    if args.write_prompts:
        write_jsonl(records, args.output_prompts)
        print(f"wrote {len(records)} judge prompts to {args.output_prompts}")
    else:
        print(f"built {len(records)} judge prompts with {PROMPT_VERSION}")
        print("use --write-prompts to write eval/judge_prompts.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
