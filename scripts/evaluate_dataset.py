#!/usr/bin/env python3
"""Run LLM-as-judge evaluation for Razorpay synthetic Q&A examples."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_dataset import CRITICAL_FAILURES, SCORING_DIMENSIONS, load_jsonl, validate_rows


DEFAULT_DATASET_PATH = Path("data/synthetic_qa.jsonl")
DEFAULT_PROMPTS_PATH = Path("eval/judge_prompts.jsonl")
DEFAULT_RESULTS_PATH = Path("eval/judge_results.jsonl")
DEFAULT_ENV_PATH = Path(".env")
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
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


def load_env_file(path: Path = DEFAULT_ENV_PATH) -> None:
    if not path.exists():
        return

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


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


def extract_response_text(response_payload: dict[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts: list[str] = []
    output = response_payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts).strip()


def extract_chat_completion_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def call_openai_judge(prompt: str, model: str, timeout: int) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required unless --mock-judge is used")

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a strict dataset quality judge. Return only valid JSON matching the "
                    "requested schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_output_tokens": 700,
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc

    text = extract_response_text(response_payload)
    if not text:
        raise RuntimeError("OpenAI API response did not contain output text")
    return text


def call_openrouter_judge(prompt: str, model: str, timeout: int) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required unless --mock-judge is used")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict dataset quality judge. Return only valid JSON matching the "
                    "requested schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        OPENROUTER_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "Razorpay ToS dataset evaluator",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenRouter API request failed: {exc.reason}") from exc

    text = extract_chat_completion_text(response_payload)
    if not text:
        raise RuntimeError("OpenRouter API response did not contain message content")
    return text


def call_judge(prompt: str, provider: str, model: str, timeout: int) -> str:
    if provider == "openai":
        return call_openai_judge(prompt, model, timeout)
    if provider == "openrouter":
        return call_openrouter_judge(prompt, model, timeout)
    raise ValueError(f"unsupported provider: {provider}")


def mock_judge_response(row: dict[str, Any]) -> str:
    scores = {
        "category_correctness": 5,
        "citation_support": 5,
        "response_quality": 4,
        "clarification_quality": None,
        "ambiguity_handling": None,
        "schema_consistency": 5,
    }
    applicable_scores = [5, 5, 4, 5]
    if row["category"] == "clarification_required":
        scores["clarification_quality"] = 5
        applicable_scores.append(5)
    if row["category"] == "genuine_ambiguity":
        scores["ambiguity_handling"] = 5
        applicable_scores.append(5)
    overall_score = round(sum(applicable_scores) / len(applicable_scores), 2)
    return json.dumps(
        {
            "id": row["id"],
            "scores": scores,
            "overall_score": overall_score,
            "passed": overall_score >= 4.0,
            "critical_failures": [],
            "notes": "Mock judge response for local evaluator verification.",
        }
    )


def parse_strict_json(raw_text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, f"malformed JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, "judge output must be a JSON object"
    return parsed, None


def validate_judge_output(result: dict[str, Any], row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_fields = {"id", "scores", "overall_score", "passed", "critical_failures", "notes"}
    missing = sorted(expected_fields - set(result))
    extra = sorted(set(result) - expected_fields)
    for field in missing:
        errors.append(f"missing required field: {field}")
    for field in extra:
        errors.append(f"unknown field: {field}")

    if result.get("id") != row["id"]:
        errors.append(f"id must be {row['id']}")

    scores = result.get("scores")
    if not isinstance(scores, dict):
        errors.append("scores must be an object")
        return errors

    missing_scores = sorted(SCORING_DIMENSIONS - set(scores))
    extra_scores = sorted(set(scores) - SCORING_DIMENSIONS)
    for dimension in missing_scores:
        errors.append(f"scores missing dimension: {dimension}")
    for dimension in extra_scores:
        errors.append(f"scores has unknown dimension: {dimension}")

    numeric_scores: list[int] = []
    for dimension in SCORING_DIMENSIONS & set(scores):
        value = scores[dimension]
        should_be_null = (
            (dimension == "clarification_quality" and row["category"] != "clarification_required")
            or (dimension == "ambiguity_handling" and row["category"] != "genuine_ambiguity")
        )
        if should_be_null:
            if value is not None:
                errors.append(f"scores.{dimension} must be null for {row['category']}")
            continue
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
            errors.append(f"scores.{dimension} must be an integer from 1 to 5")
        else:
            numeric_scores.append(value)

    if numeric_scores:
        expected_overall = round(sum(numeric_scores) / len(numeric_scores), 2)
        actual_overall = result.get("overall_score")
        if not isinstance(actual_overall, (int, float)) or isinstance(actual_overall, bool):
            errors.append("overall_score must be numeric")
        elif round(float(actual_overall), 2) != expected_overall:
            errors.append(f"overall_score must equal {expected_overall}")
    else:
        expected_overall = None
        errors.append("at least one applicable score is required")

    failures = result.get("critical_failures")
    if not isinstance(failures, list):
        errors.append("critical_failures must be an array")
        failures = []
    else:
        for index, failure in enumerate(failures):
            if failure not in CRITICAL_FAILURES:
                errors.append(
                    f"critical_failures[{index}] must be one of {sorted(CRITICAL_FAILURES)}"
                )

    if expected_overall is not None:
        expected_passed = expected_overall >= 4.0 and not failures
        if result.get("passed") is not expected_passed:
            errors.append(f"passed must be {expected_passed}")

    if not isinstance(result.get("notes"), str) or not result.get("notes", "").strip():
        errors.append("notes must be a non-empty string")

    return errors


def evaluate_row(
    row: dict[str, Any],
    provider: str,
    model: str,
    max_retries: int,
    timeout: int,
    mock_judge: bool,
) -> dict[str, Any]:
    prompt = build_prompt(row)
    attempts: list[dict[str, Any]] = []

    for attempt in range(1, max_retries + 2):
        started = time.time()
        try:
            raw_response = mock_judge_response(row) if mock_judge else call_judge(prompt, provider, model, timeout)
            parsed, parse_error = parse_strict_json(raw_response)
            validation_errors = validate_judge_output(parsed, row) if parsed is not None else [parse_error]
            elapsed_ms = round((time.time() - started) * 1000)
            attempts.append(
                {
                    "attempt": attempt,
                    "elapsed_ms": elapsed_ms,
                    "raw_response": raw_response,
                    "errors": [error for error in validation_errors if error],
                }
            )
            if parsed is not None and not validation_errors:
                return {
                    "id": row["id"],
                    "status": "valid",
                    "prompt_version": PROMPT_VERSION,
                    "provider": "mock" if mock_judge else provider,
                    "model_id": "mock-judge" if mock_judge else model,
                    "attempts": attempt,
                    "judge_response": parsed,
                    "errors": [],
                }
        except Exception as exc:  # noqa: BLE001 - record per-row failures without aborting the run.
            elapsed_ms = round((time.time() - started) * 1000)
            attempts.append(
                {
                    "attempt": attempt,
                    "elapsed_ms": elapsed_ms,
                    "raw_response": None,
                    "errors": [str(exc)],
                }
            )

    return {
        "id": row["id"],
        "status": "invalid",
        "prompt_version": PROMPT_VERSION,
        "provider": "mock" if mock_judge else provider,
        "model_id": "mock-judge" if mock_judge else model,
        "attempts": len(attempts),
        "judge_response": None,
        "errors": attempts[-1]["errors"] if attempts else ["judge did not run"],
        "attempt_history": attempts,
    }


def evaluate_rows(
    rows: list[dict[str, Any]],
    dataset_path: Path,
    provider: str,
    model: str,
    max_retries: int,
    timeout: int,
    mock_judge: bool,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected_rows = rows[:limit] if limit is not None else rows
    run_started = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    for row in selected_rows:
        result = evaluate_row(row, provider, model, max_retries, timeout, mock_judge)
        result["run_metadata"] = {
            "run_started_at": run_started,
            "input_file": str(dataset_path),
            "provider": "mock" if mock_judge else provider,
            "temperature": 0,
            "max_retries": max_retries,
        }
        records.append(result)
    return records


def evaluate_rows_to_jsonl(
    rows: list[dict[str, Any]],
    dataset_path: Path,
    output_path: Path,
    provider: str,
    model: str,
    max_retries: int,
    timeout: int,
    mock_judge: bool,
    limit: int | None = None,
) -> tuple[int, int]:
    selected_rows = rows[:limit] if limit is not None else rows
    run_started = datetime.now(timezone.utc).isoformat()
    valid_count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in selected_rows:
            result = evaluate_row(row, provider, model, max_retries, timeout, mock_judge)
            result["run_metadata"] = {
                "run_started_at": run_started,
                "input_file": str(dataset_path),
                "provider": "mock" if mock_judge else provider,
                "temperature": 0,
                "max_retries": max_retries,
            }
            if result["status"] == "valid":
                valid_count += 1
            handle.write(json.dumps(result, ensure_ascii=False))
            handle.write("\n")
            handle.flush()
            print(f"{row['id']}: {result['status']}", flush=True)
    return len(selected_rows), valid_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output-prompts", type=Path, default=DEFAULT_PROMPTS_PATH)
    parser.add_argument("--output-results", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--print-prompt-id")
    parser.add_argument("--write-prompts", action="store_true")
    parser.add_argument("--run-judge", action="store_true")
    parser.add_argument("--mock-judge", action="store_true")
    parser.add_argument("--provider", choices=("openai", "openrouter"), default="openai")
    parser.add_argument("--model")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    load_env_file()
    model = args.model or (
        DEFAULT_OPENROUTER_MODEL if args.provider == "openrouter" else DEFAULT_OPENAI_MODEL
    )

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
        return 0

    if args.run_judge:
        total_count, valid_count = evaluate_rows_to_jsonl(
            rows=rows,
            dataset_path=args.dataset,
            output_path=args.output_results,
            provider=args.provider,
            model=model,
            max_retries=args.max_retries,
            timeout=args.timeout,
            mock_judge=args.mock_judge,
            limit=args.limit,
        )
        print(f"wrote {total_count} judge results to {args.output_results}")
        print(f"valid: {valid_count}")
        print(f"invalid: {total_count - valid_count}")
        return 0 if valid_count == total_count else 1

    print(f"built {len(records)} judge prompts with {PROMPT_VERSION}")
    print("use --write-prompts to write eval/judge_prompts.jsonl")
    print("use --run-judge to call the LLM judge and write eval/judge_results.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
