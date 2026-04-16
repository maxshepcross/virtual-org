"""Tests for AgentMail integration boundaries."""

import os
import unittest
from unittest.mock import Mock, patch

from services.agentmail_service import AgentMailSendRequest, AgentMailService


class AgentMailServiceTests(unittest.TestCase):
    def test_send_requires_api_key(self) -> None:
        with patch.dict(os.environ, {"AGENTMAIL_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "AGENTMAIL_API_KEY"):
                AgentMailService(api_key="").send_message(
                    AgentMailSendRequest(
                        inbox_id="inbox_1",
                        to="founder@example.com",
                        subject="Hello",
                        text="Body",
                    )
                )

    @patch("services.agentmail_service.httpx.post")
    def test_send_uses_agentmail_messages_endpoint(self, post) -> None:
        response = Mock()
        response.json.return_value = {"message_id": "msg_1", "thread_id": "thr_1"}
        response.raise_for_status.return_value = None
        post.return_value = response

        result = AgentMailService(api_key="key").send_message(
            AgentMailSendRequest(
                inbox_id="inbox_1",
                to="founder@example.com",
                subject="Hello",
                text="Body",
            )
        )

        self.assertEqual(result.message_id, "msg_1")
        self.assertIn("/v0/inboxes/inbox_1/messages/send", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer key")


if __name__ == "__main__":
    unittest.main()
