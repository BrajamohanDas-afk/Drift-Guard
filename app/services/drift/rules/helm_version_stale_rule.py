from __future__ import annotations

import re

from app.services.drift.rules.base import (
    BaseDriftRule,
    DriftAlertDraft,
    DriftRuleContext,
)


class HelmVersionStaleRule(BaseDriftRule):
    rule_type = "helm_version_stale"
    severity = "medium"
    _SEMVER_PATTERN = re.compile(
        r"^v?(?P<core>\d+(?:\.\d+){0,2})(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
    )

    def _parse_chart_value(self, value: str) -> tuple[str, str] | None:
        normalized = value.strip()
        if "@" not in normalized:
            return None
        chart_name, current_version = normalized.rsplit("@", 1)
        if not chart_name.strip() or not current_version.strip():
            return None
        return chart_name.strip(), current_version.strip()

    def _parse_version(
        self, version: str
    ) -> tuple[tuple[int, int, int], tuple[int | str, ...] | None] | None:
        normalized = version.strip()
        match = self._SEMVER_PATTERN.match(normalized)
        if match is None:
            return None

        core_parts = [int(part) for part in match.group("core").split(".")]
        while len(core_parts) < 3:
            core_parts.append(0)
        core = (core_parts[0], core_parts[1], core_parts[2])

        pre_release = match.group("pre")
        if pre_release is None:
            return core, None

        identifiers: list[int | str] = []
        for identifier in pre_release.split("."):
            if not identifier:
                return None
            if identifier.isdigit():
                identifiers.append(int(identifier))
            else:
                identifiers.append(identifier)
        return core, tuple(identifiers)

    def _compare_pre_release(
        self,
        current_pre_release: tuple[int | str, ...] | None,
        latest_pre_release: tuple[int | str, ...] | None,
    ) -> int:
        if current_pre_release is None and latest_pre_release is None:
            return 0
        if current_pre_release is None:
            return 1
        if latest_pre_release is None:
            return -1

        for current_identifier, latest_identifier in zip(
            current_pre_release, latest_pre_release
        ):
            if current_identifier == latest_identifier:
                continue

            current_is_int = isinstance(current_identifier, int)
            latest_is_int = isinstance(latest_identifier, int)
            if current_is_int and latest_is_int:
                return -1 if current_identifier < latest_identifier else 1
            if current_is_int and not latest_is_int:
                return -1
            if not current_is_int and latest_is_int:
                return 1
            return -1 if current_identifier < latest_identifier else 1

        if len(current_pre_release) == len(latest_pre_release):
            return 0
        return -1 if len(current_pre_release) < len(latest_pre_release) else 1

    def _compare_versions(self, current: str, latest: str) -> int | None:
        current_parsed = self._parse_version(current)
        latest_parsed = self._parse_version(latest)
        if current_parsed is None or latest_parsed is None:
            return None

        current_core, current_pre_release = current_parsed
        latest_core, latest_pre_release = latest_parsed
        if current_core != latest_core:
            return -1 if current_core < latest_core else 1
        return self._compare_pre_release(current_pre_release, latest_pre_release)

    def _is_stale(self, current: str, latest: str) -> bool:
        comparison = self._compare_versions(current, latest)
        if comparison is None:
            return False
        return comparison < 0

    def _latest_version_map(self, context: DriftRuleContext) -> dict[str, str]:
        raw = context.evidence.get("helm_latest_versions")
        if not isinstance(raw, dict):
            return {}

        version_map: dict[str, str] = {}
        for chart_name, latest_version in raw.items():
            normalized_chart = str(chart_name).strip()
            normalized_latest = str(latest_version).strip()
            if normalized_chart and normalized_latest:
                version_map[normalized_chart] = normalized_latest
        return version_map

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        chart_values = [
            str(entity.get("value", "")).strip()
            for entity in context.entities
            if str(entity.get("entity_type", "")).strip().lower() == "helm_chart"
            and str(entity.get("value", "")).strip()
        ]
        if not chart_values:
            return []

        latest_map = self._latest_version_map(context)
        if not latest_map:
            return []

        alerts: list[DriftAlertDraft] = []
        for chart_value in chart_values:
            parsed = self._parse_chart_value(chart_value)
            if parsed is None:
                continue

            chart_name, current_version = parsed
            latest_version = latest_map.get(chart_name)
            if latest_version is None:
                continue
            if not self._is_stale(current_version, latest_version):
                continue

            alerts.append(
                DriftAlertDraft(
                    rule_type=self.rule_type,
                    severity=self.severity,
                    message=(
                        f"Helm chart version is stale: {chart_name}@{current_version} "
                        f"(latest: {latest_version})"
                    ),
                    document_id=context.document_id,
                    evidence={
                        "chart": chart_name,
                        "current_version": current_version,
                        "latest_version": latest_version,
                    },
                )
            )

        return alerts
