# Razorpay ToS Compliance Assistant Dataset Plan

## Assignment Context

The assignment is to build the foundation of a synthetic training dataset for a Q&A compliance assistant. The assistant is meant to help a fast-growing Indian fintech startup answer internal questions about its Razorpay agreement quickly and accurately.

The source document is the publicly available Razorpay Payments Terms and Conditions:

- Source URL: https://razorpay.com/terms/
- Current observed effective date: January 01, 2026
- Primary document scope: Razorpay payment services, including payment aggregation and related product-specific terms

The deliverables are:

- A script that generates at least 45 Q&A examples from the Razorpay ToS
- At least 15 examples in each required category
- A structured JSONL dataset
- A README with setup/run instructions, determinism notes, and seed information
- An eval summary

The core grading signal is not just whether the examples are plausible. The dataset and pipeline should show that the assistant can distinguish between:

1. Questions that the ToS clearly answers
2. Questions where the answer depends on a missing fact
3. Questions where the ToS is genuinely incomplete, vague, or dependent on external regulation

## Required Answer Categories

### A. Clear Answer

The ToS explicitly and unambiguously answers the question.

A good response should:

- Give a direct answer
- Cite the relevant clause or clause path
- Avoid asking unnecessary follow-up questions

Example behavior:

If the question asks whether Razorpay fees remain payable after a refund, the assistant should answer directly because the current terms state that Razorpay PA fees are payable on each transaction even if the merchant refunds the customer.

### B. Clarification Required

The ToS contains a rule, but the user has not provided a fact that determines how the rule applies.

A good response should:

- Ask one specific, targeted clarifying question
- Explain why that fact changes the answer
- Avoid vague follow-ups like "can you provide more details?"

Example behavior:

If the question asks whether Razorpay can hold settlement money after an unauthorized transaction, the answer may depend on whether the Facility Provider has intimated Razorpay about the unauthorized debit and what stage the dispute or investigation has reached.

### C. Genuine Ambiguity

The ToS is silent, vague, discretionary, or cross-references external rules in a way that prevents a reliable answer from the ToS alone.

A good response should:

- Clearly state that the ToS does not fully resolve the issue
- Explain what the ToS does say
- Explain what remains unknown
- Recommend a next step, such as checking external regulation, legal review, or asking Razorpay for clarification

Example behavior:

If the question asks how long Razorpay can hold funds after suspending an account under Clause 16.1, the ToS gives Razorpay suspension rights but does not specify a maximum hold duration. The assistant should not invent a timeline.

## Agreed Dataset Schema

Each JSONL row will use the following schema.

```json
{
  "id": "stable unique identifier",
  "category": "clear_answer | clarification_required | genuine_ambiguity",
  "user_question": "natural Slack-style question",
  "assistant_response": "complete ideal answer",
  "needs_clarification": false,
  "clarifying_question": null,
  "why_clarification_matters": null,
  "ambiguity_reason": null,
  "recommended_next_step": null,
  "citations": [
    {
      "source_url": "https://razorpay.com/terms/",
      "effective_date": "2026-01-01",
      "part": "Part A or Part B",
      "section": "section name",
      "clause_path": "hierarchical path to the cited rule",
      "clause_label": "human-readable clause label",
      "evidence_summary": "short summary of what the cited clause says"
    }
  ],
  "legal_issue_tags": ["refunds", "fees"],
  "product_tags": ["payment_aggregation"],
  "merchant_context_assumed": {},
  "missing_facts": [],
  "confidence": "high | medium | low",
  "scoring_dimensions": {
    "category_correctness": null,
    "citation_support": null,
    "response_quality": null,
    "clarification_quality": "not_applicable",
    "ambiguity_handling": "not_applicable",
    "schema_consistency": null
  },
  "overall_score": null,
  "passed": null,
  "critical_failures": [],
  "generation_metadata": {
    "source_doc_version": "razorpay_terms_2026_01_01",
    "script_seed": 42,
    "deterministic": true,
    "template_id": "refund_fee_clear_001",
    "model_id": null
  }
}
```

