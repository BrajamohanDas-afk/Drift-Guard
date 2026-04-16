import uuid

import pytest

from app.services.drift.rules import DashboardDeadRule, OwnerMissingRule
from app.services.drift.rules.base import (
    BaseDriftRule,
    DriftAlertDraft,
    DriftRuleContext,
)
from app.services.drift.rules_engine import RulesEngine


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class InvalidReturnRule(BaseDriftRule):
    rule_type = "invalid_return"
    severity = "low"

    def evaluate(self, context: DriftRuleContext):  # type: ignore[override]
        return None


class RaisingRule(BaseDriftRule):
    rule_type = "raising_rule"
    severity = "low"

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        raise RuntimeError("rule exploded")


class DuplicateAlertRuleA(BaseDriftRule):
    rule_type = "duplicate_alert_a"
    severity = "low"

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        return [
            DriftAlertDraft(
                rule_type="shared_rule",
                severity="medium",
                message="same alert",
                document_id=context.document_id,
                evidence={"a": 1, "b": 2},
            )
        ]


class DuplicateAlertRuleB(BaseDriftRule):
    rule_type = "duplicate_alert_b"
    severity = "low"

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        return [
            DriftAlertDraft(
                rule_type="shared_rule",
                severity="medium",
                message="same alert",
                document_id=context.document_id,
                evidence={"b": 2, "a": 1},
            )
        ]


class DistinctAlertRule(BaseDriftRule):
    rule_type = "distinct_alert"
    severity = "low"

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        return [
            DriftAlertDraft(
                rule_type="shared_rule",
                severity="medium",
                message="same alert but distinct evidence",
                document_id=context.document_id,
                evidence={"a": 1, "b": 3},
            )
        ]


class SetEvidenceRuleA(BaseDriftRule):
    rule_type = "set_evidence_rule_a"
    severity = "low"

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        return [
            DriftAlertDraft(
                rule_type="set_alert",
                severity="low",
                message="set evidence",
                document_id=context.document_id,
                evidence={"members": {1, 2, 3}},
            )
        ]


class SetEvidenceRuleB(BaseDriftRule):
    rule_type = "set_evidence_rule_b"
    severity = "low"

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        return [
            DriftAlertDraft(
                rule_type="set_alert",
                severity="low",
                message="set evidence",
                document_id=context.document_id,
                evidence={"members": {3, 2, 1}},
            )
        ]


def test_base_rule_is_abstract():
    with pytest.raises(TypeError):
        BaseDriftRule()  # type: ignore[abstract]


def test_base_rule_requires_rule_type():
    with pytest.raises(TypeError):

        class MissingRuleType(BaseDriftRule):
            severity = "high"

            def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
                return []


def test_base_rule_requires_valid_severity():
    with pytest.raises(TypeError):

        class InvalidSeverity(BaseDriftRule):
            rule_type = "invalid_severity"
            severity = "urgent"

            def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
                return []


def test_context_uses_immutable_payload_views():
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=[{"entity_type": "owner", "value": "@team-platform"}],
        evidence={"dashboard_http_status": "found"},
    )

    with pytest.raises(TypeError):
        context.evidence["new_key"] = "blocked"  # type: ignore[index]

    with pytest.raises(TypeError):
        context.entities[0]["value"] = "@team-other"  # type: ignore[index]


def test_rules_engine_returns_empty_when_rules_do_not_trigger():
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=[{"entity_type": "owner", "value": "@team-platform"}],
        evidence={"dashboard_http_status": "found"},
    )
    engine = RulesEngine(rules=[OwnerMissingRule(), DashboardDeadRule()])

    alerts = engine.evaluate(context)

    assert alerts == []


def test_rules_engine_handles_none_document_id_and_default_payloads():
    context = DriftRuleContext(document_id=None)
    engine = RulesEngine(rules=[OwnerMissingRule()])

    alerts = engine.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].document_id is None
    assert alerts[0].rule_type == "owner_missing"
    assert alerts[0].severity == "high"
    assert alerts[0].evidence == {"missing_entity_type": "owner"}


def test_rules_engine_collects_alerts_from_multiple_rules():
    document_id = uuid.uuid4()
    context = DriftRuleContext(
        document_id=document_id,
        entities=[{"entity_type": "dashboard", "value": "https://grafana.example.com/d/payments"}],
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": "https://grafana.example.com/d/payments",
                    "status": "found",
                    "error": None,
                    "evidence": {"status_code": 404},
                }
            ]
        },
    )
    engine = RulesEngine(rules=[OwnerMissingRule(), DashboardDeadRule()])

    alerts = engine.evaluate(context)

    assert len(alerts) == 2
    # Engine preserves rule registration order.
    assert [alert.rule_type for alert in alerts] == ["owner_missing", "dashboard_dead"]
    assert all(alert.document_id == document_id for alert in alerts)
    assert alerts[0].severity == "high"
    assert alerts[0].message == "Owner is missing from runbook metadata"
    assert alerts[0].evidence == {"missing_entity_type": "owner"}
    assert alerts[1].severity == "medium"
    assert "Dashboard URL appears unreachable" in alerts[1].message
    assert alerts[1].evidence["dashboard"] == "https://grafana.example.com/d/payments"


def test_rules_engine_rejects_invalid_rule_return_shape():
    context = DriftRuleContext(document_id=uuid.uuid4())
    engine = RulesEngine(rules=[InvalidReturnRule()])

    with pytest.raises(TypeError):
        engine.evaluate(context)


def test_rules_engine_is_fail_fast_on_rule_exception():
    context = DriftRuleContext(document_id=uuid.uuid4())
    engine = RulesEngine(rules=[RaisingRule(), OwnerMissingRule()])

    with pytest.raises(RuntimeError):
        engine.evaluate(context)


def test_rules_engine_deduplicates_identical_alerts_across_rules():
    context = DriftRuleContext(document_id=uuid.uuid4())
    engine = RulesEngine(rules=[DuplicateAlertRuleA(), DuplicateAlertRuleB()])

    alerts = engine.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "shared_rule"
    assert alerts[0].message == "same alert"


def test_rules_engine_keeps_distinct_alerts():
    context = DriftRuleContext(document_id=uuid.uuid4())
    engine = RulesEngine(
        rules=[DuplicateAlertRuleA(), DuplicateAlertRuleB(), DistinctAlertRule()]
    )

    alerts = engine.evaluate(context)

    assert len(alerts) == 2
    assert alerts[0].message == "same alert"
    assert alerts[1].message == "same alert but distinct evidence"


def test_rules_engine_deduplicates_set_evidence_with_different_orderings():
    context = DriftRuleContext(document_id=uuid.uuid4())
    engine = RulesEngine(rules=[SetEvidenceRuleA(), SetEvidenceRuleB()])

    alerts = engine.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "set_alert"
