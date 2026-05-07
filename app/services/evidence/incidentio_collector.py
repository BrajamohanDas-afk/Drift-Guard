from datetime import datetime, timezone
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from app.config import settings

INCIDENTIO_API_BASE = "https://api.incident.io"


class IncidentIOServiceEvidence(BaseModel):
    query: str
    exists: bool
    entry_id: Optional[str] = None
    entry_name: Optional[str] = None
    catalog_type_id: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    permalink: Optional[str] = None
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncidentIOCollector:
    def __init__(
        self,
        api_token: Optional[str] = None,
        catalog_type_id: Optional[str] = None,
        timeout_seconds: float = 5.0,
    ):
        self.api_token = (
            settings.incidentio_api_token if api_token is None else api_token
        )
        self.catalog_type_id = (
            settings.incidentio_catalog_type_id
            if catalog_type_id is None
            else catalog_type_id
        )
        self.timeout_seconds = timeout_seconds

    def _find_exact_or_alias_match(
        self,
        entries: list[object],
        normalized_name: str,
    ) -> Optional[dict]:
        normalized_query = normalized_name.lower()
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            name = entry.get("name")
            if isinstance(name, str) and name.strip().lower() == normalized_query:
                return entry

            aliases = entry.get("aliases") or []
            if not isinstance(aliases, list):
                continue

            normalized_aliases = {
                alias.strip().lower()
                for alias in aliases
                if isinstance(alias, str)
            }
            if normalized_query in normalized_aliases:
                return entry

        return None

    def _next_page_cursor(self, payload: dict) -> Optional[str]:
        pagination_meta = payload.get("pagination_meta")
        if isinstance(pagination_meta, dict):
            for key in ("after", "next_after", "next_cursor", "cursor"):
                value = pagination_meta.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return None

    async def collect_service(self, service_name: str) -> IncidentIOServiceEvidence:
        checked_at = datetime.now(timezone.utc)
        normalized_name = service_name.strip()

        if not normalized_name:
            return IncidentIOServiceEvidence(
                query=service_name,
                exists=False,
                error="service_name must not be empty",
                checked_at=checked_at,
            )

        if not self.api_token:
            return IncidentIOServiceEvidence(
                query=service_name,
                exists=False,
                error="incident.io API token not configured",
                checked_at=checked_at,
            )

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }
        try:
            after: Optional[str] = None
            seen_cursors: set[str] = set()

            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
            ) as client:
                while True:
                    params: dict[str, str | int] = {
                        "identifier": normalized_name,
                        "page_size": 25,
                    }
                    if self.catalog_type_id:
                        params["catalog_type_id"] = self.catalog_type_id
                    if after:
                        params["after"] = after

                    response = await client.get(
                        f"{INCIDENTIO_API_BASE}/v3/catalog_entries",
                        headers=headers,
                        params=params,
                    )

                    if response.status_code == 401:
                        return IncidentIOServiceEvidence(
                            query=service_name,
                            exists=False,
                            error="Unauthorized: invalid incident.io API token",
                            checked_at=checked_at,
                        )

                    response.raise_for_status()
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        return IncidentIOServiceEvidence(
                            query=service_name,
                            exists=False,
                            error=f"Invalid incident.io JSON response: {exc}",
                            checked_at=checked_at,
                        )

                    if not isinstance(payload, dict):
                        return IncidentIOServiceEvidence(
                            query=service_name,
                            exists=False,
                            error="Invalid incident.io response shape: expected object",
                            checked_at=checked_at,
                        )

                    entries = payload.get("catalog_entries", [])
                    if not isinstance(entries, list):
                        return IncidentIOServiceEvidence(
                            query=service_name,
                            exists=False,
                            error=(
                                "Invalid incident.io response shape: "
                                "catalog_entries must be a list"
                            ),
                            checked_at=checked_at,
                        )

                    exact_match = self._find_exact_or_alias_match(
                        entries,
                        normalized_name,
                    )
                    if exact_match is not None:
                        aliases = [
                            alias
                            for alias in (exact_match.get("aliases") or [])
                            if isinstance(alias, str)
                        ]

                        return IncidentIOServiceEvidence(
                            query=service_name,
                            exists=True,
                            entry_id=exact_match.get("id"),
                            entry_name=exact_match.get("name"),
                            catalog_type_id=exact_match.get("catalog_type_id"),
                            aliases=aliases,
                            permalink=exact_match.get("permalink"),
                            error=None,
                            checked_at=checked_at,
                        )

                    next_cursor = self._next_page_cursor(payload)
                    if not next_cursor or next_cursor in seen_cursors:
                        break

                    seen_cursors.add(next_cursor)
                    after = next_cursor

            return IncidentIOServiceEvidence(
                query=service_name,
                exists=False,
                error=None,
                checked_at=checked_at,
            )
        except httpx.HTTPError as exc:
            return IncidentIOServiceEvidence(
                query=service_name,
                exists=False,
                error=str(exc),
                checked_at=checked_at,
            )
