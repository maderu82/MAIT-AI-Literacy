"""LLM call helper for the classification pipeline.

All model calls go through get_mistral_client() so telemetry, observability
metadata and credentials (the injected service-account token in managed
deployments) work without any API key in the repository.
"""
from __future__ import annotations

import json
import re
from typing import Any

from mistralai.workflows.client import get_mistral_client

MAX_TOKENS = 8192


class PromptOutputError(RuntimeError):
    """Raised when the model output cannot be parsed as the expected JSON shape.

    Raising inside an activity triggers the platform retry, which gives the
    model fresh attempts with a clean call.
    """


def _strip_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", content)
        content = re.sub(r"\s*```\s*$", "", content)
    return content.strip()


def parse_json_payload(content: str | None, expect: str) -> Any:
    """Parse the model's raw answer into JSON of the expected top-level shape."""
    if not content or not content.strip():
        raise PromptOutputError("The model returned an empty answer.")
    text = _strip_fences(content)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: slice out the outermost JSON value.
    opener, closer = ("[", "]") if expect == "array" else ("{", "}")
    start, end = text.find(opener), text.rfind(closer)
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise PromptOutputError(
                f"The model output could not be parsed as JSON ({exc}). Head: {text[:200]!r}"
            ) from exc
    raise PromptOutputError(f"No JSON found in the model output. Head: {text[:200]!r}")


async def run_prompt(
    system: str, user: str, model: str, temperature: float, expect: str
) -> Any:
    """Run one classification prompt over one input and return the parsed JSON.

    expect: "array" (prompt 1: one JSON object per offering) or
            "object" (prompt 2: one score record).
    """
    client = get_mistral_client()
    response = await client.chat.complete_async(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=MAX_TOKENS,
    )
    content = None
    if response is not None and getattr(response, "choices", None):
        content = response.choices[0].message.content

    data = parse_json_payload(content, expect)
    if expect == "array" and not isinstance(data, list):
        raise PromptOutputError(
            f"Expected a JSON array, got {type(data).__name__}. Head: {str(data)[:200]!r}"
        )
    if expect == "object" and not isinstance(data, dict):
        raise PromptOutputError(
            f"Expected a JSON object, got {type(data).__name__}. Head: {str(data)[:200]!r}"
        )
    return data
