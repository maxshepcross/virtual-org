"""Reusable workflow recipes and shared memory for the control plane.

This file stores two lightweight knowledge types:
- workflow recipes: repeatable task templates you can run again later
- memory entries: prompts, plans, and decisions worth keeping out of chat history
"""

from __future__ import annotations

import json
import logging
import re
import string
from datetime import date, datetime, timezone
from typing import Any

import psycopg2.extras
from pydantic import BaseModel, Field

from models.task import Task, _conn, create_task

logger = logging.getLogger(__name__)
MAX_MEMORY_BODY_CHARS = 4000
MAX_CONTEXT_BODY_CHARS = 500
MAX_TITLE_CHARS = 200
MAX_SUMMARY_CHARS = 1000
_TEMPLATE_FORMATTER = string.Formatter()


class WorkflowRecipe(BaseModel):
    id: int | None = None
    slug: str
    title: str
    summary: str
    category: str
    target_repo: str | None = None
    venture: str | None = None
    task_title_template: str
    task_description_template: str
    tags_json: list[str] = Field(default_factory=list)
    created_by: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class MemoryEntry(BaseModel):
    id: int | None = None
    kind: str
    title: str
    body: str
    task_id: int | None = None
    target_repo: str | None = None
    venture: str | None = None
    tags_json: list[str] = Field(default_factory=list)
    source_key: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _decode_json_fields(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    for field in fields:
        if row.get(field) and isinstance(row[field], str):
            row[field] = json.loads(row[field])
    return row


def _row_to_model(
    row: dict[str, Any] | None,
    model: type[BaseModel],
    *json_fields: str,
) -> BaseModel | None:
    if not row:
        return None
    return model(**_decode_json_fields(row, *json_fields))


def _normalize_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Workflow recipe slug cannot be empty.")
    return normalized[:80]


def _normalize_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for tag in tags or []:
        value = str(tag).strip().lower()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", (text or "").lower()))


def _clean_required_text(value: str, field_name: str, *, max_chars: int) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty.")
    if len(cleaned) > max_chars:
        raise ValueError(f"{field_name} cannot exceed {max_chars} characters.")
    return cleaned


def _validate_template(template: str, field_name: str) -> str:
    try:
        parsed = list(_TEMPLATE_FORMATTER.parse(template))
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid template: {exc}") from exc

    for _, placeholder, _, _ in parsed:
        if not placeholder:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", placeholder):
            raise ValueError(
                f"{field_name} can only use simple placeholders like {{request}} or {{today}}."
            )

    try:
        template.format_map(_SafeTemplateValues({"request": "example"}))
    except (KeyError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} is not a valid template: {exc}") from exc
    return template


class _SafeTemplateValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def create_workflow_recipe(
    *,
    slug: str | None,
    title: str,
    summary: str,
    category: str,
    target_repo: str | None = None,
    venture: str | None = None,
    task_title_template: str | None = None,
    task_description_template: str | None = None,
    tags: list[str] | None = None,
    created_by: str | None = None,
) -> WorkflowRecipe:
    title = _clean_required_text(title, "title", max_chars=MAX_TITLE_CHARS)
    summary = _clean_required_text(summary, "summary", max_chars=MAX_SUMMARY_CHARS)
    category = _clean_required_text(category, "category", max_chars=80)
    recipe_slug = _normalize_slug(slug or title)
    title_template = (task_title_template or title).strip() or title
    description_template = (
        task_description_template
        or (
            f"{summary}\n\n"
            "Request:\n"
            "{request}\n"
        )
    ).strip()
    title_template = _validate_template(title_template, "task_title_template")
    description_template = _validate_template(description_template, "task_description_template")

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO workflow_recipes (
                    slug,
                    title,
                    summary,
                    category,
                    target_repo,
                    venture,
                    task_title_template,
                    task_description_template,
                    tags_json,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (slug)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    category = EXCLUDED.category,
                    target_repo = EXCLUDED.target_repo,
                    venture = EXCLUDED.venture,
                    task_title_template = EXCLUDED.task_title_template,
                    task_description_template = EXCLUDED.task_description_template,
                    tags_json = EXCLUDED.tags_json,
                    created_by = COALESCE(EXCLUDED.created_by, workflow_recipes.created_by),
                    updated_at = NOW()
                RETURNING *
                """,
                (
                    recipe_slug,
                    title,
                    summary,
                    category,
                    (target_repo or "").strip() or None,
                    (venture or "").strip() or None,
                    title_template,
                    description_template,
                    json.dumps(_normalize_tags(tags)),
                    (created_by or "").strip() or None,
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), WorkflowRecipe, "tags_json")
    finally:
        conn.close()


def list_workflow_recipes(
    *,
    limit: int = 50,
    category: str | None = None,
    target_repo: str | None = None,
) -> list[WorkflowRecipe]:
    conn = _conn()
    where_parts: list[str] = []
    params: list[Any] = []
    if category:
        where_parts.append("category = %s")
        params.append(category)
    if target_repo:
        where_parts.append("(target_repo = %s OR target_repo IS NULL)")
        params.append(target_repo)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    params.append(max(1, min(int(limit), 200)))

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT * FROM workflow_recipes
                {where_sql}
                ORDER BY COALESCE(last_used_at, created_at) DESC, id DESC
                LIMIT %s
                """,
                params,
            )
            return [
                _row_to_model(row, WorkflowRecipe, "tags_json")
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def get_workflow_recipe(slug: str) -> WorkflowRecipe | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM workflow_recipes WHERE slug = %s",
                (_normalize_slug(slug),),
            )
            return _row_to_model(cur.fetchone(), WorkflowRecipe, "tags_json")
    finally:
        conn.close()


def create_task_from_workflow_recipe(
    slug: str,
    *,
    request: str = "",
    variables: dict[str, Any] | None = None,
    requested_by: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
) -> Task:
    recipe = get_workflow_recipe(slug)
    if not recipe:
        raise ValueError(f"Workflow recipe '{slug}' was not found.")

    template_values = _SafeTemplateValues(
        {
            "request": (request or "").strip(),
            "today": date.today().isoformat(),
            "target_repo": recipe.target_repo or "",
            "venture": recipe.venture or "",
            **{str(key): str(value) for key, value in (variables or {}).items()},
        }
    )
    title = recipe.task_title_template.format_map(template_values).strip() or recipe.title
    description = recipe.task_description_template.format_map(template_values).strip() or recipe.summary

    task = create_task(
        idea_id=None,
        title=title,
        description=description,
        category=recipe.category,
        target_repo=recipe.target_repo,
        venture=recipe.venture,
        requested_by=requested_by,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
    )

    try:
        conn = _conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_recipes
                    SET last_used_at = NOW(),
                        updated_at = NOW()
                    WHERE slug = %s
                    """,
                    (recipe.slug,),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Could not mark workflow recipe '%s' as used: %s", recipe.slug, exc)

    return task


def upsert_memory_entry(
    *,
    kind: str,
    title: str,
    body: str,
    task_id: int | None = None,
    target_repo: str | None = None,
    venture: str | None = None,
    tags: list[str] | None = None,
    source_key: str | None = None,
    created_by: str | None = None,
) -> MemoryEntry:
    kind = _clean_required_text(kind, "kind", max_chars=40)
    title = _clean_required_text(title, "title", max_chars=MAX_TITLE_CHARS)
    body = _clean_required_text(body, "body", max_chars=MAX_MEMORY_BODY_CHARS)

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO memory_entries (
                    kind,
                    title,
                    body,
                    task_id,
                    target_repo,
                    venture,
                    tags_json,
                    source_key,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_key)
                DO UPDATE SET
                    kind = EXCLUDED.kind,
                    title = EXCLUDED.title,
                    body = EXCLUDED.body,
                    task_id = EXCLUDED.task_id,
                    target_repo = EXCLUDED.target_repo,
                    venture = EXCLUDED.venture,
                    tags_json = EXCLUDED.tags_json,
                    created_by = COALESCE(EXCLUDED.created_by, memory_entries.created_by)
                RETURNING *
                """,
                (
                    kind,
                    title,
                    body,
                    task_id,
                    (target_repo or "").strip() or None,
                    (venture or "").strip() or None,
                    json.dumps(_normalize_tags(tags)),
                    (source_key or "").strip() or None,
                    (created_by or "").strip() or None,
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), MemoryEntry, "tags_json")
    finally:
        conn.close()


