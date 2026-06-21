#!/usr/bin/env python3
"""Validate the Razorpay clause inventory against the normalized ToS source."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_INVENTORY_PATH = Path("data/razorpay_clause_inventory.json")
DEFAULT_TERMS_PATH = Path("data/razorpay_terms_normalized.json")

REQUIRED_TOPICS = {
    "fees",
    "refunds",
    "chargebacks",
    "fraud",
    "settlements",
    "prohibited goods",
    "gaming",
    "marketplace/sub-merchants",
    "tax",
    "data",
    "suspension",
    "cross-border",
}

REQUIRED_ITEM_FIELDS = {
    "topic_id",
    "topic",
    "source_clause_ids",
    "clause_paths",
    "legal_commercial_meaning",
    "legal_issue_tags",
    "product_tags",
    "supports_answerability",
    "clear_answer_uses",
    "clarification_triggers",
    "ambiguity_triggers",
}

ALLOWED_ANSWERABILITY = {
    "clear_answer",
    "clarification_required",
    "genuine_ambiguity",
}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate(inventory_path: Path, terms_path: Path) -> list[str]:
    inventory = load_json(inventory_path)
    terms = load_json(terms_path)
    source_clause_ids = {clause["id"] for clause in terms.get("clauses", [])}

    errors: list[str] = []
    topics = inventory.get("topics")
    if not isinstance(topics, list) or not topics:
        return ["inventory must contain a non-empty topics array"]

    seen_topic_ids: set[str] = set()
    covered_topics: set[str] = set()

    for index, item in enumerate(topics):
        prefix = f"topics[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue

        missing_fields = sorted(REQUIRED_ITEM_FIELDS - set(item))
        for field in missing_fields:
            errors.append(f"{prefix} missing required field: {field}")

        topic_id = item.get("topic_id")
        if topic_id in seen_topic_ids:
            errors.append(f"{prefix} duplicate topic_id: {topic_id}")
        elif isinstance(topic_id, str):
            seen_topic_ids.add(topic_id)

        topic = item.get("topic")
        if isinstance(topic, str):
            covered_topics.add(topic)

        clause_ids = item.get("source_clause_ids")
        if not isinstance(clause_ids, list) or not clause_ids:
            errors.append(f"{prefix}.source_clause_ids must be a non-empty array")
        else:
            for clause_id in clause_ids:
                if clause_id not in source_clause_ids:
                    errors.append(f"{prefix} references unknown clause id: {clause_id}")

        answerability = item.get("supports_answerability")
        if not isinstance(answerability, list) or not answerability:
            errors.append(f"{prefix}.supports_answerability must be a non-empty array")
        else:
            invalid = sorted(set(answerability) - ALLOWED_ANSWERABILITY)
            if invalid:
                errors.append(f"{prefix}.supports_answerability has invalid values: {invalid}")

        for field in ("legal_issue_tags", "product_tags", "clause_paths"):
            value = item.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"{prefix}.{field} must be a non-empty array")

    missing_topics = sorted(REQUIRED_TOPICS - covered_topics)
    if missing_topics:
        errors.append(f"missing required topics: {missing_topics}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY_PATH)
    parser.add_argument("--terms", type=Path, default=DEFAULT_TERMS_PATH)
    args = parser.parse_args()

    errors = validate(args.inventory, args.terms)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    inventory = load_json(args.inventory)
    print(f"validated {len(inventory['topics'])} inventory topics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