### Field Notes

- `id`: Stable unique identifier for each example.
- `category`: The assignment-required label. Must be one of `clear_answer`, `clarification_required`, or `genuine_ambiguity`.
- `user_question`: A realistic internal question, phrased like something an engineering, product, finance, or ops teammate might ask in Slack.
- `assistant_response`: The complete ideal response the assistant should learn to produce.
- `needs_clarification`: Boolean flag. Should be `true` for category B and usually `false` for categories A and C.
- `clarifying_question`: Required for category B. Should be specific and targeted.
- `why_clarification_matters`: Required for category B. Explains how the missing fact changes the answer.
- `ambiguity_reason`: Required for category C. Examples include `tos_silent`, `undefined_term`, `external_regulation`, `razorpay_discretion`, and `jurisdiction_dependent`.
- `recommended_next_step`: Especially important for category C. Examples include asking Razorpay support, legal review, checking RBI/NPCI rules, or confirming whether an offline agreement applies.
- `citations`: Array because some answers depend on more than one clause.
- `legal_issue_tags`: Compliance or legal issue labels, such as refunds, chargebacks, settlements, fraud, prohibited goods, gaming, marketplace/sub-merchants, data protection, KYC, tax, cross-border, and termination.
- `product_tags`: Razorpay product or service labels, such as payment aggregation, POS, subscriptions, TokenHQ, Magic Checkout, cross-border outward, and e-mandate.
- `merchant_context_assumed`: Facts baked into the example. This makes the training example auditable.
- `missing_facts`: Facts needed before the assistant can answer confidently. This is especially important for category B.
- `confidence`: High, medium, or low, based on how strongly the ToS supports the response.
- `scoring_dimensions`: Evaluation placeholders for the 6-dimension judge rubric. Applicable dimensions are `null` until scored; category-specific dimensions that do not apply are marked `not_applicable`.
- `overall_score`: Average of applicable integer dimension scores, rounded to 2 decimal places. It remains `null` until all applicable dimensions are scored.
- `passed`: `true` only when `overall_score >= 4.0` and `critical_failures` is empty. It remains `null` until all applicable dimensions are scored.
- `critical_failures`: Evaluation failure IDs that override the average score.
- `generation_metadata`: Pipeline traceability, including source version, seed, determinism, template ID, and model ID if an LLM is used.

## Important Source-Document Considerations

The Razorpay terms page may change over time. The pipeline should capture the effective date and, ideally, store a local normalized copy or source snapshot metadata so examples can be traced back to the version used.

The assignment seed questions appear to reference clause labels from an older or differently structured version of the Razorpay terms. For example, the current page includes refund fee language under a payment aggregation refund section rather than exactly under the seed's stated Part A clause numbering. Because clause numbers can shift, the dataset should preserve:

- `part`
- `section`
- `clause_path`
- `clause_label`
- `evidence_summary`

This avoids relying only on brittle clause numbers.

## Plan of Action

### 1. Ingest and Normalize the ToS

Scrape the Razorpay terms page and extract the terms content.

The normalized source should preserve:

- Source URL
- Effective date
- Part hierarchy
- Section headings
- Clause numbers
- Subclauses and numbered items
- Raw clause text

The output of this step should be a machine-readable source inventory, likely JSON.

### 2. Build a Clause Inventory

Create a structured map of clauses that are useful for compliance-style Q&A.

Initial topic areas:

- Fees
- Refunds
- Chargebacks
- Fraudulent transactions
- Settlement holds
- Suspensions and termination
- Prohibited products and services
- Gaming
- Marketplace or sub-merchant use cases
- KYC and onboarding
- Tax and invoicing
- Data protection and tokenization
- Cross-border transactions
- Product-specific terms

Each inventory item should include:

- Clause path
- Short legal/commercial meaning
- Relevant tags
- Whether it supports clear answers, clarification examples, ambiguity examples, or multiple categories

### 3. Define Answerability Rules

The generator should classify examples using explicit rules.

Clear answer:

