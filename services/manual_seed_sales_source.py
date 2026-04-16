"""Manual seed-list importer for the Tempa sales experiment."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from pydantic import BaseModel


class SeedProspect(BaseModel):
    email: str
    company_name: str
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    company_domain: str | None = None
    company_url: str | None = None
    country: str | None = "US"
    source_context_json: dict[str, Any] | None = None


REQUIRED_COLUMNS = {"email", "company_name"}


def parse_seed_csv(csv_text: str) -> list[SeedProspect]:
    """Parse a founder seed CSV into validated prospect inputs."""
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("Seed CSV is missing a header row.")
    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        raise ValueError(f"Seed CSV is missing required columns: {', '.join(sorted(missing))}.")

    prospects: list[SeedProspect] = []
    for index, row in enumerate(reader, start=2):
        email = (row.get("email") or "").strip()
        company_name = (row.get("company_name") or "").strip()
        if not email or "@" not in email:
            raise ValueError(f"Seed CSV row {index} has an invalid email.")
        if not company_name:
            raise ValueError(f"Seed CSV row {index} is missing company_name.")
        prospects.append(
            SeedProspect(
                email=email,
                company_name=company_name,
                first_name=(row.get("first_name") or "").strip() or None,
                last_name=(row.get("last_name") or "").strip() or None,
                title=(row.get("title") or "").strip() or None,
                company_domain=(row.get("company_domain") or "").strip().lower() or None,
                company_url=(row.get("company_url") or "").strip() or None,
                country=(row.get("country") or "US").strip().upper() or "US",
                source_context_json={"manual_seed_row": index},
            )
        )
    return prospects
