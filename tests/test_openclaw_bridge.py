"""Tests for the OpenClaw Gateway chat bridge."""

import os
import unittest
from unittest.mock import patch

from services.openclaw_bridge import send_openclaw_chat_message


class OpenClawBridgeTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "OPENCLAW_CHAT_BASE_URL": "http://127.0.0.1:18789/v1",
            "OPENCLAW_GATEWAY_TOKEN": "test-token",
            "OPENCLAW_CHAT_MODEL": "openclaw/default",
        },
    )
    @patch("services.openclaw_bridge.httpx.post")
    def test_send_openclaw_chat_message_calls_gateway_chat_endpoint(self, post) -> None:
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "OpenClaw response"}}],
        }

        result = send_openclaw_chat_message(
            "What is blocked?",
            session_key="slack:C123:111.222",
            slack_user_id="U123",
        )

        self.assertEqual(result.text, "OpenClaw response")
        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(kwargs["headers"]["x-openclaw-session-key"], "slack:C123:111.222")
        self.assertEqual(kwargs["headers"]["x-openclaw-message-channel"], "slack-control-bridge")
        self.assertEqual(kwargs["json"]["messages"][0]["content"], "What is blocked?")


if __name__ == "__main__":
    unittest.main()
