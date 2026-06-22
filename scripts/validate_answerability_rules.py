#!/usr/bin/env python3
"""Validate answerability rules used by the dataset generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_RULES_PATH = Path("data/answerability_rules.json")

ALLOWED_CATEGORIES = {
    "clear_answer",
    "clarification_required",
    "genuine_ambiguity",
}

REQUIRED_CATEGORY_FIELDS = {
    "category",
    "label",
    "rule",
    "required_conditions",
    "response_requirements",
    "dataset_requirements",
    "positive_signals",
    "negative_signals",
}

REQUIRED_DATASET_FIELDS = {
    "needs_clarification",
    "required_fields",
    "empty_or_null_fields",
}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def require_non_empty_string(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")


def require_non_empty_string_list(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must be a non-empty array")
        return

    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field}[{index}] must be a non-empty string")


def validate_category(item: Any, index: int) -> list[str]:
    prefix = f"categories[{index}]"
    errors: list[str] = []

    if not isinstance(item, dict):
        return [f"{prefix} must be an object"]

    missing_fields = sorted(REQUIRED_CATEGORY_FIELDS - set(item))
    for field in missing_fields:
        errors.append(f"{prefix} missing required field: {field}")

    category = item.get("category")
    if category not in ALLOWED_CATEGORIES:
        errors.append(f"{prefix}.category must be one of {sorted(ALLOWED_CATEGORIES)}")

    for field in ("label", "rule"):
        require_non_empty_string(item.get(field), f"{prefix}.{field}", errors)

    for field in (
        "required_conditions",
        "response_requirements",
        "positive_signals",
        "negative_signals",
    ):
        require_non_empty_string_list(item.get(field), f"{prefix}.{field}", errors)

    dataset_requirements = item.get("dataset_requirements")
    if not isinstance(dataset_requirements, dict):
        errors.append(f"{prefix}.dataset_requirements must be an object")
        return errors

    missing_dataset_fields = sorted(REQUIRED_DATASET_FIELDS - set(dataset_requirements))
    for field in missing_dataset_fields:
        errors.append(f"{prefix}.dataset_requirements missing required field: {field}")

    if not isinstance(dataset_requirements.get("needs_clarification"), bool):
        errors.append(f"{prefix}.dataset_requirements.needs_clarification must be a boolean")

    for field in ("required_fields", "empty_or_null_fields"):
        require_non_empty_string_list(
            dataset_requirements.get(field),
            f"{prefix}.dataset_requirements.{field}",
            errors,
        )

    if category == "clear_answer":
        if dataset_requirements.get("needs_clarification") is not False:
            errors.append(f"{prefix} clear_answer must not require clarification")
        missing_facts = dataset_requirements.get("missing_facts")
        if missing_facts != []:
            errors.append(f"{prefix}.dataset_requirements.missing_facts must be []")

    if category == "clarification_required":
        if dataset_requirements.get("needs_clarification") is not True:
            errors.append(f"{prefix} clarification_required must require clarification")
        required_fields = set(dataset_requirements.get("required_fields", []))
        for field in ("clarifying_question", "why_clarification_matters", "missing_facts"):
            if field not in required_fields:
                errors.append(f"{prefix}.dataset_requirements.required_fields must include {field}")

    if category == "genuine_ambiguity":
        if dataset_requirements.get("needs_clarification") is not False:
            errors.append(f"{prefix} genuine_ambiguity must not require clarification")
        reasons = item.get("allowed_ambiguity_reasons")
        require_non_empty_string_list(reasons, f"{prefix}.allowed_ambiguity_reasons", errors)
        required_fields = set(dataset_requirements.get("required_fields", []))
        for field in ("ambiguity_reason", "recommended_next_step"):
            if field not in required_fields:
                errors.append(f"{prefix}.dataset_requirements.required_fields must include {field}")

    return errors


def validate(path: Path) -> list[str]:
    rules = load_json(path)
    errors: list[str] = []

    if not isinstance(rules, dict):
        return ["rules file must contain an object"]

    categories = rules.get("categories")
    if not isinstance(categories, list) or not categories:
        return ["rules file must contain a non-empty categories array"]

    seen_categories: set[str] = set()
    for index, item in enumerate(categories):
        errors.extend(validate_category(item, index))
        if isinstance(item, dict):
            category = item.get("category")
            if category in seen_categories:
                errors.append(f"categories[{index}] duplicate category: {category}")
            elif isinstance(category, str):
                seen_categories.add(category)

    missing_categories = sorted(ALLOWED_CATEGORIES - seen_categories)
    if missing_categories:
        errors.append(f"missing categories: {missing_categories}")

    classification_order = rules.get("classification_order")
    if not isinstance(classification_order, list) or len(classification_order) != 3:
        errors.append("classification_order must contain exactly three steps")
    else:
        steps = [item.get("step") for item in classification_order if isinstance(item, dict)]
        if steps != [1, 2, 3]:
            errors.append("classification_order steps must be [1, 2, 3]")
        for index, item in enumerate(classification_order):
            if not isinstance(item, dict):
                errors.append(f"classification_order[{index}] must be an object")
                continue
            require_non_empty_string(
                item.get("instruction"),
                f"classification_order[{index}].instruction",
                errors,
            )

    require_non_empty_string_list(rules.get("global_requirements"), "global_requirements", errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    args = parser.parse_args()

    errors = validate(args.rules)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    rules = load_json(args.rules)
    print(f"validated {len(rules['categories'])} answerability categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
