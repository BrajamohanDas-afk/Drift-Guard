from app.services.extraction.cluster_extractor import extract_clusters
from app.services.extraction.command_extractor import extract_commands
from app.services.extraction.dashboard_extractor import extract_dashboards
from app.services.extraction.dependency_extractor import extract_dependencies
from app.services.extraction.env_var_extractor import extract_env_vars
from app.services.extraction.helm_chart_extractor import extract_helm_charts
from app.services.extraction.iam_role_extractor import extract_iam_roles
from app.services.extraction.owner_extractor import extract_owners
from app.services.extraction.service_extractor import extract_services
from app.services.extraction.url_extractor import extract_urls


class EntityExtractor:
    def extract(self, text: str) -> list[dict]:
        entities = []

        for url in extract_urls(text):
            entities.append({"entity_type": "url", "value": url, "context": ""})

        for dashboard in extract_dashboards(text):
            entities.append(
                {"entity_type": "dashboard", "value": dashboard, "context": ""}
            )

        for service in extract_services(text):
            entities.append(
                {"entity_type": "service", "value": service, "context": ""}
            )

        for dependency in extract_dependencies(text):
            entities.append(
                {"entity_type": "dependency", "value": dependency, "context": ""}
            )

        for owner in extract_owners(text):
            entities.append({"entity_type": "owner", "value": owner, "context": ""})

        for command in extract_commands(text):
            entities.append(
                {"entity_type": "command", "value": command, "context": ""}
            )

        for env_var in extract_env_vars(text):
            entities.append(
                {"entity_type": "env_var", "value": env_var, "context": ""}
            )

        for iam_role in extract_iam_roles(text):
            entities.append(
                {"entity_type": "iam_role", "value": iam_role, "context": ""}
            )

        for helm_chart in extract_helm_charts(text):
            entities.append(
                {"entity_type": "helm_chart", "value": helm_chart, "context": ""}
            )

        for cluster in extract_clusters(text):
            entities.append(
                {"entity_type": "cluster", "value": cluster, "context": ""}
            )

        return entities
