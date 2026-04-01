from datetime import datetime, timezone
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from app.config import settings


PAGERDUTY_API_BASE = "https://api.pagerduty.com"
PAGERDUTY_ACCEPT_HEADER = "application/vnd.pagerduty+json;version=2"


class PagerDutyServiceEvidence(BaseModel):
    query: str
    exists: bool
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    escalation_policy_id: Optional[str] = None
    html_url: Optional[str] = None
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PagerDutyCollector:
    def __init__(self, api_token: Optional[str] = None, timeout_seconds: float = 5.0):
        self.api_token = settings.pagerduty_api_token if api_token is None else api_token
        self.timeout_seconds = timeout_seconds

    async def collect_service(self, service_name: str) -> PagerDutyServiceEvidence:
        checked_at = datetime.now(timezone.utc)
        
        if not service_name.strip():
            return PagerDutyServiceEvidence(
                query=service_name,
                exists=False,
                error="service_name must not be empty",
                checked_at=checked_at,
            )


        if not self.api_token:
            return PagerDutyServiceEvidence(
                query=service_name,
                exists=False,
                error="PagerDuty API token not configured",
                checked_at=checked_at,
            )

        headers = {
            "Authorization": f"Token token={self.api_token}",
            "Accept": PAGERDUTY_ACCEPT_HEADER,
        }

        params = {
            "query": service_name,
            "limit": 25,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    f"{PAGERDUTY_API_BASE}/services",
                    headers=headers,
                    params=params,
                )

            if response.status_code == 401:
                return PagerDutyServiceEvidence(
                    query=service_name,
                    exists=False,
                    error="Unauthorized: invalid PagerDuty API token",
                    checked_at=checked_at,
                )

            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                return PagerDutyServiceEvidence(
                    query=service_name,
                    exists=False,
                    error=f"Invalid PagerDuty JSON response: {exc}",
                    checked_at=checked_at,
                )
            services = payload.get("services", [])

            exact_match = next(
                (
                    service
                    for service in services
                    if service.get("name", "").strip().lower()
                    == service_name.strip().lower()
                ),
                None,
            )

            if exact_match is None:
                return PagerDutyServiceEvidence(
                    query=service_name,
                    exists=False,
                    error=None,
                    checked_at=checked_at,
                )

            escalation_policy = exact_match.get("escalation_policy") or {}

            return PagerDutyServiceEvidence(
                query=service_name,
                exists=True,
                service_id=exact_match.get("id"),
                service_name=exact_match.get("name"),
                escalation_policy_id=escalation_policy.get("id"),
                html_url=exact_match.get("html_url"),
                error=None,
                checked_at=checked_at,
            )

        except httpx.HTTPError as exc:
            return PagerDutyServiceEvidence(
                query=service_name,
                exists=False,
                error=str(exc),
                checked_at=checked_at,
            )
