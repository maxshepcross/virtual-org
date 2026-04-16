"""Preview and unsubscribe token helpers for public sales pages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

from models.sales import (
    SalesPreviewToken,
    create_preview_token,
    get_latest_personalization_for_prospect,
    get_preview_token,
    get_prospect,
    mark_unsent_messages_for_prospect_status,
    record_suppression,
    transition_prospect_status,
)


class SalesPreviewService:
    def create_preview_token(self, prospect_id: int) -> tuple[str, SalesPreviewToken]:
        return create_preview_token(
            prospect_id=prospect_id,
            purpose="preview",
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )

    def create_unsubscribe_token(self, prospect_id: int) -> tuple[str, SalesPreviewToken]:
        return create_preview_token(prospect_id=prospect_id, purpose="unsubscribe", expires_at=None)

    def resolve_preview(self, raw_token: str) -> tuple[str, str]:
        token = get_preview_token(raw_token, purpose="preview")
        if not token:
            return "invalid", self._not_found_html()
        if token.status == "revoked":
            return "revoked", self._not_found_html()
        if token.expires_at and token.expires_at < datetime.now(timezone.utc):
            return "expired", self._expired_html()
        prospect = get_prospect(token.prospect_id)
        if not prospect:
            return "error", self._not_found_html()
        personalization = get_latest_personalization_for_prospect(prospect.id)
        if not personalization:
            return "error", self._not_found_html()
        return (
            "valid",
            self._strategy_html(prospect, personalization.strategy_json),
        )

    def unsubscribe(self, raw_token: str) -> bool:
        token = get_preview_token(raw_token, purpose="unsubscribe")
        if not token or token.status == "revoked":
            return False
        prospect = get_prospect(token.prospect_id)
        if not prospect:
            return False
        record_suppression(email=prospect.email, reason="unsubscribe", source="public")
        mark_unsent_messages_for_prospect_status(prospect.id, "skipped")
        if prospect.status != "unsubscribed":
            try:
                transition_prospect_status(
                    prospect.id,
                    "unsubscribed",
                    event_message="Prospect unsubscribed.",
                    event_details={"source": "public"},
                )
            except Exception:
                pass
        return True

    def _not_found_html(self) -> str:
        return "<!doctype html><html><body><h1>Page not found</h1></body></html>"

    def _expired_html(self) -> str:
        return "<!doctype html><html><body><h1>This preview has expired</h1></body></html>"

    def _strategy_html(self, prospect, strategy: dict) -> str:
        company = escape(prospect.company_name)
        first_name = escape(prospect.first_name or "there")
        observed = escape(str(strategy.get("observed_growth_context") or "A current growth signal stood out."))
        angle = escape(str(strategy.get("suggested_paid_social_angle") or "Test one clear paid-social angle."))
        audience = escape(str(strategy.get("target_audience") or "A focused buyer segment."))
        concept = escape(str(strategy.get("example_ad_concept") or "A simple creative test."))
        why_tempa = escape(str(strategy.get("why_tempa_can_help") or "Tempa can turn the idea into a small creative test."))
        confidence = strategy.get("confidence_score")
        confidence_text = escape(f"{float(confidence):.0%}") if isinstance(confidence, int | float) else "High"
        evidence_links = self._evidence_links(strategy.get("evidence_urls"))
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Tempa idea for {company}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172018;
      --muted: #5f6b61;
      --line: #d9e1d8;
      --surface: #f7faf6;
      --accent: #176b4d;
      --accent-2: #245f8f;
      --paper: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--surface);
      line-height: 1.5;
    }}
    main {{
      width: min(920px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0 56px;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 14px;
      font-weight: 700;
      margin: 0 0 12px;
      text-transform: uppercase;
    }}
    h1 {{
      font-size: 40px;
      line-height: 1.1;
      margin: 0 0 16px;
      letter-spacing: 0;
    }}
    .intro {{
      max-width: 680px;
      color: var(--muted);
      font-size: 18px;
      margin: 0 0 32px;
    }}
    .strategy {{
      display: grid;
      gap: 16px;
    }}
    section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
    }}
    h2 {{
      font-size: 18px;
      margin: 0 0 8px;
    }}
    p {{
      margin: 0;
    }}
    .pair {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .confidence {{
      color: var(--accent-2);
      font-weight: 700;
    }}
    ul {{
      margin: 8px 0 0;
      padding-left: 20px;
    }}
    a {{
      color: var(--accent-2);
      overflow-wrap: anywhere;
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100% - 24px, 920px); padding-top: 28px; }}
      h1 {{ font-size: 30px; }}
      .intro {{ font-size: 16px; }}
      .pair {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <p class="eyebrow">Private Tempa strategy</p>
    <h1>Paid social idea for {company}</h1>
    <p class="intro">Hi {first_name}, I put this together as a small, specific test I would run before scaling spend.</p>
    <div class="strategy">
      <section>
        <h2>What stood out</h2>
        <p>{observed}</p>
      </section>
      <div class="pair">
        <section>
          <h2>Audience</h2>
          <p>{audience}</p>
        </section>
        <section>
          <h2>Angle</h2>
          <p>{angle}</p>
        </section>
      </div>
      <section>
        <h2>Example ad concept</h2>
        <p>{concept}</p>
      </section>
      <section>
        <h2>Why Tempa can help</h2>
        <p>{why_tempa}</p>
      </section>
      <section>
        <h2>Confidence</h2>
        <p class="confidence">{confidence_text}</p>
      </section>
      <section>
        <h2>Evidence checked</h2>
        {evidence_links}
      </section>
    </div>
  </main>
</body>
</html>"""

    def _evidence_links(self, evidence_urls) -> str:
        if not isinstance(evidence_urls, list) or not evidence_urls:
            return "<p>No public evidence links were attached.</p>"
        items = []
        for url in evidence_urls:
            safe_url = escape(str(url), quote=True)
            if not safe_url.startswith("https://"):
                continue
            items.append(f'<li><a href="{safe_url}" rel="noreferrer noopener">{safe_url}</a></li>')
        if not items:
            return "<p>No public evidence links were attached.</p>"
        return f"<ul>{''.join(items)}</ul>"
