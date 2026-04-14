"""Regression tests for task schema setup."""

import unittest

from scripts.setup_db import SCHEMA_SQL


class SetupDbSchemaTests(unittest.TestCase):
    def test_schema_upgrades_existing_tasks_table_with_story_columns(self) -> None:
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_stories_json JSONB;", SCHEMA_SQL)
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_notes_json JSONB;", SCHEMA_SQL)
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verification_json JSONB;", SCHEMA_SQL)
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS current_story_id TEXT;", SCHEMA_SQL)

    def test_schema_creates_control_plane_tables(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS agent_runs", SCHEMA_SQL)
        self.assertIn("run_key         TEXT NOT NULL", SCHEMA_SQL)
        self.assertIn("artifact_summary_json JSONB NOT NULL DEFAULT '[]'::JSONB", SCHEMA_SQL)
        self.assertIn("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS run_kind TEXT NOT NULL DEFAULT 'interactive';", SCHEMA_SQL)
        self.assertIn("ALTER TABLE agent_runs ALTER COLUMN run_key SET NOT NULL;", SCHEMA_SQL)
        self.assertIn("ALTER TABLE signals ADD COLUMN IF NOT EXISTS agent_run_id BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL;", SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS signals", SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS attention_items", SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS approval_requests", SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_decisions", SCHEMA_SQL)

    def test_schema_creates_reusable_workflow_and_memory_tables(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS workflow_recipes", SCHEMA_SQL)
        self.assertIn("slug            TEXT NOT NULL UNIQUE", SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS memory_entries", SCHEMA_SQL)
        self.assertIn("source_key      TEXT UNIQUE", SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