def list_memory_entries(
    *,
    limit: int = 50,
    kind: str | None = None,
    target_repo: str | None = None,
    venture: str | None = None,
) -> list[MemoryEntry]:
    conn = _conn()
    where_parts: list[str] = []
    params: list[Any] = []
    if kind:
        where_parts.append("kind = %s")
        params.append(kind)
    if target_repo:
        where_parts.append("(target_repo = %s OR target_repo IS NULL)")
        params.append(target_repo)
    if venture:
        where_parts.append("(venture = %s OR venture IS NULL)")
        params.append(venture)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    params.append(max(1, min(int(limit), 200)))

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT * FROM memory_entries
                {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                params,
            )
            return [
                _row_to_model(row, MemoryEntry, "tags_json")
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def build_reusable_context(task: Task, *, limit: int = 3) -> dict[str, str]:
    """Return the most relevant recipes and memories as prompt-ready markdown."""
    if not task.target_repo and not task.venture:
        return {"workflow_context": "", "memory_context": ""}

    recipe_candidates = list_workflow_recipes(limit=50, target_repo=task.target_repo, category=task.category)
    memory_candidates = list_memory_entries(limit=100, target_repo=task.target_repo, venture=task.venture)
    task_tokens = _tokenize(f"{task.title} {task.description} {task.category} {task.venture or ''}")

    def score_recipe(recipe: WorkflowRecipe) -> int:
        score = 0
        if task.target_repo and recipe.target_repo == task.target_repo:
            score += 12
        if task.venture and recipe.venture == task.venture:
            score += 8
        if recipe.category == task.category:
            score += 6
        score += len(
            task_tokens.intersection(
                _tokenize(f"{recipe.title} {recipe.summary} {' '.join(recipe.tags_json)}")
            )
        )
        return score

    def score_memory(entry: MemoryEntry) -> int:
        score = 0
        if task.target_repo and entry.target_repo == task.target_repo:
            score += 10
        if task.venture and entry.venture == task.venture:
            score += 8
        if entry.kind == "decision":
            score += 2
        score += len(
            task_tokens.intersection(
                _tokenize(f"{entry.title} {entry.body[:MAX_CONTEXT_BODY_CHARS]} {' '.join(entry.tags_json)}")
            )
        )
        return score

    top_recipes = [
        recipe for recipe in sorted(recipe_candidates, key=score_recipe, reverse=True)
        if score_recipe(recipe) > 0
    ][: max(0, int(limit))]
    top_memory = [
        entry for entry in sorted(memory_candidates, key=score_memory, reverse=True)
        if score_memory(entry) > 0
    ][: max(0, int(limit))]

    workflow_lines = [
        json.dumps(
            {
                "slug": recipe.slug,
                "title": recipe.title,
                "summary": recipe.summary,
                "target_repo": recipe.target_repo,
                "venture": recipe.venture,
            },
            sort_keys=True,
        )
        for recipe in top_recipes
    ]
    memory_lines = [
        json.dumps(
            {
                "kind": entry.kind,
                "title": entry.title,
                "body_excerpt": entry.body[:MAX_CONTEXT_BODY_CHARS].strip(),
                "target_repo": entry.target_repo,
                "venture": entry.venture,
            },
            sort_keys=True,
        )
        for entry in top_memory
    ]

    return {
        "workflow_context": "\n".join(workflow_lines),
        "memory_context": "\n".join(memory_lines),
    }
