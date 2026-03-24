import re

pattern = r'\b[a-z][a-z0-9-]*(?:api|service|worker|job|consumer)\b'

def extract_services(text: str) -> list[str]:
    return re.findall(pattern,text)