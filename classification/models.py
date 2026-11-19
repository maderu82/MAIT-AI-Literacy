"""Input models for the AI literacy classification pipeline."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScrapePage(BaseModel):
    """One scraped provider page, exactly as the inventory/scrape step fetched it."""

    text: str = Field(..., description="The scraped page text, unmodified.")
    page_id: str | None = Field(
        default=None,
        description="Stable identifier for this page, e.g. the row id in the scrape workbook.",
    )
    provider: str | None = Field(default=None, description="Provider name as recorded during scraping.")
    page_title: str | None = Field(default=None, description="Page title as recorded during scraping.")
    url: str | None = Field(default=None, description="Source URL of the page.")
    fetched_at: str | None = Field(default=None, description="Timestamp of the scrape, ISO 8601 recommended.")


class PipelineInput(BaseModel):
    """One classification run over a scrape batch against one framework version."""

    framework: str = Field(
        ...,
        description=(
            "The complete framework file (codebook, sections 1-6) as markdown, "
            "exactly as produced and approved through the framework-builder cycle. "
            "The pipeline reads it as material; it never changes it."
        ),
    )
    pages: list[ScrapePage] = Field(
        ...,
        min_length=1,
        description="The scraped pages to classify. Keep batches under ~150 pages per run.",
    )
    framework_name: str | None = Field(
        default=None,
        description="Optional provenance: the framework file name or reference, kept with the results."
    )
    batch_label: str | None = Field(
        default=None,
        description="Optional label for this scrape batch, e.g. 'Scrape 2026-11-19'."
    )
    model: str = Field(
        default="mistral-medium-latest",
        description="Model used for both extraction (prompt 1) and scoring (prompt 2)."
    )
    max_concurrent: int = Field(
        default=6,
        ge=1,
        le=16,
        description="Pages processed in parallel per wave. Lower it when hitting rate limits."
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for the classification calls; keep it low for consistency."
    )
