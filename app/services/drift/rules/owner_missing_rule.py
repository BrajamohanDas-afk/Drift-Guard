from app.services.drift.rules.base import (
    BaseDriftRule,
    DriftAlertDraft,
    DriftRuleContext,
)


class OwnerMissingRule(BaseDriftRule):
    rule_type = "owner_missing"
    severity = "high"

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        has_owner = any(
            str(entity.get("entity_type", "")).strip().lower() == "owner"
            and isinstance(entity.get("value"), str)
            and entity.get("value", "").strip()
            for entity in context.entities
        )
        if has_owner:
            return []

        return [
            DriftAlertDraft(
                rule_type=self.rule_type,
                severity=self.severity,
                message="Owner is missing from runbook metadata",
                document_id=context.document_id,
                evidence={"missing_entity_type": "owner"},
            )
        ]
