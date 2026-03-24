import re

pattern = r'(?:grafana|datadog|kibana|cloudwatch):[a-zA-Z0-9_-]+'

def extract_dashboards(text: str) -> list[str]:
    return re.findall(pattern,text)