"""Briefing helpers for turning attention items into short founder summaries."""

from __future__ import annotations

from models.control_plane import Briefing, create_briefing, list_attention_items


def generate_briefing(scope: str, delivered_to: str | None = None) -> Briefing:
    attention_items = list_attention_items(limit=10)
    items = [
        {
            "id": item.id,
            "headline": item.headline,
            "severity": item.severity,
            "recommended_action": item.recommended_action,
        }
        for item in attention_items
    ]
    headline = f"{scope.title()} briefing with {len(items)} active attention item(s)"
    return create_briefing(scope=scope, headline=headline, items_json=items, delivered_to=delivered_to)
