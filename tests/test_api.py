"""Tests for the internal control-plane HTTP API."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from models.control_plane import AgentRun, ApprovalRequest, AttentionItem, Briefing, Signal
from models.task import Task


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = patch.dict(os.environ, {"CONTROL_API_TOKEN": "test-token"}, clear=False)
        self.env_patcher.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token"}

    def tearDown(self) -> None:
        self.env_patcher.stop()

    @patch("api.app.record_signal")
    def test_create_signal_endpoint_returns_signal_and_attention_item(self, record_signal) -> None:
        record_signal.return_value = {
            "signal": Signal(
                id=1,
                source="policy",
                kind="approval_required",
                severity="high",
                summary="Push requires approval",
                dedupe_key="abc123",
                bucket="approval_required",
            ),
            "attention_item": AttentionItem(
                id=2,
                signal_id=1,
                bucket="approval_required",
                severity="high",
                headline="Push requires approval",
                recommended_action="Approve or deny it.",
            ),
            "deduped": False,
        }

        response = self.client.post(
            "/v1/signals",
            json={
                "source": "policy",
                "kind": "approval_required",
                "severity": "high",
                "summary": "Push requires approval",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["signal"]["kind"], "approval_required")
        self.assertEqual(response.json()["attention_item"]["bucket"], "approval_required")

    @patch("api.app.list_attention_items")
    def test_list_attention_endpoint_filters_by_venture(self, list_attention_items) -> None:
        list_attention_items.return_value = [
            AttentionItem(
                id=2,
                venture="officely",
                bucket="digest",
                severity="normal",
                headline="Usage is up 20% this week",
                recommended_action="Include this in the next founder brief.",
            )
        ]

        response = self.client.get("/v1/attention?venture=officely&limit=5", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["venture"], "officely")
        list_attention_items.assert_called_once_with(limit=5, venture="officely")

    @patch("api.app.record_business_signal")
    def test_create_business_signal_endpoint_returns_importance_decision(self, record_business_signal) -> None:
        record_business_signal.return_value = {
            "decision": {
                "should_record": True,
                "kind": "usage_trend",
                "severity": "normal",
                "bucket": "digest",
                "summary": "Usage is up 20% this week",
                "recommended_action": "Include this in the next founder brief.",
                "reason": "Product usage improved enough to mention in a brief.",
            },
            "signal": Signal(
                id=4,
                source="paperclip",
                kind="usage_trend",
                venture="officely",
                severity="normal",
                summary="Usage is up 20% this week",
                dedupe_key="abc123",
                bucket="digest",
            ),
            "attention_item": AttentionItem(
                id=5,
                signal_id=4,
                venture="officely",
                bucket="digest",
                severity="normal",
                headline="Usage is up 20% this week",
                recommended_action="Include this in the next founder brief.",
            ),
            "deduped": False,
        }

        response = self.client.post(
            "/v1/intake/business-signals",
            json={
                "source": "paperclip",
                "category": "usage",
                "metric_name": "weekly_active_teams",
                "summary": "Usage is up 20% this week",
                "venture": "officely",
                "direction": "up",
                "change_percent": 20,
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["decision"]["bucket"], "digest")
        self.assertEqual(response.json()["signal"]["kind"], "usage_trend")

    @patch("api.app.list_tasks")
    def test_list_tasks_endpoint_returns_filtered_tasks(self, list_tasks) -> None:
        list_tasks.return_value = [
            Task(id=7, title="Ship fix", description="desc", category="ops", status="blocked"),
        ]

        response = self.client.get("/v1/tasks?status=blocked&limit=10", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], 7)
        list_tasks.assert_called_once_with(limit=10, status="blocked", venture=None, requested_by=None)

    @patch("api.app.create_task")
    def test_create_task_endpoint_returns_record(self, create_task) -> None:
        create_task.return_value = Task(
            id=9,
            title="New task",
            description="desc",
            category="ops",
            status="queued",
        )

        response = self.client.post(
            "/v1/tasks",
            json={"title": "New task", "description": "desc", "category": "ops"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], 9)

    @patch("api.app.evaluate_and_record_policy")
    def test_policy_endpoint_returns_decision(self, evaluate_and_record_policy) -> None:
        evaluate_and_record_policy.return_value = type(
            "Result",
            (),
            {
                "model_dump": lambda self: {
                    "decision": "allow",
                    "policy_name": "default",
                    "reason": "ok",
                    "approval_required": False,
                    "policy_decision_id": 1,
                    "approval_request_id": None,
                    "signal_id": None,
                    "attention_item_id": None,
                }
            },
        )()

        response = self.client.post(
            "/v1/policy/evaluate",
            json={
                "task_id": 1,
                "agent_role": "implementer",
                "action_type": "read",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "allow")

    @patch("api.app.resolve_approval")
    def test_resolve_approval_returns_forbidden_for_untrusted_users(self, resolve_approval) -> None:
        resolve_approval.side_effect = PermissionError("Slack user is not allowed to approve actions.")

        response = self.client.post(
            "/v1/approvals/12/resolve",
            json={
                "slack_user_id": "U123",
                "resolution": "approved",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 403)

    @patch("api.app.create_approval")
    def test_create_approval_endpoint_returns_record(self, create_approval) -> None:
        create_approval.return_value = ApprovalRequest(
            id=3,
            task_id=9,
            action_type="git_push",
            target_summary="Push branch to repo",
        )

        response = self.client.post(
            "/v1/approvals",
            json={
                "task_id": 9,
                "action_type": "git_push",
                "target_summary": "Push branch to repo",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["action_type"], "git_push")

    @patch("api.app.create_approval")
    def test_create_approval_endpoint_returns_bad_request_for_missing_task(self, create_approval) -> None:
        create_approval.side_effect = ValueError("Task 1 was not found.")

        response = self.client.post(
            "/v1/approvals",
            json={
                "task_id": 1,
                "action_type": "git_push",
                "target_summary": "Push branch to repo",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Task 1 was not found.")

    @patch("api.app.complete_manual_verification")
    def test_complete_manual_verification_endpoint_returns_updated_task(self, complete_manual_verification) -> None:
        complete_manual_verification.return_value = Task(
            id=7,
            title="Verify story",
            description="desc",
            category="ops",
            status="queued",
            current_story_id="STORY-2",
        )

        response = self.client.post(
            "/v1/tasks/7/manual-verification/complete",
            json={"story_id": "STORY-1", "note": "Checked in browser"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")
        complete_manual_verification.assert_called_once_with(
            task_id=7,
            story_id="STORY-1",
            note="Checked in browser",
        )

    @patch("api.app.requeue_task")
    def test_requeue_task_endpoint_returns_updated_task(self, requeue_task) -> None:
        requeue_task.return_value = Task(
            id=7,
            title="Retry task",
            description="desc",
            category="ops",
            status="queued",
        )

        response = self.client.post(
            "/v1/tasks/7/requeue",
            json={"note": "Try again"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")
        requeue_task.assert_called_once_with(7, note="Try again")

    @patch("api.app.create_agent_run")
    def test_create_agent_run_endpoint_returns_rich_run_record(self, create_agent_run) -> None:
        create_agent_run.return_value = AgentRun(
            id=11,
            task_id=9,
            run_key="run-abc",
            story_id="STORY-1",
            run_kind="implementation",
            trigger_source="task_queue",
            agent_class="claude",
            agent_role="implementer",
            artifact_summary_json=[],
            status="running",
        )

        response = self.client.post(
            "/v1/agent-runs",
            json={
                "task_id": 9,
                "story_id": "STORY-1",
                "run_kind": "implementation",
                "trigger_source": "task_queue",
                "agent_class": "claude",
                "agent_role": "implementer",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["run_key"], "run-abc")
        self.assertEqual(response.json()["run_kind"], "implementation")

    @patch("api.app.append_agent_run_artifact")
    def test_append_agent_run_artifact_endpoint_returns_updated_run(self, append_agent_run_artifact) -> None:
        append_agent_run_artifact.return_value = AgentRun(
            id=11,
            task_id=9,
            run_key="run-abc",
            agent_class="claude",
            agent_role="implementer",
            artifact_summary_json=[{"type": "verification"}],
            status="running",
        )

        response = self.client.post(
            "/v1/agent-runs/11/artifacts",
            json={"artifact": {"type": "verification"}},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["artifact_summary_json"][0]["type"], "verification")

    @patch("api.app.list_agent_runs")
    def test_list_agent_runs_endpoint_returns_runs(self, list_agent_runs) -> None:
        list_agent_runs.return_value = [
            AgentRun(
                id=11,
                task_id=9,
                run_key="run-abc",
                run_kind="implementation",
                trigger_source="task_queue",
                agent_class="claude",
                agent_role="implementer",
                status="running",
            )
        ]

        response = self.client.get(
            "/v1/agent-runs?task_id=9&status=running&limit=5",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["run_key"], "run-abc")
        list_agent_runs.assert_called_once_with(
            limit=5,
            task_id=9,
            run_kind=None,
            status="running",
            trigger_source=None,
        )

    @patch("api.app.list_briefings")
    def test_list_briefings_endpoint_returns_recent_briefings(self, list_briefings) -> None:
        list_briefings.return_value = [
            Briefing(
                id=5,
                scope="morning",
                headline="Morning briefing with 2 active attention item(s)",
                items_json=[{"headline": "Revenue risk"}],
                delivered_to="max",
            )
        ]

        response = self.client.get(
            "/v1/briefings?scope=morning&delivered_to=max&limit=5",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["scope"], "morning")
        list_briefings.assert_called_once_with(
            limit=5,
            scope="morning",
            delivered_to="max",
        )

    @patch("api.app.Thread")
    @patch("api.app._worker_run_lock")
    def test_run_worker_once_endpoint_starts_background_pass(self, worker_run_lock, thread_cls) -> None:
        worker_run_lock.acquire.return_value = True

        response = self.client.post(
            "/v1/worker/run-once",
            json={"worker_id": "studio-chief"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "started")
        thread_cls.return_value.start.assert_called_once()

    @patch("api.app._worker_run_lock")
    def test_run_worker_once_endpoint_reports_when_pass_is_already_running(self, worker_run_lock) -> None:
        worker_run_lock.acquire.return_value = False

        response = self.client.post(
            "/v1/worker/run-once",
            json={"worker_id": "studio-chief"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "already_running")

    def test_control_api_requires_bearer_token(self) -> None:
        response = self.client.get("/v1/attention")

        self.assertEqual(response.status_code, 401)

    def test_control_api_rejects_wrong_bearer_token(self) -> None:
        response = self.client.get("/v1/attention", headers={"Authorization": "Bearer wrong"})

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
