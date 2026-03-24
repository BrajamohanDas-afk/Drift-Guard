from app.services.extraction.url_extractor import extract_urls
from app.services.extraction.service_extractor import extract_services
from app.services.extraction.owner_extractor import extract_owners
from app.services.extraction.iam_role_extractor import extract_iam_roles
from app.services.extraction.helm_chart_extractor import extract_helm_charts
from app.services.extraction.env_var_extractor import extract_env_vars
from app.services.extraction.dashboard_extractor import extract_dashboards
from app.services.extraction.command_extractor import extract_commands
from app.services.extraction.cluster_extractor import extract_clusters


class EntityExtractor:
    def extract(self, text: str) -> list[dict]:
        entities = []
        
        # call url extractor
        for url in extract_urls(text):
            entities.append({
                "entity_type": "url",
                "value": url,
                "context": ""
            })
            
        # dashboards → entity_type = "dashboard"
        for dashboard in extract_dashboards(text):
            entities.append({
                "entity_type": "dashboard",
                "value": dashboard,
                "context": ""
            })
            
        # services → entity_type = "service"
        for service in extract_services(text):
            entities.append({
                "entity_type": "service",
                "value": service,
                "context": ""
            })
            
        # owners → entity_type = "owner"
        for owner in extract_owners(text):
            entities.append({
                "entity_type": "owner",
                "value": owner,
                "context": ""
            })
            
        # commands → entity_type = "command"
        for command in extract_commands(text):
            entities.append({
                "entity_type": "command",
                "value": command,
                "context": ""
            })
            
        # env_vars → entity_type = "env_var"
        for env_var in extract_env_vars(text):
            entities.append({
                "entity_type": "env_var",
                "value": env_var,
                "context": ""
            })
            
        # iam_roles → entity_type = "iam_role"
        for iam_role in extract_iam_roles(text):
            entities.append({
                "entity_type": "iam_role",
                "value": iam_role,
                "context": ""
            })
            
        # helm_charts → entity_type = "helm_chart"
        for helm_chart in extract_helm_charts(text):
            entities.append({
                "entity_type": "helm_chart",
                "value": helm_chart,
                "context": ""
            })
            
        # clusters → entity_type = "cluster"
        for cluster in extract_clusters(text):
            entities.append({
                "entity_type": "cluster",
                "value": cluster,
                "context": ""
            })
        
        return entities
        