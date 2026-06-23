# Razorpay ToS Compliance Assistant Dataset

This project builds a small synthetic Q&A dataset for a compliance assistant that answers internal questions about the Razorpay Payments Terms and Conditions.

The dataset is designed to teach three answerability modes:

- `clear_answer`: the Razorpay ToS directly answers the question.
- `clarification_required`: the ToS has a conditional rule, but the user omitted a fact that changes the answer.
- `genuine_ambiguity`: the ToS is silent, discretionary, or depends on external law or rules.

The current generated dataset contains 45 examples: 15 per category.

## Project Layout

```text
.
|-- PLAN.md
|-- README.md
|-- data/
|   |-- answerability_rules.json
|   |-- razorpay_clause_inventory.json
|   |-- razorpay_terms_normalized.json
|   `-- synthetic_qa.jsonl
`-- scripts/
    |-- generate_dataset.py
    |-- ingest_terms.py
    |-- evaluate_dataset.py
    |-- validate_answerability_rules.py
    |-- validate_clause_inventory.py
    `-- validate_dataset.py
```

## Setup

Use Python 3. No third-party Python packages are required; the scripts only use the standard library.

From the repository root:

```bash
python3 --version
```

The scripts assume they are run from the repository root so the default `data/...` paths resolve correctly.

## Run The Pipeline

To regenerate the synthetic dataset from the checked-in normalized terms and clause inventory:

```bash
python3 -B scripts/generate_dataset.py
```

This writes:

```text
data/synthetic_qa.jsonl
```

Expected output:

```text
wrote 45 examples to data/synthetic_qa.jsonl
clear_answer: 15
clarification_required: 15
genuine_ambiguity: 15
```

To use a different output path:

```bash
python3 -B scripts/generate_dataset.py --output data/my_synthetic_qa.jsonl
```

To change the number of examples per category:

```bash
python3 -B scripts/generate_dataset.py --per-category 20
```

The current topic sequences are built for the assignment requirement of 15 examples per category. Higher values cycle through the configured topic sequence.

## Optional Source Ingestion

The repository already includes a normalized Razorpay terms artifact:

```text
data/razorpay_terms_normalized.json
```

To refresh it from the live Razorpay terms page:

```bash
python3 -B scripts/ingest_terms.py
```

This fetches:

```text
https://razorpay.com/terms/
```

and writes:

```text
data/razorpay_terms_normalized.json
```

The current checked-in normalized source was fetched at `2026-06-21T06:55:21+00:00`, observed `Effective January 01, 2026`, and contains 489 normalized blocks and 443 clauses.

For offline parsing from a saved HTML file:

```bash
python3 -B scripts/ingest_terms.py --input-html path/to/razorpay_terms.html
```

## Validation

Validate the final JSONL dataset:

```bash
python3 -B scripts/validate_dataset.py
```

Validate the clause inventory against the normalized source:

```bash
python3 -B scripts/validate_clause_inventory.py
```

Validate the answerability rules:

```bash
python3 -B scripts/validate_answerability_rules.py
```

Build judge prompts without calling a model:

```bash
python3 -B scripts/evaluate_dataset.py
```

Write prompt records to `eval/judge_prompts.jsonl`:

```bash
python3 -B scripts/evaluate_dataset.py --write-prompts
```

Inspect a single prompt:

```bash
python3 -B scripts/evaluate_dataset.py --print-prompt-id rq-clear-answer-001
```

Run the LLM judge and write detailed per-row results to `eval/judge_results.jsonl`:

```bash
python3 -B scripts/evaluate_dataset.py --run-judge --model gpt-4.1-mini
```

Run the judge through OpenRouter with `openai/gpt-oss-120b:free`:

```bash
python3 -B scripts/evaluate_dataset.py --run-judge --provider openrouter
```

The evaluator loads API keys from environment variables or a local `.env` file. For OpenRouter, use:

```text
OPENROUTER_API_KEY=...
```

The `.env` file is ignored by Git and must not be committed.

The evaluator retries malformed judge output once by default. Change that with `--max-retries`, or use `--mock-judge` for local plumbing checks without calling a model:

```bash
python3 -B scripts/evaluate_dataset.py --run-judge --mock-judge --limit 3 --output-results /tmp/judge_results.jsonl
```

Current validation results:

```text
validated 45 examples
clarification_required: 15
clear_answer: 15
genuine_ambiguity: 15

validated 14 inventory topics

