"""Small Slack Web API client shared by the dispatcher and Slack agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SlackPostResult:
    channel: str
    ts: str | None


class SlackApiError(RuntimeError):
    """Raised when a Slack API call fails."""


class SlackApiClient:
    """Small wrapper around Slack Web API methods used by this repo."""

    def __init__(self, bot_token: str | None = None) -> None:
        resolved_token = (bot_token or os.getenv("SLACK_BOT_TOKEN", "")).strip()
        if not resolved_token:
            raise SlackApiError("SLACK_BOT_TOKEN is not configured in .env.")
        self._client = httpx.Client(
            base_url="https://slack.com/api/",
            headers={"Authorization": f"Bearer {resolved_token}"},
            timeout=20.0,
        )

    def close(self) -> None:
        self._client.close()

    def post_message(
        self,
        *,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> SlackPostResult:
        payload: dict[str, Any] = {"channel": self._resolve_channel(channel), "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if blocks:
            payload["blocks"] = blocks
        data = self._call("chat.postMessage", payload)
        return SlackPostResult(channel=str(data.get("channel", payload["channel"])), ts=data.get("ts"))

    def update_message(
        self,
        *,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> SlackPostResult:
        payload: dict[str, Any] = {
            "channel": self._resolve_channel(channel),
            "ts": ts,
            "text": text,
        }
        if blocks is not None:
            payload["blocks"] = blocks
        data = self._call("chat.update", payload)
        return SlackPostResult(channel=str(data.get("channel", payload["channel"])), ts=data.get("ts"))

    def set_status(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        status: str,
        loading_messages: list[str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "status": status,
        }
        if loading_messages:
            payload["loading_messages"] = loading_messages
        self._call("assistant.threads.setStatus", payload)

    def set_title(self, *, channel_id: str, thread_ts: str, title: str) -> None:
        self._call(
            "assistant.threads.setTitle",
            {"channel_id": channel_id, "thread_ts": thread_ts, "title": title},
        )

    def set_suggested_prompts(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        prompts: list[dict[str, str]],
        title: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "prompts": prompts,
        }
        if title:
            payload["title"] = title
        self._call("assistant.threads.setSuggestedPrompts", payload)

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(method, json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise SlackApiError(f"Slack API error: {data.get('error', 'unknown_error')}")
        return data

    def _resolve_channel(self, channel: str) -> str:
        if not channel.startswith("#"):
            return channel

        target_name = channel.removeprefix("#")
        cursor: str | None = None
        while True:
            params = {
                "exclude_archived": "true",
                "limit": "200",
                "types": "public_channel,private_channel",
            }
            if cursor:
                params["cursor"] = cursor
            response = self._client.get("conversations.list", params=params)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise SlackApiError(f"Slack API error: {data.get('error', 'unknown_error')}")

            for conversation in data.get("channels", []):
                if conversation.get("name") == target_name:
                    return str(conversation["id"])

            cursor = data.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break

        raise SlackApiError(f"Slack channel {channel} was not found for the bot token.")
