import re
from urllib.parse import urlparse

from app.services.drift.rules.base import (
    BaseDriftRule,
    DriftAlertDraft,
    DriftRuleContext,
)


class DashboardDeadRule(BaseDriftRule):
    rule_type = "dashboard_dead"
    severity = "medium"
    _DEAD_STATUSES = {"not_found", "collection_error", "dead"}

    def _normalize_url(self, value: str) -> str:
        raw = value.strip()
        if "://" not in raw:
            return raw

        parsed = urlparse(raw)
        host = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        normalized = f"{parsed.scheme.lower()}://{host}{path}"
        if parsed.query:
            normalized = f"{normalized}?{parsed.query}"
        return normalized

    def _is_dashboard_reference(self, value: str) -> bool:
        normalized = value.strip().lower()
        return normalized.startswith(("grafana:", "datadog:", "kibana:", "cloudwatch:"))

    def _ref_matches_target(self, dashboard_ref: str, target: str) -> bool:
        ref = dashboard_ref.strip()
        normalized_target = self._normalize_url(target)
        normalized_ref = self._normalize_url(ref)
        if normalized_ref == normalized_target:
            return True

        if self._is_dashboard_reference(ref):
            _, _, slug = ref.partition(":")
            slug = slug.strip().lower()
            if not slug:
                return False

            parsed_target = urlparse(normalized_target)
            path_segments = [
                segment.strip().lower()
                for segment in parsed_target.path.split("/")
                if segment.strip()
            ]
            if slug in path_segments:
                return True

            for segment in path_segments:
                tokens = [token for token in re.split(r"[^a-z0-9]+", segment) if token]
                if slug in tokens:
                    return True
            return False

        return False

    def _status_code_as_int(self, value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                return int(normalized)
            except ValueError:
                return None
        return None

    def _has_error(self, value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return bool(value)

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        dashboard_refs = [
            str(entity.get("value", "")).strip()
            for entity in context.entities
            if str(entity.get("entity_type", "")).strip().lower() == "dashboard"
            and str(entity.get("value", "")).strip()
        ]
        if not dashboard_refs:
            return []

        alerts: list[DriftAlertDraft] = []
        records = context.evidence.get("records")

        # Primary path: consume EvidenceStore payload shape.
        matched_records = 0
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, dict) or record.get("collector") != "http":
                    continue

                target = str(record.get("target", "")).strip()
                if not target:
                    continue

                matched_ref = next(
                    (
                        ref
                        for ref in dashboard_refs
                        if self._ref_matches_target(ref, target)
                    ),
                    None,
                )
                if matched_ref is None:
                    continue
                matched_records += 1

                status = str(record.get("status", "")).strip().lower()
                record_error = record.get("error")
                evidence_payload = (
                    record.get("evidence")
                    if isinstance(record.get("evidence"), dict)
                    else {}
                )
                status_code = self._status_code_as_int(
                    evidence_payload.get("status_code")
                )
                is_dead = (
                    status in self._DEAD_STATUSES
                    or self._has_error(record_error)
                    or (status_code is not None and status_code >= 400)
                )
                if not is_dead:
                    continue

                alerts.append(
                    DriftAlertDraft(
                        rule_type=self.rule_type,
                        severity=self.severity,
                        message=f"Dashboard URL appears unreachable: {target}",
                        document_id=context.document_id,
                        evidence={
                            "dashboard": matched_ref,
                            "target": target,
                            "http_status": status,
                            "status_code": status_code,
                            "error": record_error,
                        },
                    )
                )

            if matched_records > 0:
                return alerts

        # Fallback path for simplified evidence stubs.
        dashboard_health = (
            str(context.evidence.get("dashboard_http_status", "")).strip().lower()
        )
        if dashboard_health in self._DEAD_STATUSES:
            ref = dashboard_refs[0]
            return [
                DriftAlertDraft(
                    rule_type=self.rule_type,
                    severity=self.severity,
                    message=f"Dashboard URL appears unreachable: {ref}",
                    document_id=context.document_id,
                    evidence={
                        "dashboard": ref,
                        "dashboard_http_status": dashboard_health,
                    },
                )
            ]

        return []
