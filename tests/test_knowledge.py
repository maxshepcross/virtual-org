"""Tests for reusable workflow recipes and shared memory helpers."""

import unittest
from unittest.mock import patch

from models.knowledge import (
    MemoryEntry,
    WorkflowRecipe,
    build_reusable_context,
    create_task_from_workflow_recipe,
    create_workflow_recipe,
    upsert_memory_entry,
)
from models.task import Task


class KnowledgeModelTests(unittest.TestCase):
    @patch("models.knowledge._conn")
    @patch("models.knowledge.create_task")
    @patch("models.knowledge.get_workflow_recipe")
    def test_create_task_from_workflow_recipe_renders_templates(
        self,
        get_workflow_recipe_mock,
        create_task_mock,
        conn_factory,
    ) -> None:
        get_workflow_recipe_mock.return_value = WorkflowRecipe(
            slug="founder-brief",
            title="Founder brief",
            summary="Turn notes into a concise brief.",
            category="ops",
            target_repo="studio/control",
            venture="virtual-org",
            task_title_template="Write brief for {company}",
            task_description_template="Summarize this request:\n{request}",
        )
        create_task_mock.return_value = Task(
            id=12,
            title="Write brief for Acme",
            description="Summarize this request:\nUse the latest notes",
            category="ops",
            target_repo="studio/control",
            venture="virtual-org",
        )

        task = create_task_from_workflow_recipe(
            "founder-brief",
            request="Use the latest notes",
            variables={"company": "Acme"},
            requested_by="max",
        )

        self.assertEqual(task.id, 12)
        create_task_mock.assert_called_once_with(
            idea_id=None,
            title="Write brief for Acme",
            description="Summarize this request:\nUse the latest notes",
            category="ops",
            target_repo="studio/control",
            venture="virtual-org",
            requested_by="max",
            slack_channel_id=None,
            slack_thread_ts=None,
        )
        conn_factory.return_value.cursor.return_value.__enter__.return_value.execute.assert_called_once()

    @patch("models.knowledge._conn", side_effect=RuntimeError("timestamp update failed"))
    @patch("models.knowledge.create_task")
    @patch("models.knowledge.get_workflow_recipe")
    def test_create_task_from_workflow_recipe_ignores_last_used_timestamp_failure(
        self,
        get_workflow_recipe_mock,
        create_task_mock,
        _conn_mock,
    ) -> None:
        get_workflow_recipe_mock.return_value = WorkflowRecipe(
            slug="founder-brief",
            title="Founder brief",
            summary="Turn notes into a concise brief.",
            category="ops",
            target_repo="studio/control",
            venture="virtual-org",
            task_title_template="Write brief",
            task_description_template="{request}",
        )
        create_task_mock.return_value = Task(
            id=12,
            title="Write brief",
            description="Use the latest notes",
            category="ops",
            target_repo="studio/control",
            venture="virtual-org",
        )

        task = create_task_from_workflow_recipe("founder-brief", request="Use the latest notes")

        self.assertEqual(task.id, 12)
        create_task_mock.assert_called_once()

    @patch("models.knowledge.list_memory_entries")
    @patch("models.knowledge.list_workflow_recipes")
    def test_build_reusable_context_prefers_matching_items(
        self,
        list_workflow_recipes_mock,
        list_memory_entries_mock,
    ) -> None:
        list_workflow_recipes_mock.return_value = [
            WorkflowRecipe(
                slug="spec-review",
                title="Spec review",
                summary="Turn a rough ask into a plan.",
                category="ops",
                target_repo="studio/control",
                task_title_template="Review {request}",
                task_description_template="{request}",
                tags_json=["planning", "brief"],
            ),
            WorkflowRecipe(
                slug="other-recipe",
                title="Unrelated feature",
                summary="Something else.",
                category="feature",
                target_repo="other/repo",
                task_title_template="Do it",
                task_description_template="Do it",
            ),
        ]
        list_memory_entries_mock.return_value = [
            MemoryEntry(
                kind="decision",
                title="Use story breakdowns",
                body="Break founder requests into small execution stories before coding.",
                target_repo="studio/control",
                tags_json=["planning"],
            ),
            MemoryEntry(
                kind="note",
                title="Unrelated note",
                body="Nothing to do with this task.",
                target_repo="other/repo",
            ),
        ]

        context = build_reusable_context(
            Task(
                title="Plan founder request",
                description="Need a short plan with execution stories",
                category="ops",
                target_repo="studio/control",
            )
        )

        self.assertIn("spec-review", context["workflow_context"])
        self.assertIn("Use story breakdowns", context["memory_context"])
        self.assertNotIn("other-recipe", context["workflow_context"])

    @patch("models.knowledge.list_memory_entries")
    @patch("models.knowledge.list_workflow_recipes")
    def test_build_reusable_context_skips_unscoped_tasks(
        self,
        list_workflow_recipes_mock,
        list_memory_entries_mock,
    ) -> None:
        context = build_reusable_context(
            Task(
                title="Plan founder request",
                description="Need a short plan",
                category="ops",
            )
        )

        self.assertEqual(context, {"workflow_context": "", "memory_context": ""})
        list_workflow_recipes_mock.assert_not_called()
        list_memory_entries_mock.assert_not_called()

    def test_create_workflow_recipe_rejects_malformed_templates(self) -> None:
        with self.assertRaises(ValueError):
            create_workflow_recipe(
                slug="bad-template",
                title="Bad template",
                summary="This should fail.",
                category="ops",
                task_title_template="{request",
            )

    def test_create_workflow_recipe_rejects_attribute_access_templates(self) -> None:
        with self.assertRaises(ValueError):
            create_workflow_recipe(
                slug="bad-template",
                title="Bad template",
                summary="This should fail.",
                category="ops",
                task_title_template="{request.__class__}",
            )

    def test_memory_entries_reject_oversized_body(self) -> None:
        with self.assertRaises(ValueError):
            upsert_memory_entry(
                kind="decision",
                title="Too large",
                body="x" * 4001,
            )


if __name__ == "__main__":
    unittest.main()
