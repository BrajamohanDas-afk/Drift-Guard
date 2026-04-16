import uuid

import pytest

from app.services.drift.rules import (
    CommandDeprecatedRule,
    DashboardDeadRule,
    DependencyUndocumentedRule,
    HelmVersionStaleRule,
    OwnerMissingRule,
)
from app.services.drift.rules.base import DriftRuleContext


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


def test_owner_missing_rule_triggers_when_owner_absent():
    rule = OwnerMissingRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "service", "value": "payments-api"},
            {"entity_type": "dashboard", "value": "https://grafana.example.com/d/payments"},
        ),
        evidence={},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "owner_missing"
    assert alerts[0].severity == "high"


def test_owner_missing_rule_no_alert_when_owner_present():
    rule = OwnerMissingRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "owner", "value": "@team-platform"},
            {"entity_type": "service", "value": "payments-api"},
        ),
        evidence={},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_owner_missing_rule_treats_blank_owner_as_missing():
    rule = OwnerMissingRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "owner", "value": "   "},
            {"entity_type": "service", "value": "payments-api"},
        ),
        evidence={},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "owner_missing"


def test_dashboard_dead_rule_triggers_on_http_404_from_evidence_store():
    url = "https://grafana.example.com/d/payments"
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": url},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": url,
                    "status": "found",
                    "error": None,
                    "evidence": {"status_code": 404},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "dashboard_dead"
    assert alerts[0].severity == "medium"
    assert alerts[0].evidence["dashboard"] == url
    assert alerts[0].evidence["target"] == url
    assert alerts[0].evidence["status_code"] == 404


def test_dashboard_dead_rule_no_alert_when_dashboard_is_healthy():
    url = "https://grafana.example.com/d/payments"
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": url},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": url,
                    "status": "found",
                    "error": None,
                    "evidence": {"status_code": 200},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_dashboard_dead_rule_matches_provider_style_dashboard_reference():
    dashboard_ref = "grafana:payments"
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": dashboard_ref},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": "https://grafana.example.com/d/payments",
                    "status": "not_found",
                    "error": None,
                    "evidence": {"status_code": 404},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].evidence["dashboard"] == dashboard_ref
    assert alerts[0].evidence["http_status"] == "not_found"


def test_dashboard_dead_rule_uses_fallback_when_records_have_no_dashboard_match():
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": "grafana:payments"},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": "https://status.example.com/health",
                    "status": "found",
                    "error": None,
                    "evidence": {"status_code": 200},
                }
            ],
            "dashboard_http_status": "dead",
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "dashboard_dead"
    assert alerts[0].evidence["dashboard_http_status"] == "dead"


def test_dashboard_dead_rule_triggers_on_record_error():
    url = "https://grafana.example.com/d/payments"
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": url},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": url,
                    "status": "found",
                    "error": "timeout",
                    "evidence": {"status_code": None},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].evidence["error"] == "timeout"


def test_dashboard_dead_rule_treats_numeric_string_status_code_as_dead():
    url = "https://grafana.example.com/d/payments"
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": url},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": url,
                    "status": "found",
                    "error": None,
                    "evidence": {"status_code": "404"},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].evidence["status_code"] == 404


def test_dashboard_dead_rule_ignores_blank_error_string():
    url = "https://grafana.example.com/d/payments"
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": url},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": url,
                    "status": "found",
                    "error": "  ",
                    "evidence": {"status_code": 200},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_dashboard_dead_rule_provider_slug_does_not_overmatch_substring():
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": "grafana:ops"},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": "https://grafana.example.com/d/devops-overview",
                    "status": "not_found",
                    "error": None,
                    "evidence": {"status_code": 404},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_dashboard_dead_rule_provider_slug_does_not_match_host_or_query_only():
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": "grafana:ops"},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": "https://ops.example.com/d/system?team=ops",
                    "status": "not_found",
                    "error": None,
                    "evidence": {"status_code": 404},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_dashboard_dead_rule_ignores_falsy_non_string_error_values():
    url = "https://grafana.example.com/d/payments"
    rule = DashboardDeadRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dashboard", "value": url},),
        evidence={
            "records": [
                {
                    "collector": "http",
                    "target": url,
                    "status": "found",
                    "error": 0,
                    "evidence": {"status_code": 200},
                }
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_command_deprecated_rule_triggers_with_exact_match():
    rule = CommandDeprecatedRule()
    command = "kubectl run nginx --image=nginx"
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "command", "value": command},),
        evidence={
            "command_deprecations": {
                command: {
                    "replacement": "kubectl create deployment nginx --image=nginx",
                    "reason": "kubectl run generators are deprecated",
                }
            }
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "command_deprecated"
    assert alerts[0].evidence["command"] == command
    assert "replacement" in alerts[0].evidence


def test_command_deprecated_rule_triggers_with_prefix_match():
    rule = CommandDeprecatedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "command", "value": "kubectl run api --image=api:1.0"},
        ),
        evidence={
            "command_deprecations": {"kubectl run": {"reason": "deprecated family"}}
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "command_deprecated"


def test_command_deprecated_rule_prefix_requires_token_boundary():
    rule = CommandDeprecatedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "command", "value": "kubectl runner --help"},),
        evidence={"command_deprecations": {"kubectl run": {"reason": "deprecated"}}},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_command_deprecated_rule_uses_longest_prefix_match():
    rule = CommandDeprecatedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "command", "value": "kubectl run job --image=nginx"},
        ),
        evidence={
            "command_deprecations": {
                "kubectl run": {"reason": "generic"},
                "kubectl run job": {"reason": "specific"},
            }
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].evidence["reason"] == "specific"


