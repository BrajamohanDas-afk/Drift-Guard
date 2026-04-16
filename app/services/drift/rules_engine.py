import json
import uuid
from collections.abc import Sequence
from datetime import date, datetime, time

from app.services.drift.rules.base import (
    BaseDriftRule,
    DriftAlertDraft,
    DriftRuleContext,
)


class RulesEngine:
    def __init__(self, rules: Sequence[BaseDriftRule]):
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[BaseDriftRule, ...]:
        return self._rules

    def _normalize_evidence_value(self, value: object) -> object:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): self._normalize_evidence_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [self._normalize_evidence_value(item) for item in value]
        if isinstance(value, (set, frozenset)):
            normalized_items = [self._normalize_evidence_value(item) for item in value]
            return sorted(
                normalized_items,
                key=lambda item: json.dumps(
                    item, sort_keys=True, separators=(",", ":")
                ),
            )
        return {"__python_repr__": repr(value), "__python_type__": type(value).__name__}

    def _alert_fingerprint(
        self, alert: DriftAlertDraft
    ) -> tuple[str, str, str, str, str]:
        normalized_evidence = self._normalize_evidence_value(alert.evidence)
        return (
            alert.rule_type,
            alert.severity,
            alert.message,
            str(alert.document_id),
            json.dumps(
                normalized_evidence,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def _deduplicate_alerts(
        self, alerts: list[DriftAlertDraft]
    ) -> list[DriftAlertDraft]:
        seen: set[tuple[str, str, str, str, str]] = set()
        deduplicated: list[DriftAlertDraft] = []
        for alert in alerts:
            fingerprint = self._alert_fingerprint(alert)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduplicated.append(alert)
        return deduplicated

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        alerts: list[DriftAlertDraft] = []
        for rule in self._rules:
            rule_alerts = rule.evaluate(context)
            if not isinstance(rule_alerts, list):
                raise TypeError(
                    (
                        f"{rule.__class__.__name__}.evaluate must return "
                        "list[DriftAlertDraft]"
                    )
                )
            if not all(isinstance(alert, DriftAlertDraft) for alert in rule_alerts):
                raise TypeError(
                    (
                        f"{rule.__class__.__name__}.evaluate returned "
                        "non-DriftAlertDraft entries"
                    )
                )
            alerts.extend(rule_alerts)
        return self._deduplicate_alerts(alerts)
