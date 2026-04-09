"""Planning helpers for shaping rough tasks into a brief and small execution slices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from config.constants import MAX_RESEARCH_TOKENS, RESEARCH_MODEL
from models.task import Task

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
CREATE_PRD_PROMPT = (PROMPTS_DIR / "create_prd.md").read_text()
TASK_BREAKDOWN_PROMPT = (PROMPTS_DIR / "task_breakdown.md").read_text()


def _coerce_prompt_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value if item is not None)
    if isinstance(value, dict):
        return json.dumps(value, indent=2, sort_keys=True)
    return str(value)


def _render_prompt(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{key}}}", _coerce_prompt_value(value))
    return rendered


def _extract_fenced_block(text: str, fence: str) -> str:
    marker = f"```{fence}"
    if marker in text:
        return text.split(marker, 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text.strip()


def _call_llm_text(client: Anthropic, prompt: str, max_tokens: int) -> str:
    response = client.messages.create(
        model=RESEARCH_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _call_llm_json(client: Anthropic, prompt: str, max_tokens: int) -> dict[str, Any]:
    text = _call_llm_text(client, prompt, max_tokens)
    try:
        return json.loads(_extract_fenced_block(text, "json"))
    except json.JSONDecodeError:
        return {}


def _normalize_breakdown(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    stories = data.get("execution_stories")
    if not isinstance(stories, list):
        stories = []
    return {
        "summary": str(data.get("summary") or ""),
        "execution_stories": [
            story for story in stories
            if isinstance(story, dict)
        ],
    }


def build_planning_context(task: Task, client: Anthropic | None = None) -> dict[str, Any]:
    client = client or Anthropic()

    prompt_values = {
        "title": task.title,
        "category": task.category,
        "description": task.description,
        "target_repo": task.target_repo or "N/A",
    }
    prd_markdown = _call_llm_text(
        client,
        _render_prompt(CREATE_PRD_PROMPT, prompt_values),
        max_tokens=max(800, MAX_RESEARCH_TOKENS // 2),
    )

    breakdown_prompt = _render_prompt(
        TASK_BREAKDOWN_PROMPT,
        {
            **prompt_values,
            "prd_markdown": prd_markdown,
        },
    )
    task_breakdown = _normalize_breakdown(
        _call_llm_json(
            client,
            breakdown_prompt,
            max_tokens=max(1200, MAX_RESEARCH_TOKENS // 2),
        )
    )

    return {
        "prd_markdown": prd_markdown,
        "task_breakdown": task_breakdown,
    }


def merge_planning_context(
    result: dict[str, Any],
    planning_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not planning_context:
        return result

    merged = dict(result)
    task_breakdown = planning_context.get("task_breakdown") or {}
    breakdown_summary = str(task_breakdown.get("summary") or "").strip()
    breakdown_stories = task_breakdown.get("execution_stories") or []

    if not merged.get("summary") and breakdown_summary:
        merged["summary"] = breakdown_summary
    if not merged.get("execution_stories") and breakdown_stories:
        merged["execution_stories"] = breakdown_stories

    merged["prd_markdown"] = str(planning_context.get("prd_markdown") or "")
    merged["task_breakdown_json"] = task_breakdown
    return merged
