# Evaluation Summary

Input: `eval/judge_results.jsonl`  
Judge: `openai/gpt-oss-120b:free` through OpenRouter  
Rows evaluated: 45

## Scoring Dimensions

- `category_correctness`: Does the example belong in the labeled category?
- `citation_support`: Do the cited clauses actually support the assistant response?
- `response_quality`: Is the response useful, concise, compliant, and commercially practical?
- `clarification_quality`: For `clarification_required` rows only, does the row ask a targeted clarifying question and explain the decision point?
- `ambiguity_handling`: For `genuine_ambiguity` rows only, does the response flag uncertainty, explain what is known, and recommend a sensible next step?
- `schema_consistency`: Are structured fields internally consistent with the category, response, missing facts, and ambiguity fields?

Scores use a 1-5 scale: 1 is poor, 3 is acceptable but flawed, and 5 is excellent. `overall_score` is the average of applicable numeric scores. A row passes only when `overall_score >= 4.0` and there are no critical failures.

## Judge Run Quality

The judge returned structurally valid output for only 19 of 45 rows.

| Status | Count |
| --- | ---: |
| valid | 19 |
| invalid | 26 |

Invalid judge-output reasons:

| Reason | Count |
| --- | ---: |
| OpenRouter API response did not contain message content | 12 |
| `notes` was missing or empty | 10 |
| malformed JSON | 4 |

These invalid rows are not reliable dataset-quality judgments. They mainly show that the selected free OpenRouter model is weak at strict JSON compliance under this prompt.

## Dataset Quality From Valid Judgments

Among the 19 valid judge outputs, 13 passed and 6 failed.

| Metric | Value |
| --- | ---: |
| Valid-judgment pass rate | 68.4% |
| Average overall score | 4.45 |
| Valid clear-answer pass/fail | 3 / 3 |
| Valid clarification-required pass/fail | 2 / 2 |
| Valid genuine-ambiguity pass/fail | 8 / 1 |

Average scores by dimension:

| Dimension | Average |
| --- | ---: |
| `category_correctness` | 4.89 |
| `citation_support` | 3.84 |
| `response_quality` | 3.84 |
| `clarification_quality` | 5.00 |
| `ambiguity_handling` | 4.89 |
| `schema_consistency` | 5.00 |

The dataset is structurally strong and usually categorized correctly, but citation support is the main quality risk. Every valid failed row had the same critical failure: `citation_does_not_support_answer`.

## Three Worst Examples

### 1. `rq-clear-answer-011`

The question asks who must keep GSTIN and tax details accurate, but the cited clause is about e-commerce operator TDS withholding. The generator selected a broad tax topic summary and mismatched the citation. A rubric/code check should require answer keywords to overlap with cited source text before emitting clear-answer rows.

### 2. `rq-clear-answer-007`

The response begins “Yes” to accepting NFT or crypto payments, then cites a clause prohibiting crypto products. This came from the generic clear-answer template, which assumes affirmative phrasing even for prohibition questions. A code rule should invert answers for prohibited-category templates and flag “Yes” plus prohibitory citation conflicts.

### 3. `rq-genuine-ambiguity-014`

The Magic Checkout ambiguity response cites e-mandate onboarding clauses, so the ambiguity framing is plausible but unsupported. This came from product-specific citation preferences pointing at the wrong product family. A rubric/code check should require product tag alignment between question, response, and cited clause path before generation passes.

## Bottom Line

Using only valid judge outputs, the dataset is promising but not yet production-quality. The strongest areas are schema consistency, category labeling, and ambiguity handling. The weakest area is citation grounding. The next improvement should be citation-selection repair, especially for prohibited goods, tax/GST, marketplace, and product-specific examples.
