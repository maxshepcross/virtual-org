"""Regression tests for Tempa sales deployment files and runbook coverage."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


class SalesDeployDocsTests(unittest.TestCase):
    def test_public_api_systemd_unit_runs_sales_public_api(self) -> None:
        unit = (ROOT / "deploy/systemd/virtual-org-sales-public-api.service").read_text()

        self.assertIn("User=virtual-org", unit)
        self.assertIn("EnvironmentFile=/opt/virtual-org/.env", unit)
        self.assertIn("scripts/run_sales_public_api.py", unit)
        self.assertIn("Restart=always", unit)
        self.assertIn("NoNewPrivileges=yes", unit)
        self.assertNotIn("ReadWritePaths=/opt/virtual-org", unit)

    def test_worker_systemd_unit_runs_loop_with_blocked_send_safety(self) -> None:
        unit = (ROOT / "deploy/systemd/virtual-org-sales-worker.service").read_text()

        self.assertIn("User=virtual-org", unit)
        self.assertNotIn("Environment=SALES_AGENT_ID=1", unit)
        self.assertIn("EnvironmentFile=/opt/virtual-org/.env", unit)
        self.assertIn("scripts/run_sales_worker.py --loop", unit)
        self.assertIn("--loop", unit)
        self.assertNotIn("--stop-on-blocked", unit)
        self.assertIn("NoNewPrivileges=yes", unit)
        self.assertNotIn("ReadWritePaths=/opt/virtual-org", unit)

    def test_sales_runbook_documents_safe_launch_and_emergency_stop(self) -> None:
        runbook = (ROOT / "docs/tempa-sales-agent-runbook.md").read_text()

        self.assertIn("SALES_SEND_MODE=dry_run", runbook)
        self.assertIn("SALES_KILL_SWITCH=true", runbook)
        self.assertIn("First Live Send", runbook)
        self.assertIn("Emergency Stop", runbook)
        self.assertIn("scripts/setup_db.py", runbook)
        self.assertIn("127.0.0.1:8091", runbook)
        self.assertIn("systemctl stop virtual-org-sales-worker", runbook)

    def test_main_production_runbook_links_sales_runbook(self) -> None:
        runbook = (ROOT / "docs/production-runbook.md").read_text()

        self.assertIn("virtual-org-sales-public-api", runbook)
        self.assertIn("virtual-org-sales-worker", runbook)
        self.assertIn("docs/tempa-sales-agent-runbook.md", runbook)


if __name__ == "__main__":
    unittest.main()
