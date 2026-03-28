import re

pattern = r'(?:prod|staging|dev)-[a-z]+-[a-z]+-[0-9]+(?:-[a-z0-9]+)*'

def extract_clusters(text: str) -> list[str]:
    return re.findall(pattern, text)