def test_command_deprecated_rule_no_alert_without_evidence():
    rule = CommandDeprecatedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "command", "value": "kubectl get pods"},),
        evidence={},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_command_deprecated_rule_skips_malformed_metadata():
    rule = CommandDeprecatedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "command", "value": "kubectl run api --image=api:1.0"},
        ),
        evidence={"command_deprecations": {"kubectl run": "deprecated"}},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_command_deprecated_rule_prefix_matches_shell_separator_boundaries():
    rule = CommandDeprecatedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "command", "value": "kubectl run;echo done"},),
        evidence={"command_deprecations": {"kubectl run": {"reason": "deprecated"}}},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "command_deprecated"


def test_helm_version_stale_rule_triggers_when_current_is_older():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "helm_chart", "value": "bitnami/postgresql@12.1.0"},),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "13.0.0"}},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "helm_version_stale"
    assert alerts[0].evidence["chart"] == "bitnami/postgresql"
    assert alerts[0].evidence["current_version"] == "12.1.0"
    assert alerts[0].evidence["latest_version"] == "13.0.0"


def test_helm_version_stale_rule_no_alert_when_up_to_date():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "helm_chart", "value": "bitnami/postgresql@13.0.0"},),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "13.0.0"}},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_helm_version_stale_rule_no_alert_without_latest_version_evidence():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "helm_chart", "value": "bitnami/postgresql@12.1.0"},),
        evidence={},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_helm_version_stale_rule_treats_shorthand_and_patch_equal():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "helm_chart", "value": "bitnami/postgresql@1.2"},),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "1.2.0"}},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_helm_version_stale_rule_marks_prerelease_as_older_than_release():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "helm_chart", "value": "bitnami/postgresql@1.2.0-rc.1"},
        ),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "1.2.0"}},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "helm_version_stale"


def test_helm_version_stale_rule_ignores_build_metadata_for_comparison():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "helm_chart", "value": "bitnami/postgresql@1.2.0+abc"},
        ),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "1.2.0+def"}},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_helm_version_stale_rule_uses_case_sensitive_prerelease_ordering():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "helm_chart", "value": "bitnami/postgresql@1.0.0-BETA"},
        ),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "1.0.0-alpha"}},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "helm_version_stale"


def test_helm_version_stale_rule_compares_numeric_prerelease_identifiers():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "helm_chart", "value": "bitnami/postgresql@1.2.0-rc.2"},
        ),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "1.2.0-rc.10"}},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "helm_version_stale"


def test_helm_version_stale_rule_compares_prerelease_identifier_length():
    rule = HelmVersionStaleRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "helm_chart", "value": "bitnami/postgresql@1.2.0-alpha"},
        ),
        evidence={"helm_latest_versions": {"bitnami/postgresql": "1.2.0-alpha.1"}},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "helm_version_stale"


def test_dependency_undocumented_rule_triggers_for_observed_undocumented_dependency():
    rule = DependencyUndocumentedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dependency", "value": "postgres"},),
        evidence={"observed_dependencies": ["postgres", "redis"]},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].rule_type == "dependency_undocumented"
    assert alerts[0].evidence["dependency"] == "redis"


def test_dependency_undocumented_rule_no_alert_when_all_observed_are_documented():
    rule = DependencyUndocumentedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(
            {"entity_type": "dependency", "value": "postgres"},
            {"entity_type": "service_dependency", "value": "redis"},
        ),
        evidence={"observed_dependencies": ["postgres", "redis"]},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_dependency_undocumented_rule_deduplicates_observed_values():
    rule = DependencyUndocumentedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dependency", "value": "postgres"},),
        evidence={"observed_dependencies": ["redis", "Redis", "redis"]},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].evidence["dependency"] == "redis"


def test_dependency_undocumented_rule_supports_dict_observed_payload_shape():
    rule = DependencyUndocumentedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "depends_on", "value": "postgres"},),
        evidence={
            "service_dependencies": [
                {"name": "postgres"},
                {"dependency": "redis"},
                {"service": "kafka"},
            ]
        },
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 2
    assert [alert.evidence["dependency"] for alert in alerts] == ["kafka", "redis"]


def test_dependency_undocumented_rule_no_alert_without_observed_dependencies():
    rule = DependencyUndocumentedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=({"entity_type": "dependency", "value": "postgres"},),
        evidence={},
    )

    alerts = rule.evaluate(context)

    assert alerts == []


def test_dependency_undocumented_rule_falls_back_when_primary_dict_key_is_blank():
    rule = DependencyUndocumentedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(),
        evidence={"service_dependencies": [{"dependency": " ", "name": "redis"}]},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].evidence["dependency"] == "redis"


def test_dependency_undocumented_rule_ignores_none_and_non_string_observed_values():
    rule = DependencyUndocumentedRule()
    context = DriftRuleContext(
        document_id=uuid.uuid4(),
        entities=(),
        evidence={"observed_dependencies": [None, 0, False, "redis"]},
    )

    alerts = rule.evaluate(context)

    assert len(alerts) == 1
    assert alerts[0].evidence["dependency"] == "redis"