- The clause directly answers the user's question
- No missing factual condition is needed
- Response can cite one or more clauses and answer confidently

Clarification required:

- The ToS provides a conditional rule
- The user question omits a condition that changes the outcome
- The assistant should ask a targeted question before answering

Genuine ambiguity:

- The ToS is silent on the precise issue
- The ToS uses broad discretion without a concrete operational limit
- The ToS refers to external law, RBI/NPCI rules, or other documents not included in the dataset
- The ToS uses an undefined or jurisdiction-dependent term

### 4. Generate Examples

Start with deterministic templates for reliability.

Recommended first version:

- 15 clear answer examples
- 15 clarification required examples
- 15 genuine ambiguity examples

Use templates to produce:

- User question variants
- Ideal assistant response
- Citation objects
- Tags
- Merchant context
- Missing facts or ambiguity reasons

Optional later improvement:

- Use an LLM to paraphrase questions and responses
- Keep citations, tags, and labels deterministic
- Record model ID and seed in `generation_metadata`

### 5. Validate the Dataset

Add validation checks before writing the final JSONL.

Minimum validation rules:

- Output is valid JSONL
- At least 45 total examples
- At least 15 examples per category
- Every row has all required top-level fields
- Every row has at least one citation
- `category` is one of the three allowed values
- Category B rows have `needs_clarification: true`
- Category B rows have `clarifying_question`, `why_clarification_matters`, and non-empty `missing_facts`
- Category C rows have `ambiguity_reason` and `recommended_next_step`
- Category A rows do not ask unnecessary clarifying questions
- `confidence` is one of `high`, `medium`, or `low`

### 6. Run Quality Evaluation

Design and run an LLM-as-judge evaluation on the generated dataset.

The goal is to evaluate whether the dataset teaches the desired compliance-assistant behavior, not only whether the JSONL is structurally valid.

Input:

- `data/synthetic_qa.jsonl`

Outputs:

- `eval/judge_results.jsonl`
- `eval/eval_summary.md`

#### Scoring Dimensions

Score each example from 1 to 5 on the applicable dimensions:

- 1 = poor
- 3 = acceptable but flawed
- 5 = excellent

- `category_correctness`: Does the example belong in the labeled category? Clear-answer examples must be answerable from the ToS; clarification-required examples must depend on a missing fact; genuine-ambiguity examples must be unresolved by the ToS alone.
- `citation_support`: Do the cited clauses actually support the response? This catches hallucinated citations, weak citations, and cases where the response goes beyond the cited clause.
- `response_quality`: Is the assistant response useful, concise, compliant, and commercially practical? It should sound like a good compliance assistant, not a vague legal disclaimer machine.
- `clarification_quality`: Only for category B. Does the example ask a targeted clarifying question, and does `why_clarification_matters` explain the decision point? For non-B rows, mark `not_applicable`.
- `ambiguity_handling`: Only for category C. Does the response honestly flag uncertainty, explain what is known, and recommend a sensible next step? For non-C rows, mark `not_applicable`.
- `schema_consistency`: Are the structured fields internally consistent? Examples: `needs_clarification` is true only for category B; category C has `ambiguity_reason`; clear-answer rows have no unnecessary clarifying question; missing facts align with the response.

Use `null` for applicable dimensions that have not yet been scored, an integer from 1 to 5 after scoring, and `not_applicable` only for dimensions that do not apply to a row's category.

#### Pass/Fail Logic

For each row:

- Calculate `overall_score` as the average of applicable dimension scores.
- Mark `passed: true` only if `overall_score >= 4.0` and there are no critical failures.

Critical failures should override the average score.

Examples of critical failures:

- `wrong_category`
- `citation_does_not_support_answer`
- `assistant_gives_definitive_answer_for_genuine_ambiguity`
- `clarification_required_but_no_specific_question`
- `clear_answer_but_response_refuses_or_over_hedges`

This matters because a row with decent writing but the wrong category is bad training data.

Dataset-level quality targets:

- Pass rate of at least 85%
- Average overall score of at least 4.2 out of 5
- No category below 80% pass rate

