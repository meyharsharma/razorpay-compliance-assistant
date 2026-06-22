#!/usr/bin/env python3
"""Generate deterministic synthetic Razorpay ToS Q&A examples."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


DEFAULT_TERMS_PATH = Path("data/razorpay_terms_normalized.json")
DEFAULT_INVENTORY_PATH = Path("data/razorpay_clause_inventory.json")
DEFAULT_OUTPUT_PATH = Path("data/synthetic_qa.jsonl")
DEFAULT_SEED = 42
SOURCE_DOC_VERSION = "razorpay_terms_2026_01_01"

CATEGORIES = ("clear_answer", "clarification_required", "genuine_ambiguity")
PER_CATEGORY = 15


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def compact(text: str, limit: int = 220) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def clause_label(clause: dict[str, Any]) -> str:
    hierarchy = clause.get("hierarchy", {})
    for key in ("clause", "subclause", "item"):
        value = hierarchy.get(key)
        if value:
            return str(value)
    marker = clause.get("marker")
    if marker:
        return str(marker)
    section_title = hierarchy.get("section_title")
    return str(section_title or "Clause")


def section_name(clause: dict[str, Any]) -> str | None:
    hierarchy = clause.get("hierarchy", {})
    return hierarchy.get("section_title") or hierarchy.get("clause_title")


def part_name(clause: dict[str, Any]) -> str:
    hierarchy = clause.get("hierarchy", {})
    part = hierarchy.get("part") or "Unknown part"
    title = hierarchy.get("part_title")
    return f"{part}: {title}" if title else str(part)


def build_citations(
    topic: dict[str, Any],
    clauses_by_id: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
    max_citations: int = 2,
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    effective_date = metadata.get("effective_date") or metadata["effective_date_iso"]
    candidate_ids = [
        clause_id
        for clause_id in topic["source_clause_ids"]
        if "DEFINITIONS" not in clauses_by_id[clause_id]["clause_path_text"]
    ]
    if not candidate_ids:
        candidate_ids = topic["source_clause_ids"]

    for clause_id in candidate_ids[:max_citations]:
        clause = clauses_by_id[clause_id]
        citations.append(
            {
                "source_url": metadata["source_url"],
                "effective_date": effective_date,
                "part": part_name(clause),
                "section": section_name(clause),
                "clause_path": clause["clause_path_text"],
                "clause_label": clause_label(clause),
                "evidence_summary": compact(clause.get("text_without_marker") or clause.get("text") or ""),
            }
        )
    return citations


def citation_names(citations: list[dict[str, Any]]) -> str:
    return "; ".join(citation["clause_path"] for citation in citations)


def pick(values: list[str], index: int) -> str:
    return values[index % len(values)]


def clarifying_question(trigger: str, topic: dict[str, Any]) -> str:
    topic_name = topic["topic"]
    if trigger.lower().startswith("whether"):
        stem = trigger[8:]
        return f"Can you confirm whether {stem}?"
    if trigger.lower().startswith("which"):
        return f"Which {trigger[6:]}?"
    return f"Can you confirm the {trigger[0].lower() + trigger[1:]}?"


def missing_fact_name(trigger: str) -> str:
    return trigger[0].lower() + trigger[1:]


def clear_question(use: str, topic: dict[str, Any], index: int) -> str:
    openers = [
        "Quick compliance check:",
        "Finance is asking:",
        "For the product note, can we say",
        "Ops question:",
        "Before we reply internally,",
    ]
    opener = pick(openers, index)
    question = use[0].lower() + use[1:]
    if opener.endswith(":"):
        return f"{opener} {question} under the Razorpay terms?"
    return f"{opener} {question} under the Razorpay terms?"


def clear_response(use: str, topic: dict[str, Any], citations: list[dict[str, Any]]) -> str:
    return (
        f"Yes. The ToS directly answers this point: {topic['legal_commercial_meaning']} "
        f"This is supported by {citation_names(citations)}. No additional merchant fact is needed "
        f"to answer this specific question from the terms."
    )


def clarification_question(trigger: str, topic: dict[str, Any], index: int) -> str:
    prompts = [
        "Can we answer the ToS question yet",
        "Need a quick read from the terms",
        "Support wants to know the answer",
        "For this merchant escalation, can we decide the ToS position",
        "Can legal ops confirm the answer",
    ]
    base = pick(prompts, index)
    fact = missing_fact_name(trigger)
    return f"{base} if we do not know {fact}?"


def clarification_response(
    trigger: str,
    topic: dict[str, Any],
    citations: list[dict[str, Any]],
) -> tuple[str, str, str]:
    question = clarifying_question(trigger, topic)
    why = (
        f"The ToS has a conditional rule for {topic['topic']}: {topic['legal_commercial_meaning']} "
        f"The answer changes based on {missing_fact_name(trigger)}."
    )
    response = (
        f"I need one fact before giving a yes/no answer. {question} {why} "
        f"The relevant ToS support is {citation_names(citations)}."
    )
    return response, question, why


def ambiguity_question(trigger: str, topic: dict[str, Any], index: int) -> str:
    prompts = [
        "Can we rely on the Razorpay ToS alone to determine",
        "Does the ToS give us a final answer on",
        "Do the terms specify",
        "Can we tell the business exactly",
        "Is there a fixed ToS rule for",
    ]
    prompt = pick(prompts, index)
    scenario = ambiguity_question_object(trigger)
    return f"{prompt} {scenario}?"


def ambiguity_question_object(trigger: str) -> str:
    lowered = trigger.lower()
    if "exact fee amount" in lowered:
        return "the exact fee amount, rate, or future pricing change"
    if "operational slas" in lowered:
        return "the operational SLA for every refund rail and customer-facing refund policy"
    if "facility provider" in lowered:
        return "what the Facility Provider will ultimately decide"
    if "post-settlement fraud" in lowered:
        return "how a post-settlement fraud dispute must be resolved without checking RBI or NPCI materials"
    if "maximum hold period" in lowered:
        return "the maximum period Razorpay can hold settlement amounts"
    if "borderline products" in lowered:
        return "whether a borderline product category is allowed"
    if "classification of a game" in lowered:
        return "whether a game is legally classified as prohibited gaming or gambling"
    if "licenses" in lowered or "permits" in lowered:
        return "the exact permits and due-diligence scope for the marketplace"
    if "kyc document set" in lowered:
        return "the exact KYC documents Razorpay will accept as sufficient"
    if "actual tax treatment" in lowered:
        return "the merchant's final tax treatment"
    if "privacy policy" in lowered:
        return "all privacy-law obligations without reviewing the incorporated policy or applicable law"
    if "maximum suspension" in lowered:
        return "a universal maximum suspension or settlement-hold duration"
    if "final remittance timing" in lowered:
        return "final cross-border remittance timing and compliance outcome"
    if "pricing terms" in lowered or "supplemental" in lowered:
        return "all product-specific operational details without the supplemental documents"
    return trigger[0].lower() + trigger[1:]


def ambiguity_reason(trigger: str) -> str:
    lowered = trigger.lower()
    if "external" in lowered or "law" in lowered or "rbi" in lowered or "npci" in lowered:
        return "external_regulation"
    if "discretion" in lowered or "suitable" in lowered:
        return "razorpay_discretion"
    if "undefined" in lowered:
        return "undefined_term"
    if "jurisdiction" in lowered:
        return "jurisdiction_dependent"
    return "tos_silent"


def recommended_next_step(reason: str) -> str:
    steps = {
        "external_regulation": "Check the applicable RBI, NPCI, tax, banking, or other external rule and have counsel confirm the result.",
        "razorpay_discretion": "Ask Razorpay for written clarification on how it will exercise the discretion in this scenario.",
        "undefined_term": "Ask Razorpay or legal counsel to confirm the intended interpretation before relying on the term.",
        "jurisdiction_dependent": "Confirm the merchant and transaction jurisdictions, then obtain jurisdiction-specific legal review.",
        "tos_silent": "Ask Razorpay support or legal counsel for confirmation because the ToS does not state a complete rule.",
    }
    return steps[reason]


def ambiguity_response(
    trigger: str,
    topic: dict[str, Any],
    citations: list[dict[str, Any]],
) -> tuple[str, str, str]:
    reason = ambiguity_reason(trigger)
    next_step = recommended_next_step(reason)
    response = (
        f"Not from the ToS alone. The terms say this about {topic['topic']}: "
        f"{topic['legal_commercial_meaning']} The unresolved point is that {trigger[0].lower() + trigger[1:]}. "
        f"The relevant clauses are {citation_names(citations)}. {next_step}"
    )
    return response, reason, next_step


def make_base_row(
    category: str,
    index: int,
    topic: dict[str, Any],
    citations: list[dict[str, Any]],
    seed: int,
) -> dict[str, Any]:
    return {
        "id": f"rq-{category.replace('_', '-')}-{index + 1:03d}",
        "category": category,
        "user_question": "",
        "assistant_response": "",
        "needs_clarification": category == "clarification_required",
        "clarifying_question": None,
        "why_clarification_matters": None,
        "ambiguity_reason": None,
        "recommended_next_step": None,
        "citations": citations,
        "legal_issue_tags": topic["legal_issue_tags"],
        "product_tags": topic["product_tags"],
        "merchant_context_assumed": {},
        "missing_facts": [],
        "confidence": "high" if category == "clear_answer" else "medium",
        "generation_metadata": {
            "source_doc_version": SOURCE_DOC_VERSION,
            "script_seed": seed,
            "deterministic": True,
            "template_id": f"{topic['topic_id']}_{category}_{index + 1:03d}",
            "model_id": None,
        },
    }


def generate_examples(
    terms_path: Path,
    inventory_path: Path,
    seed: int,
    per_category: int = PER_CATEGORY,
) -> list[dict[str, Any]]:
    random.Random(seed)
    terms = load_json(terms_path)
    inventory = load_json(inventory_path)
    metadata = terms["metadata"]
    clauses_by_id = {clause["id"]: clause for clause in terms["clauses"]}
    topics = inventory["topics"]

    rows: list[dict[str, Any]] = []
    for category in CATEGORIES:
        supported = [topic for topic in topics if category in topic["supports_answerability"]]
        if len(supported) < 1:
            raise ValueError(f"no inventory topics support {category}")

        for index in range(per_category):
            topic = supported[index % len(supported)]
            citations = build_citations(topic, clauses_by_id, metadata)
            row = make_base_row(category, index, topic, citations, seed)

            if category == "clear_answer":
                use = pick(topic["clear_answer_uses"], index)
                row["user_question"] = clear_question(use, topic, index)
                row["assistant_response"] = clear_response(use, topic, citations)

            elif category == "clarification_required":
                trigger = pick(topic["clarification_triggers"], index)
                response, question, why = clarification_response(trigger, topic, citations)
                row["user_question"] = clarification_question(trigger, topic, index)
                row["assistant_response"] = response
                row["clarifying_question"] = question
                row["why_clarification_matters"] = why
                row["missing_facts"] = [missing_fact_name(trigger)]

            else:
                trigger = pick(topic["ambiguity_triggers"], index)
                response, reason, next_step = ambiguity_response(trigger, topic, citations)
                row["user_question"] = ambiguity_question(trigger, topic, index)
                row["assistant_response"] = response
                row["ambiguity_reason"] = reason
                row["recommended_next_step"] = next_step
                row["confidence"] = "medium" if reason in {"razorpay_discretion", "external_regulation"} else "low"

            rows.append(row)

    return rows


def write_jsonl(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terms", type=Path, default=DEFAULT_TERMS_PATH)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--per-category", type=int, default=PER_CATEGORY)
    args = parser.parse_args()

    rows = generate_examples(args.terms, args.inventory, args.seed, args.per_category)
    write_jsonl(rows, args.output)
    print(f"wrote {len(rows)} examples to {args.output}")
    for category in CATEGORIES:
        print(f"{category}: {sum(1 for row in rows if row['category'] == category)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
