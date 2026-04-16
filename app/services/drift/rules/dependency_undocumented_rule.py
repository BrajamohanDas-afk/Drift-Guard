from app.services.drift.rules.base import (
    BaseDriftRule,
    DriftAlertDraft,
    DriftRuleContext,
)


class DependencyUndocumentedRule(BaseDriftRule):
    rule_type = "dependency_undocumented"
    severity = "medium"
    _DOCUMENTED_ENTITY_TYPES = {"dependency", "service_dependency", "depends_on"}
    _OBSERVED_EVIDENCE_KEYS = ("observed_dependencies", "service_dependencies")

    def _normalize_dependency(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized.lower()

    def _extract_dependency_from_item(self, item: object) -> str | None:
        if isinstance(item, str):
            return self._normalize_dependency(item)

        if isinstance(item, dict):
            for key in ("dependency", "name", "service", "value"):
                if key in item:
                    dependency = self._normalize_dependency(item.get(key))
                    if dependency is not None:
                        return dependency
        return None

    def _documented_dependencies(self, context: DriftRuleContext) -> set[str]:
        documented: set[str] = set()
        for entity in context.entities:
            entity_type = str(entity.get("entity_type", "")).strip().lower()
            if entity_type not in self._DOCUMENTED_ENTITY_TYPES:
                continue

            dependency = self._normalize_dependency(entity.get("value", ""))
            if dependency is not None:
                documented.add(dependency)
        return documented

    def _observed_dependencies(self, context: DriftRuleContext) -> set[str]:
        observed: set[str] = set()
        for evidence_key in self._OBSERVED_EVIDENCE_KEYS:
            raw = context.evidence.get(evidence_key)
            if not isinstance(raw, list):
                continue

            for item in raw:
                dependency = self._extract_dependency_from_item(item)
                if dependency is not None:
                    observed.add(dependency)
        return observed

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        observed_dependencies = self._observed_dependencies(context)
        if not observed_dependencies:
            return []

        documented_dependencies = self._documented_dependencies(context)
        undocumented_dependencies = sorted(
            observed_dependencies - documented_dependencies
        )
        if not undocumented_dependencies:
            return []

        alerts: list[DriftAlertDraft] = []
        for dependency in undocumented_dependencies:
            alerts.append(
                DriftAlertDraft(
                    rule_type=self.rule_type,
                    severity=self.severity,
                    message=f"Undocumented dependency detected: {dependency}",
                    document_id=context.document_id,
                    evidence={
                        "dependency": dependency,
                        "documented_dependencies": sorted(documented_dependencies),
                    },
                )
            )
        return alerts
