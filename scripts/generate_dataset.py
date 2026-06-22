#!/usr/bin/env python3
"""Generate deterministic synthetic Razorpay ToS Q&A examples."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from validate_dataset import validate_rows


DEFAULT_TERMS_PATH = Path("data/razorpay_terms_normalized.json")
DEFAULT_INVENTORY_PATH = Path("data/razorpay_clause_inventory.json")
DEFAULT_OUTPUT_PATH = Path("data/synthetic_qa.jsonl")
DEFAULT_SEED = 42
SOURCE_DOC_VERSION = "razorpay_terms_2026_01_01"

CATEGORIES = ("clear_answer", "clarification_required", "genuine_ambiguity")
PER_CATEGORY = 15
SCORING_DIMENSIONS = (
    "category_correctness",
    "citation_support",
    "response_quality",
    "clarification_quality",
    "ambiguity_handling",
    "schema_consistency",
)

CATEGORY_TOPIC_SEQUENCE = {
    "clear_answer": [
        "refunds_payment_aggregation",
        "refunds_payment_aggregation",
        "fees_general",
        "chargebacks",
        "fraudulent_transactions",
        "settlements_holds_and_deductions",
        "prohibited_goods_and_services",
        "gaming_and_gambling",
        "marketplace_and_sub_merchants",
        "kyc_onboarding_monitoring",
        "tax_and_invoicing",
        "data_protection_and_tokenization",
        "suspension_and_termination",
        "cross_border_outward",
        "product_specific_terms",
    ],
    "clarification_required": [
        "fraudulent_transactions",
        "fraudulent_transactions",
        "refunds_payment_aggregation",
        "chargebacks",
        "settlements_holds_and_deductions",
        "prohibited_goods_and_services",
        "gaming_and_gambling",
        "marketplace_and_sub_merchants",
        "kyc_onboarding_monitoring",
        "tax_and_invoicing",
        "data_protection_and_tokenization",
        "suspension_and_termination",
        "cross_border_outward",
        "product_specific_terms",
        "fees_general",
    ],
    "genuine_ambiguity": [
        "gaming_and_gambling",
        "suspension_and_termination",
        "fees_general",
        "refunds_payment_aggregation",
        "chargebacks",
        "fraudulent_transactions",
        "settlements_holds_and_deductions",
        "prohibited_goods_and_services",
        "marketplace_and_sub_merchants",
        "kyc_onboarding_monitoring",
        "tax_and_invoicing",
        "data_protection_and_tokenization",
        "cross_border_outward",
        "product_specific_terms",
        "gaming_and_gambling",
    ],
}

QUESTION_BANK = {
    "clear_answer": {
        "refunds_payment_aggregation": [
            "We refunded a customer their full payment. Do we still have to pay Razorpay their processing fee?",
            "A customer paid via UPI but we never captured the payment. What happens to their money?",
            "If we issue a refund, does Razorpay send it back to the same payment method the customer used?",
        ],
        "fees_general": [
            "When Razorpay quotes fees to us, are taxes charged on top of those fees?",
            "Where should finance look for Razorpay's monthly fee invoices?",
        ],
        "chargebacks": [
            "A card network raised a chargeback. Are we responsible for the chargeback amount under the Razorpay terms?",
            "If there is not enough settlement money to cover a chargeback, can Razorpay send us a debit note?",
        ],
        "fraudulent_transactions": [
            "If a transaction turns out to be fraudulent, does Razorpay take responsibility for the liability?",
            "Do we have to help Razorpay and the banks respond to fraud complaints and queries?",
        ],
        "settlements_holds_and_deductions": [
            "For a domestic payment, is the default settlement timeline five days after money reaches the escrow account?",
            "Can Razorpay deduct fees, chargebacks, penalties, or fines before settling money to us?",
        ],
        "prohibited_goods_and_services": [
            "Can we use Razorpay to accept payments for NFTs or other crypto products?",
            "Can one of our sellers process gambling-related payments through our Razorpay setup?",
        ],
        "gaming_and_gambling": [
            "Can we collect Razorpay payments for real-money online gaming?",
            "Are sports betting or lottery payments allowed under the Razorpay terms?",
        ],
        "marketplace_and_sub_merchants": [
            "For our marketplace, do sellers need to be onboarded and contractually tied to us before we accept Razorpay payments for them?",
            "If a sub-merchant violates the Razorpay terms, are we still responsible to Razorpay?",
        ],
        "kyc_onboarding_monitoring": [
            "Can Razorpay ask us for additional KYC documents after onboarding?",
            "Can inaccurate business information lead to suspension or termination?",
        ],
        "tax_and_invoicing": [
            "Who is responsible for keeping our GSTIN and tax details accurate in Razorpay?",
            "If we are an e-commerce operator, does Razorpay say it must deduct Section 194O TDS for us?",
        ],
        "data_protection_and_tokenization": [
            "Can our custom checkout store full card credentials after a customer pays?",
            "If we suspect a customer data breach, do we need to notify Razorpay within 24 hours?",
        ],
        "suspension_and_termination": [
            "Can Razorpay immediately suspend our services and settlements if it believes we are using the platform unlawfully?",
            "If the agreement is terminated, do our already-accrued payment obligations disappear?",
        ],
        "cross_border_outward": [
            "We are based outside India and collect from Indian customers. Do the cross-border outward terms apply to us?",
            "For cross-border outward payments, can Razorpay settle before the escrow account is credited?",
        ],
        "product_specific_terms": [
            "If the product-specific terms conflict with the general Razorpay terms, which set of terms controls?",
            "For e-mandates, does onboarding depend on Sponsor Bank registration?",
        ],
    },
    "clarification_required": {
        "fraudulent_transactions": [
            "A customer says their card was used without their permission. Can Razorpay hold our settlement money?",
            "A fraudulent transaction happened and Razorpay already settled the money to us. What happens now?",
            "If a fraud report comes in, can we tell finance that Razorpay will definitely pause settlement?",
        ],
        "refunds_payment_aggregation": [
            "A customer wants a refund today. Can Razorpay process it for us?",
            "We have an uncaptured late-authorized payment. Will Razorpay auto-refund it?",
        ],
        "chargebacks": [
            "Razorpay asked for chargeback documents. Do we still have time to submit them?",
            "Can Razorpay withhold settlement after termination for possible chargebacks?",
        ],
        "settlements_holds_and_deductions": [
            "A payout has not arrived yet. Is Razorpay late under the settlement timeline?",
            "Can we promise the merchant that their international settlement will arrive within the domestic timeline?",
        ],
        "prohibited_goods_and_services": [
            "Our product has crypto-adjacent rewards but no token trading. Is it prohibited on Razorpay?",
            "A seller wants to list a regulated product. Can we process payments for it?",
        ],
        "gaming_and_gambling": [
            "The product team says this is a skill game with prizes. Can we use Razorpay for payments?",
            "Can we process entry fees for a tournament that pays cash prizes?",
        ],
        "marketplace_and_sub_merchants": [
            "We want to process payments for third-party sellers. Does Razorpay allow that?",
            "Can settlement go directly to a third party instead of our merchant account?",
        ],
        "kyc_onboarding_monitoring": [
            "Razorpay asked for more documents. Can it stop settlement until we provide them?",
            "A regulator asked Razorpay for customer documents. Do we have to provide them?",
        ],
        "tax_and_invoicing": [
            "Should Razorpay withhold tax on this cross-border settlement?",
            "Do the LRS and TCS declaration obligations apply to this transaction?",
        ],
        "data_protection_and_tokenization": [
            "Can our integration store this payment data for reconciliation?",
            "Do we need PCI DSS or PA-DSS compliance for this flow?",
        ],
        "suspension_and_termination": [
            "Razorpay paused our settlement. Is that allowed under the suspension clause?",
            "Can either side terminate at will here, or does another agreement change that?",
        ],
        "cross_border_outward": [
            "We have an overseas merchant collecting from Indian customers. Which Razorpay cross-border rules apply?",
            "Can Razorpay hold a PA-CB outward settlement until documents are provided?",
        ],
        "product_specific_terms": [
            "We are using Magic Checkout. Do the general terms answer this, or do product-specific terms apply?",
            "For tokenization, is Razorpay acting as a technical service provider or as the payment aggregator?",
        ],
        "fees_general": [
            "Razorpay changed pricing for a value-added service. Can we tell finance the exact fee from the ToS?",
            "We have fee credits on the account. Will Razorpay deduct fees from credits or settlement?",
        ],
    },
    "genuine_ambiguity": {
        "gaming_and_gambling": [
            "We're building a real-money gaming feature. Can we use Razorpay to collect payments for it?",
            "Our game involves skill, prizes, and paid entry. Do the Razorpay terms alone tell us whether it is allowed?",
        ],
        "suspension_and_termination": [
            "Razorpay suspended our account under Clause 16. How long can they hold our funds?",
            "Razorpay says our activity looked suspicious. Do the terms give a fixed deadline for restoring settlement?",
        ],
        "fees_general": [
            "Can we calculate Razorpay's exact future processing fee from the ToS alone?",
            "Does the ToS lock Razorpay into today's pricing forever?",
        ],
        "refunds_payment_aggregation": [
            "What is the exact SLA for every Razorpay refund rail and customer bank?",
            "Do the terms fully define what our customer-facing refund policy must say?",
        ],
        "chargebacks": [
            "Can the ToS alone tell us how the Facility Provider will decide this chargeback?",
            "If the bank asks for a different document timeline, do the Razorpay terms fully resolve the conflict?",
        ],
        "fraudulent_transactions": [
            "For a fraud dispute after settlement, can we answer without checking RBI or NPCI rules?",
            "Do the Razorpay terms fully define every fraud-liability threshold we need to apply?",
        ],
        "settlements_holds_and_deductions": [
            "If Razorpay thinks settlement is not feasible, do the terms give a universal maximum hold period?",
            "Can we tell a merchant the exact release date for every risk hold from the ToS alone?",
        ],
        "prohibited_goods_and_services": [
            "Our product is near a prohibited category but not listed exactly. Do the terms alone decide if Razorpay allows it?",
            "If Razorpay or a bank updates a prohibited category, can the static ToS tell us the final answer?",
        ],
        "marketplace_and_sub_merchants": [
            "What exact permits do we need for every marketplace seller and jurisdiction?",
            "Do the terms fully define the due diligence we must run on every sub-merchant?",
        ],
        "kyc_onboarding_monitoring": [
            "What exact KYC documents will Razorpay consider sufficient for this merchant?",
            "Can the ToS alone tell us when Razorpay will be satisfied with our onboarding documents?",
        ],
        "tax_and_invoicing": [
            "Can the Razorpay terms alone tell us the final tax treatment for this cross-border payout?",
            "Do the terms replace tax advice for GST, TDS, TCS, and withholding questions?",
        ],
        "data_protection_and_tokenization": [
            "Do the Razorpay terms alone list every privacy-law obligation we have for customer data?",
            "Can we skip reviewing the Privacy Policy because the ToS covers all data-protection duties?",
        ],
        "cross_border_outward": [
            "Can we promise the exact remittance date for a cross-border outward transaction from the ToS alone?",
            "Do the terms alone decide all FEMA, RBI, LRS, and tax compliance questions for this payment?",
        ],
        "product_specific_terms": [
            "Do the general terms alone tell us every operational detail for Magic Checkout?",
            "Can we answer offline-device pricing questions without checking the product pricing terms?",
        ],
    },
}

PREFERRED_CITATIONS = {
    "clear_answer": {
        "refunds_payment_aggregation": [
            ["clause-0202"],
            ["clause-0203"],
            ["clause-0201"],
        ],
        "fees_general": [["clause-0078"], ["clause-0079"]],
        "chargebacks": [["clause-0195"], ["clause-0193"]],
        "fraudulent_transactions": [["clause-0207"], ["clause-0208"]],
        "settlements_holds_and_deductions": [["clause-0181"], ["clause-0189", "clause-0191"]],
        "prohibited_goods_and_services": [["clause-0169"], ["clause-0145", "clause-0167"]],
        "gaming_and_gambling": [["clause-0145", "clause-0167"], ["clause-0145"]],
        "marketplace_and_sub_merchants": [["clause-0322", "clause-0323"], ["clause-0329", "clause-0330"]],
        "kyc_onboarding_monitoring": [["clause-0041", "clause-0043"], ["clause-0037", "clause-0043"]],
        "tax_and_invoicing": [["clause-0082"], ["clause-0084"]],
        "data_protection_and_tokenization": [["clause-0098"], ["clause-0099"]],
        "suspension_and_termination": [["clause-0119", "clause-0124"], ["clause-0131"]],
        "cross_border_outward": [["clause-0307", "clause-0308"], ["clause-0312"]],
        "product_specific_terms": [["clause-0209"], ["clause-0352"]],
    },
    "clarification_required": {
        "fraudulent_transactions": [
            ["clause-0204"],
            ["clause-0205", "clause-0206", "clause-0208"],
            ["clause-0204"],
        ],
        "refunds_payment_aggregation": [["clause-0199", "clause-0200"], ["clause-0203"]],
        "chargebacks": [["clause-0193", "clause-0194"], ["clause-0196"]],
        "settlements_holds_and_deductions": [["clause-0181", "clause-0183"], ["clause-0183"]],
        "prohibited_goods_and_services": [["clause-0169"], ["clause-0174"]],
        "gaming_and_gambling": [["clause-0145", "clause-0167"], ["clause-0145"]],
        "marketplace_and_sub_merchants": [["clause-0322", "clause-0323"], ["clause-0328"]],
        "kyc_onboarding_monitoring": [["clause-0041", "clause-0043"], ["clause-0218", "clause-0219"]],
        "tax_and_invoicing": [["clause-0313", "clause-0314"], ["clause-0336", "clause-0340"]],
        "data_protection_and_tokenization": [["clause-0096", "clause-0098"], ["clause-0097"]],
        "suspension_and_termination": [["clause-0119", "clause-0124"], ["clause-0130"]],
        "cross_border_outward": [["clause-0307", "clause-0308"], ["clause-0312", "clause-0313"]],
        "product_specific_terms": [["clause-0209"], ["clause-0399", "clause-0406"]],
        "fees_general": [["clause-0077", "clause-0232"], ["clause-0188"]],
    },
    "genuine_ambiguity": {
        "gaming_and_gambling": [["clause-0145", "clause-0167"], ["clause-0145", "clause-0167"]],
        "suspension_and_termination": [["clause-0119", "clause-0124"], ["clause-0119", "clause-0124"]],
        "fees_general": [["clause-0077", "clause-0107"], ["clause-0077"]],
        "refunds_payment_aggregation": [["clause-0199", "clause-0200"], ["clause-0201", "clause-0202"]],
        "chargebacks": [["clause-0193", "clause-0194"], ["clause-0193"]],
        "fraudulent_transactions": [["clause-0205", "clause-0206", "clause-0208"], ["clause-0208"]],
        "settlements_holds_and_deductions": [["clause-0183", "clause-0186"], ["clause-0183", "clause-0225"]],
        "prohibited_goods_and_services": [["clause-0174"], ["clause-0177"]],
        "marketplace_and_sub_merchants": [["clause-0322", "clause-0328"], ["clause-0324", "clause-0329"]],
        "kyc_onboarding_monitoring": [["clause-0041", "clause-0043"], ["clause-0043"]],
        "tax_and_invoicing": [["clause-0313", "clause-0314"], ["clause-0081", "clause-0084"]],
        "data_protection_and_tokenization": [["clause-0085", "clause-0096"], ["clause-0085"]],
        "cross_border_outward": [["clause-0313", "clause-0317"], ["clause-0311", "clause-0335"]],
        "product_specific_terms": [["clause-0352", "clause-0353"], ["clause-0265", "clause-0301"]],
    },
}


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
    subsection = hierarchy.get("subsection")
    if subsection:
        return str(subsection)
    section_title = hierarchy.get("section_title")
    return str(section_title or "Clause")


def section_name(clause: dict[str, Any]) -> str | None:
    hierarchy = clause.get("hierarchy", {})
    return hierarchy.get("subsection") or hierarchy.get("section_title") or hierarchy.get("clause_title")


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
    preferred_clause_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    effective_date = metadata.get("effective_date") or metadata["effective_date_iso"]
    candidate_ids = preferred_clause_ids or [
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
                "source_clause_text": " ".join(
                    (clause.get("text_without_marker") or clause.get("text") or "").split()
                ),
            }
        )
    return citations


def citation_names(citations: list[dict[str, Any]]) -> str:
    return "; ".join(citation["clause_path"] for citation in citations)


def pick(values: list[str], index: int) -> str:
    return values[index % len(values)]


def preferred_citation_ids(category: str, topic_id: str, occurrence_index: int) -> list[str] | None:
    topic_preferences = PREFERRED_CITATIONS.get(category, {}).get(topic_id)
    if not topic_preferences:
        return None
    return pick(topic_preferences, occurrence_index)


def clarifying_question(trigger: str, topic: dict[str, Any]) -> str:
    if trigger.lower().startswith("whether"):
        stem = trigger[8:]
        return f"Can you confirm whether {stem}?"
    if trigger.lower().startswith("which"):
        stem = trigger[6:]
        return f"Which {stem} in this scenario?"
    return f"Can you confirm the {trigger[0].lower() + trigger[1:]}?"


def missing_fact_name(trigger: str) -> str:
    return trigger[0].lower() + trigger[1:]


def clear_question(use: str, topic: dict[str, Any], index: int) -> str:
    questions = QUESTION_BANK["clear_answer"].get(topic["topic_id"])
    if questions:
        return pick(questions, index)

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
    questions = QUESTION_BANK["clarification_required"].get(topic["topic_id"])
    if questions:
        return pick(questions, index)

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
    questions = QUESTION_BANK["genuine_ambiguity"].get(topic["topic_id"])
    if questions:
        return pick(questions, index)

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
    scoring_dimensions = {dimension: None for dimension in SCORING_DIMENSIONS}
    if category != "clarification_required":
        scoring_dimensions["clarification_quality"] = "not_applicable"
    if category != "genuine_ambiguity":
        scoring_dimensions["ambiguity_handling"] = "not_applicable"

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
        "scoring_dimensions": scoring_dimensions,
        "overall_score": None,
        "passed": None,
        "critical_failures": [],
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
    topics_by_id = {topic["topic_id"]: topic for topic in topics}

    rows: list[dict[str, Any]] = []
    for category in CATEGORIES:
        sequence = CATEGORY_TOPIC_SEQUENCE[category]
        supported = [topics_by_id[topic_id] for topic_id in sequence]
        if len(supported) < 1:
            raise ValueError(f"no inventory topics support {category}")

        occurrences: defaultdict[str, int] = defaultdict(int)
        for index in range(per_category):
            topic = supported[index % len(supported)]
            if category not in topic["supports_answerability"]:
                raise ValueError(f"{topic['topic_id']} does not support {category}")
            occurrence_index = occurrences[topic["topic_id"]]
            occurrences[topic["topic_id"]] += 1
            preferred_ids = preferred_citation_ids(category, topic["topic_id"], occurrence_index)
            citations = build_citations(topic, clauses_by_id, metadata, preferred_clause_ids=preferred_ids)
            row = make_base_row(category, index, topic, citations, seed)

            if category == "clear_answer":
                use = pick(topic["clear_answer_uses"], occurrence_index)
                row["user_question"] = clear_question(use, topic, occurrence_index)
                row["assistant_response"] = clear_response(use, topic, citations)

            elif category == "clarification_required":
                trigger = pick(topic["clarification_triggers"], occurrence_index)
                response, question, why = clarification_response(trigger, topic, citations)
                row["user_question"] = clarification_question(trigger, topic, occurrence_index)
                row["assistant_response"] = response
                row["clarifying_question"] = question
                row["why_clarification_matters"] = why
                row["missing_facts"] = [missing_fact_name(trigger)]

            else:
                trigger = pick(topic["ambiguity_triggers"], occurrence_index)
                response, reason, next_step = ambiguity_response(trigger, topic, citations)
                row["user_question"] = ambiguity_question(trigger, topic, occurrence_index)
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
            handle.write(json.dumps(row, ensure_ascii=False))
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
    errors = validate_rows(rows)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    write_jsonl(rows, args.output)
    print(f"wrote {len(rows)} examples to {args.output}")
    for category in CATEGORIES:
        print(f"{category}: {sum(1 for row in rows if row['category'] == category)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
