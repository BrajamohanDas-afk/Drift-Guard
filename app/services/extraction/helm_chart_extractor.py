import re

pattern = r'[a-zA-Z0-9-]+/[a-zA-Z0-9-]+@\d+(?:\.\d+)*'

def extract_helm_charts(text: str) -> list[str]:
    return re.findall(pattern,text)