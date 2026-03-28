from app.services.extraction.url_extractor import extract_urls
from app.services.extraction.dashboard_extractor import extract_dashboards
from app.services.extraction.service_extractor import extract_services
from app.services.extraction.owner_extractor import extract_owners
from app.services.extraction.command_extractor import extract_commands
from app.services.extraction.env_var_extractor import extract_env_vars
from app.services.extraction.iam_role_extractor import extract_iam_roles
from app.services.extraction.helm_chart_extractor import extract_helm_charts
from app.services.extraction.cluster_extractor import extract_clusters


# URL
def test_url_found():
    assert "https://grafana.internal/d/payments" in extract_urls("Check https://grafana.internal/d/payments here")

def test_url_not_found():
    assert extract_urls("no urls here") == []


# Dashboard
def test_dashboard_found():
    assert "grafana:payments-overview" in extract_dashboards("Monitor at grafana:payments-overview")

def test_dashboard_not_found():
    assert extract_dashboards("no dashboards here") == []


# Service
def test_service_found():
    assert "payments-api" in extract_services("restart payments-api now")

def test_service_not_found():
    assert extract_services("nothing here") == []


# Owner
def test_owner_at_found():
    assert "@alice" in extract_owners("Owner: @alice")

def test_owner_team_found():
    assert "team-platform" in extract_owners("Contact team-platform")

def test_owner_not_found():
    assert extract_owners("no owners here") == []


# Command
def test_command_with_prompt():
    assert "kubectl get pods" in extract_commands("$ kubectl get pods")
    
def test_command_not_found():
    assert extract_commands("no commands here") == []


# Env var
def test_env_var_found():
    assert "STRIPE_API_KEY" in extract_env_vars("Set STRIPE_API_KEY before running")

def test_env_var_not_found():
    assert extract_env_vars("no env vars here") == []


# IAM role
def test_iam_role_found():
    assert "arn:aws:iam::123456789012:role/deploy-role" in extract_iam_roles(
        "Use arn:aws:iam::123456789012:role/deploy-role"
    )
def test_iam_role_not_found():
    assert extract_iam_roles("no iam roles here") == []


# Helm chart
def test_helm_chart_found():
    assert "bitnami/postgresql@12.1.0" in extract_helm_charts("Deploy bitnami/postgresql@12.1.0")

def test_helm_chart_not_found():
    assert extract_helm_charts("no helm charts here") == []


# Cluster
def test_cluster_with_suffix():
    assert "prod-us-east-1-blue" in extract_clusters("Running on prod-us-east-1-blue")
    
def test_cluster_not_found():
    assert extract_clusters("no clusters here") == []