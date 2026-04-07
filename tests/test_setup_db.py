"""Regression tests for task schema setup."""

import unittest

from scripts.setup_db import SCHEMA_SQL


class SetupDbSchemaTests(unittest.TestCase):
    def test_schema_upgrades_existing_tasks_table_with_story_columns(self) -> None:
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_stories_json JSONB;", SCHEMA_SQL)
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_notes_json JSONB;", SCHEMA_SQL)
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verification_json JSONB;", SCHEMA_SQL)
        self.assertIn("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS current_story_id TEXT;", SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
