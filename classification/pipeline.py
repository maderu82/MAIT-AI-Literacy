"""The AI literacy classification pipeline.

Steps per scrape batch:
  0. Fail fast when the framework file cannot support extraction or scoring.
  1. Prompt 1 (extraction): one call per scraped page, run in parallel waves.
  2. Deterministic quote verification against the scraped text.
  3. Prompt 2 (scoring): one call per extracted offering.
  4. Deterministic checks and a batch summary ready for bundling (prompt 4).

The framework file (codebook) comes from the human-in-the-loop framework
builder cycle (prompt 3) and is supplied as a run input here. This pipeline
applies it as it stands and never changes it.
"""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import mistralai.workflows as workflows

from .llm import run_prompt
from .models import PipelineInput, ScrapePage
from .validators import (
    EXTRACTION_FAILED,
    OK,
    SCORE_FAILED,
    check_extraction_shape,
    check_score_shape,
    summarize,
    verify_quotes_everywhere,
)

# Section headings of the framework file format (prompt 3, section 9).
# Extraction needs sections 1-3; scoring also needs section 4.
REQUIRED_SECTIONS = ["Purpose and scope", "Unit of analysis", "Dimensions", "General scoring rules"]


def _read_prompt(name: str) -> str:
    # Resolved lazily, inside the activity: workflow code runs in a sandbox
    # that forbids filesystem access at import time; activities may read files.
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    return (prompts_dir / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Activities (each one is an isolated unit of work with its own retries)
# --------------------------------------------------------------------------


@workflows.activity(
    name="extraction_prompt1",
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy_max_attempts=3,
    retry_policy_backoff_coefficient=2.0,
)
async def extract_page(
    page: ScrapePage, framework: str, model: str, temperature: float
) -> list[dict]:
    """Prompt 1 (extraction): messages per offering, mapped to the framework, with signals.

    Raises when the answer is not usable JSON in the required shape, so the
    platform retry gives the model fresh attempts.
    """
    source = page.url or page.page_id or page.provider or ""
    user = (
        "<scraped_text>\n"
        f"{page.text}\n"
        "</scraped_text>\n\n"
        "<framework>\n"
        f"{framework}\n"
        "</framework>\n\n"
        f"<source>{source}</source>"
    )
    records = await run_prompt(
        system=_read_prompt("prompt-1-extractie.md"),
        user=user,
        model=model,
        temperature=temperature,
        expect="array",
    )
    shape_notes = check_extraction_shape(records)
    if shape_notes:
        raise ValueError(
            "Extraction output failed structural checks: " + "; ".join(shape_notes)
        )
    return records


@workflows.activity(
    name="scoring_prompt2",
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy_max_attempts=3,
    retry_policy_backoff_coefficient=2.0,
)
async def score_offering(
    page_text: str, extraction_record: dict, framework: str, model: str, temperature: float
) -> dict:
    """Prompt 2 (scoring): one score record for one offering, as second reader."""
    user = (
        "<scraped_text>\n"
        f"{page_text}\n"
        "</scraped_text>\n\n"
        "<extraction_record>\n"
        f"{json.dumps(extraction_record, ensure_ascii=False, indent=2)}\n"
        "</extraction_record>\n\n"
        "<framework>\n"
        f"{framework}\n"
        "</framework>"
    )
    score = await run_prompt(
        system=_read_prompt("prompt-2-scoring.md"),
        user=user,
        model=model,
        temperature=temperature,
        expect="object",
    )
    shape_notes = check_score_shape(score)
    if shape_notes:
        raise ValueError(
            "Scoring output failed structural checks: " + "; ".join(shape_notes)
        )
    return score


# --------------------------------------------------------------------------
# Workflow (orchestration only: ordering, fan-out, failure isolation)
# --------------------------------------------------------------------------


@workflows.workflow.define(
    name="ai-geletterdheid-classificatie",
    workflow_display_name="AI-geletterdheid classificatie",
    workflow_description=(
        "Classificeert scrapingresultaten van aanbieders van AI-geletterdheid: "
        "extractie (prompt 1) per gescrapte pagina, scoring (prompt 2) per aanbod, "
        "automatische citaatcontrole en een batchsamenvatting van de signalen. "
        "Input: het frameworkbestand + de gescrapte pagina's."
    ),
    execution_timeout=timedelta(hours=6),
)
class AiLiteracyClassificationWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, params: PipelineInput) -> dict:
        # Step 0: the prompts themselves refuse an incomplete framework file;
        # fail the whole run fast instead of paying for calls that cannot work.
        missing = [s for s in REQUIRED_SECTIONS if s not in params.framework]
        if missing:
            return {
                "error": (
                    "Framework file is missing section(s): "
                    + ", ".join(missing)
                    + ". Supply the complete framework file (sections 1-6) as "
                    "produced by the framework builder (prompt 3)."
                )
            }

        pages_results: list[dict] = []

        for start in range(0, len(params.pages), params.max_concurrent):
            chunk = list(params.pages[start : start + params.max_concurrent])

            # Wave 1: extraction (prompt 1), one call per page, in parallel.
            extraction_results = await asyncio.gather(
                *[
                    extract_page(
                        page=page,
                        framework=params.framework,
                        model=params.model,
                        temperature=params.temperature,
                    )
                    for page in chunk
                ],
                return_exceptions=True,
            )

            chunk_shells: list[dict] = []
            for page, outcome in zip(chunk, extraction_results):
                shell: dict[str, Any] = {
                    "page": page.model_dump(),
                    "status": OK,
                    "error": None,
                    "extraction": [],
                    "score_records": [],
                    "quote_problems": [],
                }
                if isinstance(outcome, BaseException):
                    shell["status"] = EXTRACTION_FAILED
                    shell["error"] = f"{type(outcome).__name__}: {outcome}"[:600]
                else:
                    shell["extraction"] = outcome
                    shell["quote_problems"] = verify_quotes_everywhere(
                        outcome, page.text
                    )
                chunk_shells.append(shell)
            pages_results.extend(chunk_shells)

            # Wave 2: scoring (prompt 2), one call per extracted offering.
            score_calls = []
            score_refs = []
            for shell in chunk_shells:
                if shell["status"] != OK:
                    continue
                for record in shell["extraction"]:
                    rec_block = record.get("record") if isinstance(record, dict) else None
                    if not isinstance(rec_block, dict) or rec_block.get("is_offering") is False:
                        continue
                    score_calls.append(
                        score_offering(
                            page_text=shell["page"]["text"],
                            extraction_record=record,
                            framework=params.framework,
                            model=params.model,
                            temperature=params.temperature,
                        )
                    )
                    score_refs.append((shell, rec_block.get("offering_id")))

            if score_calls:
                score_results = await asyncio.gather(*score_calls, return_exceptions=True)
                for (shell, offering_id), outcome in zip(score_refs, score_results):
                    if isinstance(outcome, BaseException):
                        shell["score_records"].append(
                            {
                                "offering_id": offering_id,
                                "status": SCORE_FAILED,
                                "error": f"{type(outcome).__name__}: {outcome}"[:600],
                            }
                        )
                        continue
                    shell["score_records"].append(outcome)
                    problems = verify_quotes_everywhere(outcome, shell["page"]["text"])
                    if problems:
                        shell["quote_problems"].extend(problems)

        return {
            "batch_label": params.batch_label,
            "framework_name": params.framework_name,
            "model": params.model,
            "summary": summarize(pages_results),
            "pages": pages_results,
        }
