#!/usr/bin/env python3
"""Validate generated Razorpay synthetic Q&A JSONL examples."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_DATASET_PATH = Path("data/synthetic_qa.jsonl")
ALLOWED_CATEGORIES = {"clear_answer", "clarification_required", "genuine_ambiguity"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
MIN_TOTAL = 45
MIN_PER_CATEGORY = 15
GENERIC_CLARIFICATION_PHRASES = {
    "can you provide more details",
    "please provide more details",
    "can you clarify",
    "need more information",
    "need more details",
}

REQUIRED_FIELDS = {
    "id",
    "category",
    "user_question",
    "assistant_response",
    "needs_clarification",
    "clarifying_question",
    "why_clarification_matters",
    "ambiguity_reason",
    "recommended_next_step",
    "citations",
    "legal_issue_tags",
    "product_tags",
    "merchant_context_assumed",
    "missing_facts",
    "confidence",
    "generation_metadata",
}

REQUIRED_CITATION_FIELDS = {
    "source_url",
    "effective_date",
    "part",
    "section",
    "clause_path",
    "clause_label",
    "evidence_summary",
}


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON: {exc}")
                continue
            if not isinstance(row, dict):
                errors.append(f"line {line_number}: row must be an object")
                continue
            rows.append(row)
    return rows, errors


def require_text(row: dict[str, Any], field: str, prefix: str, errors: list[str]) -> None:
    if not isinstance(row.get(field), str) or not row[field].strip():
        errors.append(f"{prefix}.{field} must be a non-empty string")


def require_list(row: dict[str, Any], field: str, prefix: str, errors: list[str]) -> None:
    if not isinstance(row.get(field), list) or not row[field]:
        errors.append(f"{prefix}.{field} must be a non-empty array")


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_targeted_clarifying_question(row: dict[str, Any], prefix: str, errors: list[str]) -> None:
    question = row.get("clarifying_question")
    if not has_text(question):
        return

    normalized = " ".join(question.lower().split())
    if not question.strip().endswith("?"):
        errors.append(f"{prefix}.clarifying_question must be phrased as a question")
    if question.count("?") != 1:
        errors.append(f"{prefix}.clarifying_question must ask exactly one targeted question")
    if normalized in GENERIC_CLARIFICATION_PHRASES:
        errors.append(f"{prefix}.clarifying_question must be targeted, not a generic follow-up")
    if len(question.split()) < 5:
        errors.append(f"{prefix}.clarifying_question is too short to be a targeted question")

    missing_facts = row.get("missing_facts")
    if isinstance(missing_facts, list) and missing_facts:
        question_words = set(normalized.replace("?", "").split())
        matched_fact = False
        for fact in missing_facts:
            if not isinstance(fact, str):
                continue
            fact_words = [word for word in fact.lower().replace("_", " ").split() if len(word) > 3]
            if fact_words and any(word in question_words for word in fact_words):
                matched_fact = True
                break
        if not matched_fact:
            errors.append(f"{prefix}.clarifying_question must target at least one listed missing fact")


def validate_citations(row: dict[str, Any], prefix: str, errors: list[str]) -> None:
    citations = row.get("citations")
    if not isinstance(citations, list) or not citations:
        errors.append(f"{prefix}.citations must contain at least one citation")
        return

    for index, citation in enumerate(citations):
        citation_prefix = f"{prefix}.citations[{index}]"
        if not isinstance(citation, dict):
            errors.append(f"{citation_prefix} must be an object")
            continue
        missing = sorted(REQUIRED_CITATION_FIELDS - set(citation))
        for field in missing:
            errors.append(f"{citation_prefix} missing required field: {field}")
        for field in REQUIRED_CITATION_FIELDS:
            if field == "section" and citation.get(field) is None:
                continue
            if not isinstance(citation.get(field), str) or not str(citation.get(field)).strip():
                errors.append(f"{citation_prefix}.{field} must be a non-empty string")


def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if len(rows) < MIN_TOTAL:
        errors.append(f"dataset must contain at least {MIN_TOTAL} examples")

    ids = [row.get("id") for row in rows]
    duplicates = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate ids: {duplicates}")

    counts = Counter(row.get("category") for row in rows)
    for category in sorted(ALLOWED_CATEGORIES):
        if counts[category] < MIN_PER_CATEGORY:
            errors.append(
                f"{category} must have at least {MIN_PER_CATEGORY} examples; found {counts[category]}"
            )

    for index, row in enumerate(rows):
        prefix = f"rows[{index}]"
        missing = sorted(REQUIRED_FIELDS - set(row))
        for field in missing:
            errors.append(f"{prefix} missing required field: {field}")

        category = row.get("category")
        if category not in ALLOWED_CATEGORIES:
            errors.append(f"{prefix}.category must be one of {sorted(ALLOWED_CATEGORIES)}")

        for field in ("id", "user_question", "assistant_response", "confidence"):
            require_text(row, field, prefix, errors)
        if row.get("confidence") not in ALLOWED_CONFIDENCE:
            errors.append(f"{prefix}.confidence must be one of {sorted(ALLOWED_CONFIDENCE)}")

        if not isinstance(row.get("needs_clarification"), bool):
            errors.append(f"{prefix}.needs_clarification must be a boolean")
        if not isinstance(row.get("merchant_context_assumed"), dict):
            errors.append(f"{prefix}.merchant_context_assumed must be an object")
        if not isinstance(row.get("generation_metadata"), dict):
            errors.append(f"{prefix}.generation_metadata must be an object")

        for field in ("legal_issue_tags", "product_tags"):
            require_list(row, field, prefix, errors)
        validate_citations(row, prefix, errors)

        if category == "clear_answer":
            if row.get("needs_clarification") is not False:
                errors.append(f"{prefix}.needs_clarification must be false for clear_answer")
            if not isinstance(row.get("citations"), list) or not row["citations"]:
                errors.append(f"{prefix}.citations must be present for every clear_answer")
            for field in (
                "clarifying_question",
                "why_clarification_matters",
                "ambiguity_reason",
                "recommended_next_step",
            ):
                if row.get(field) is not None:
                    errors.append(f"{prefix}.{field} must be null for clear_answer")
            if row.get("missing_facts") != []:
                errors.append(f"{prefix}.missing_facts must be [] for clear_answer")

        if category == "clarification_required":
            if row.get("needs_clarification") is not True:
                errors.append(f"{prefix}.needs_clarification must be true for clarification_required")
            for field in ("clarifying_question", "why_clarification_matters"):
                require_text(row, field, prefix, errors)
            require_list(row, "missing_facts", prefix, errors)
            validate_targeted_clarifying_question(row, prefix, errors)
            if row.get("ambiguity_reason") is not None or row.get("recommended_next_step") is not None:
                errors.append(f"{prefix} ambiguity fields must be null for clarification_required")

        if category == "genuine_ambiguity":
            if row.get("needs_clarification") is not False:
                errors.append(f"{prefix}.needs_clarification must be false for genuine_ambiguity")
            for field in ("ambiguity_reason", "recommended_next_step"):
                require_text(row, field, prefix, errors)
            if row.get("clarifying_question") is not None or row.get("why_clarification_matters") is not None:
                errors.append(f"{prefix} clarification fields must be null for genuine_ambiguity")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    args = parser.parse_args()

    rows, errors = load_jsonl(args.dataset)
    errors.extend(validate_rows(rows))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    counts = Counter(row["category"] for row in rows)
    print(f"validated {len(rows)} examples")
    for category in sorted(ALLOWED_CATEGORIES):
        print(f"{category}: {counts[category]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