#### Judge Prompt Requirements

The judge prompt should include:

- Assignment category definitions
- The scoring rubric
- The full dataset row
- The cited evidence summaries and, where available, source clause text

The judge should return strict JSON for each example:

```json
{
  "id": "rzp_clear_001",
  "scores": {
    "category_correctness": 5,
    "citation_support": 5,
    "response_quality": 4,
    "clarification_quality": null,
    "ambiguity_handling": null,
    "schema_consistency": 5
  },
  "overall_score": 4.75,
  "passed": true,
  "critical_failures": [],
  "notes": "The response directly answers the question and the cited clause supports it."
}
```

#### Evaluation Script

Create `scripts/evaluate_dataset.py`.

The script should:

- Read `data/synthetic_qa.jsonl`
- Run deterministic preflight checks before making LLM calls
- Build judge prompts using a versioned rubric
- Call the LLM judge with temperature 0
- Parse strict JSON responses
- Record model ID, prompt version, input file, timestamp, and run configuration
- Write detailed per-example results to `eval/judge_results.jsonl`
- Write aggregate findings to `eval/eval_summary.md`

Deterministic preflight checks should include:

- JSONL parses successfully
- All required fields exist
- Category counts are at least 15 each
- Every row has at least one citation
- Category B has `clarifying_question`, `why_clarification_matters`, and non-empty `missing_facts`
- Category C has `ambiguity_reason` and `recommended_next_step`
- `source_url` in citations is `https://razorpay.com/terms/`

#### Eval Summary

The summary should include:

- Total examples
- Examples by category
- Overall pass rate
- Average overall score
- Average score by dimension
- Average score by category
- Critical failure counts
- Most common quality issues

It must also include the 3 worst examples, selected by failed status, lowest overall score, and number of critical failures.

For each of the 3 worst examples, include approximately 50 words describing:

- What is wrong
- Where in the pipeline it came from
- What caused the failure
- What rubric or code change would catch it

Example format:

```text
1. rzp_clarify_007
This example asks about settlement holds but gives a broad answer instead of asking whether the Facility Provider has notified Razorpay. The failure came from the clarification template. The template lacked a required missing-fact check. Add a validator that category B responses must contain a targeted question tied to missing_facts.
```

#### Determinism Notes

The LLM-as-judge step is not perfectly deterministic, even with temperature 0, because model/provider behavior can change.

To reduce variance:

- Use temperature 0
- Use a fixed model name
- Use a fixed prompt version
- Use a stable dataset input
- Record evaluation timestamp and model ID
- Keep deterministic validation separate from LLM judgment

### 7. Write README

The README should explain:

- What the project does
- How to set up the environment
- How to run the generator
- Where outputs are written
- Which outputs are deterministic
- Which outputs are not deterministic, if an LLM paraphrasing step is used
- Which seeds are used where
- Known limitations

Important limitations to call out:

- Razorpay may update the live ToS
- Current examples are based only on the Razorpay terms page unless external regulation is separately added
- Some seed-question clause references may differ from the current live document structure
- This is a training dataset, not legal advice

## Proposed Output Files

Likely project structure:

```text
.
├── PLAN.md
├── README.md
├── data/
│   ├── clause_inventory.json
│   ├── razorpay_terms_normalized.json
│   └── synthetic_qa.jsonl
├── scripts/
│   ├── ingest_terms.py
│   ├── generate_dataset.py
│   ├── validate_dataset.py
│   └── evaluate_dataset.py
└── eval/
    ├── judge_results.jsonl
    └── eval_summary.md
```

## Success Criteria

This plan is successful if the final dataset shows that the assistant can:

- Answer direct ToS questions with citations
- Ask precise clarifying questions when a missing fact changes the answer
- Recognize true ambiguity instead of over-answering
- Preserve traceability from each answer back to the source document
- Produce a repeatable JSONL artifact that can be inspected, regenerated, and evaluated
- Include an LLM-as-judge evaluation with clear rubric scores, pass/fail logic, and analysis of the 3 worst examples
