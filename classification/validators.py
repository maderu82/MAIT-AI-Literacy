"""Deterministic checks over the prompt outputs: no model calls happen here.

The classification prompts demand exact, traceable quotations and fixed record
shapes. These checks are separate from the model calls so that a failed check
can re-run only the affected step, and so that quote verification is enforced
by the pipeline itself rather than trusted to the model.
"""
from __future__ import annotations

from typing import Any

# Page / step statuses
OK = "ok"
EXTRACTION_FAILED = "extraction_failed"
SCORE_FAILED = "score_failed"


def verify_quotes_everywhere(obj: Any, page_text: str) -> list[dict]:
    """Verify every {"quote": ...} string anywhere in a record occurs
    character-for-character in the scraped page text.

    Returns a list of problem dicts with the JSON path and the offending quote.
    An exact-match check only; the prompts treat any other normalisation as an
    error, so none is applied here either.
    """

    problems: list[dict] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            quote = node.get("quote")
            if isinstance(quote, str) and quote and quote not in page_text:
                problems.append({"path": path or "quote", "quote": quote[:160]})
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(obj, "")
    return problems


def check_extraction_shape(records: Any) -> list[str]:
    """Minimal structural checks on prompt 1 output. Deviations raise upstream,
    so the activity retry gives the model fresh attempts before a page is
    marked as failed."""
    if not isinstance(records, list):
        return ["prompt 1 output is not a JSON array"]
    notes: list[str] = []
    if not records:
        return notes
    for position, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            notes.append(f"record #{position} is not a JSON object")
            continue
        rec = record.get("record")
        if not isinstance(rec, dict) or "is_offering" not in rec:
            notes.append(f"record #{position} has no record block with is_offering")
    return notes


def check_score_shape(score: Any) -> list[str]:
    """Minimal structural checks on prompt 2 output."""
    if not isinstance(score, dict):
        return ["prompt 2 output is not a JSON object"]
    notes: list[str] = []
    rec = score.get("record")
    if not isinstance(rec, dict) or "scored" not in rec:
        notes.append("the score record has no record block with scored")
    if not isinstance(score.get("scores"), list):
        notes.append("the score record has no scores list")
    return notes


def summarize(pages_results: list[dict]) -> dict:
    """Deterministic batch summary over all page results.

    Counts cover: pages, offerings, scoring outcomes, signals by kind and by
    label, records flagged for review, and quote check failures. The signal
    counts have the fixed taxonomy of prompts 1 and 2, so an output of this
    pipeline is ready for the bundling step (prompt 4) once that prompt exists.
    """
    signals_by_kind: dict[str, int] = {}
    signals_by_label: dict[str, int] = {}
    counts = {
        "pages": len(pages_results),
        "pages_ok": 0,
        "pages_extraction_failed": 0,
        "offerings": 0,
        "not_offerings": 0,
        "offerings_scored": 0,
        "scores_failed": 0,
        "trial_run_records": 0,
        "records_flagged_for_review": 0,
        "quote_problems": 0,
    }
    review_offering_ids: list[str] = []
    quote_problem_paths: list[dict] = []

    def take_signals(container: Any) -> None:
        for signal in (container or []) if isinstance(container, list) else []:
            if not isinstance(signal, dict):
                continue
            kind = signal.get("kind") or "?"
            label = signal.get("label") or "?"
            signals_by_kind[kind] = signals_by_kind.get(kind, 0) + 1
            signals_by_label[label] = signals_by_label.get(label, 0) + 1

    for page_result in pages_results:
        status = page_result.get("status")
        if status == EXTRACTION_FAILED:
            counts["pages_extraction_failed"] += 1
            continue
        counts["pages_ok"] += 1
        for record in page_result.get("extraction") or []:
            if not isinstance(record, dict):
                continue
            rec = record.get("record") or {}
            counts["offerings"] += 1
            if rec.get("is_offering") is False:
                counts["not_offerings"] += 1
            if rec.get("trial_run"):
                counts["trial_run_records"] += 1
            if rec.get("review_recommended"):
                counts["records_flagged_for_review"] += 1
                review_offering_ids.append(str(rec.get("offering_id") or "?"))
            take_signals(record.get("signals"))
        for score in page_result.get("score_records") or []:
            if not isinstance(score, dict):
                continue
            rec = score.get("record") or {}
            if rec.get("scored") is False or score.get("status") == SCORE_FAILED:
                counts["scores_failed"] += 1
            else:
                counts["offerings_scored"] += 1
            take_signals(score.get("signals"))
        problems = page_result.get("quote_problems") or []
        counts["quote_problems"] += len(problems)
        quote_problem_paths.extend(problems)

    return {
        "counts": counts,
        "signals_by_kind": signals_by_kind,
        "signals_by_label": signals_by_label,
        "review_offering_ids": review_offering_ids,
        "quote_problem_sample": quote_problem_paths[:25],
    }