validated 3 answerability categories
```

## Output Files

`data/razorpay_terms_normalized.json`

Normalized source artifact produced by `scripts/ingest_terms.py`. It includes source metadata, effective date, parser version, SHA-256 of the fetched HTML, normalized text blocks, clause records, and hierarchy paths.

`data/razorpay_clause_inventory.json`

Hand-curated inventory of compliance-relevant topics. Each topic maps to normalized clause IDs, legal/commercial meaning, tags, and the answerability categories it can support.

`data/answerability_rules.json`

Rules defining the three answerability categories and the dataset fields each category must include or leave empty.

`data/synthetic_qa.jsonl`

Generated Q&A dataset. Each line is one JSON object with the question, ideal assistant response, category label, citation objects, tags, missing facts or ambiguity details, scoring-dimension placeholders, pass/fail fields, and generation metadata. Each citation includes both `evidence_summary` and `source_clause_text` so a judge can evaluate citation support against clause text rather than plausibility alone.

`eval/judge_prompts.jsonl`

Optional prompt artifact produced by `scripts/evaluate_dataset.py --write-prompts`. Each line contains a row id, prompt version, and the full prompt payload for one judge evaluation.

`eval/judge_results.jsonl`

Detailed judge output produced by `scripts/evaluate_dataset.py --run-judge`. Each line contains the row id, valid/invalid status, prompt version, model id, attempt count, parsed judge response when valid, and errors plus attempt history when invalid.

## Scoring Dimensions

Each row includes a `scoring_dimensions` object for evaluation:

- `category_correctness`
- `citation_support`
- `response_quality`
- `clarification_quality`
- `ambiguity_handling`
- `schema_consistency`

Scores use a 1-5 scale where 1 is poor, 3 is acceptable but flawed, and 5 is excellent. Applicable dimensions are `null` until scored. `clarification_quality` is `not_applicable` for non-`clarification_required` rows, and `ambiguity_handling` is `not_applicable` for non-`genuine_ambiguity` rows.

When scored, each row derives:

- `overall_score`: the average of applicable integer dimension scores, rounded to 2 decimal places.
- `passed`: `true` only when `overall_score >= 4.0` and `critical_failures` is empty.
- `critical_failures`: failure IDs that override the average score, including `wrong_category`, `citation_does_not_support_answer`, `assistant_gives_definitive_answer_for_genuine_ambiguity`, `clarification_required_but_no_specific_question`, and `clear_answer_but_response_refuses_or_over_hedges`.

## Seeds And Determinism

The dataset generator default seed is:

```text
42
```

It is exposed as:

```bash
python3 -B scripts/generate_dataset.py --seed 42
```

Every generated row records the seed in:

```text
generation_metadata.script_seed
```

The current generator is deterministic because it uses fixed templates, fixed category/topic sequences, fixed citation preferences, and the local `data/razorpay_terms_normalized.json` plus `data/razorpay_clause_inventory.json` inputs. It does not call an LLM. `generation_metadata.model_id` is therefore `null`, and `generation_metadata.deterministic` is `true`.

With the current checked-in inputs and default arguments, `data/synthetic_qa.jsonl` has SHA-256:

```text
a30673fe6dd7cc9e2adb90482d1dc44c7c9fe054a77c954ec81cf9f4a7572dc2
```

Changing `--seed` currently changes the recorded metadata seed, but it does not randomize row content because the generator's selection logic is template and sequence based. The seed is reserved for future randomization or paraphrasing steps.

The live ingestion step is not fully deterministic. If `scripts/ingest_terms.py` fetches the Razorpay page again, the output can change because of live ToS edits, page markup changes, responsive page chrome, HTTP behavior, parser changes, or a new fetch timestamp. To make source parsing reproducible, use `--input-html` with a saved HTML snapshot.

If a future LLM paraphrasing step is added, the generated prose may become non-deterministic unless the model, model settings, prompt version, and seed behavior are pinned and recorded.

## Known Limitations

Razorpay may update the live terms page at any time. The current examples trace to the normalized source artifact in this repository, not necessarily to the latest live page after that artifact was produced.

The examples are based only on the Razorpay terms page and the local clause inventory. They do not incorporate external RBI, NPCI, FEMA, tax, privacy, card-network, or bank rules unless those are explicitly referenced as unresolved next steps.

Some original seed-question clause references may not match the current live document structure. The dataset therefore cites durable hierarchy paths and clause summaries rather than relying only on brittle clause numbers.

The clause inventory is curated for coverage and traceability, not for exhaustive legal interpretation of every Razorpay product or edge case.

This is a synthetic training dataset, not legal advice.
