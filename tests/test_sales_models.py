"""Tests for sales model helpers."""

import unittest
from unittest.mock import patch

from models.sales import claim_next_ready_message, hash_email, hash_token, normalize_email, redact_email


class _FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql, params) -> None:
        self.sql = sql
        self.params = params

    def fetchone(self):
        return None


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


class SalesModelHelperTests(unittest.TestCase):
    def test_email_hash_normalizes_case_and_spaces(self) -> None:
        self.assertEqual(hash_email(" Founder@Example.COM "), hash_email("founder@example.com"))

    def test_token_hash_does_not_normalize(self) -> None:
        self.assertNotEqual(hash_token("ABC"), hash_token("abc"))

    def test_redact_email_keeps_domain_for_debugging(self) -> None:
        self.assertEqual(redact_email("max@example.com"), "ma***@example.com")
        self.assertEqual(normalize_email(" A@B.COM "), "a@b.com")

    def test_claim_next_ready_message_only_locks_active_sender(self) -> None:
        cursor = _FakeCursor()
        conn = _FakeConnection(cursor)

        with patch("models.sales._conn", return_value=conn):
            result = claim_next_ready_message(agent_id=1, sender_account_id=2, sender_daily_cap=10)

        self.assertIsNone(result)
        self.assertIn("status = 'active'", cursor.sql)
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
