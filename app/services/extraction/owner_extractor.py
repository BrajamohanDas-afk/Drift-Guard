import re

pattern = r'(?<![a-zA-Z0-9._%+-])@[a-zA-Z0-9_]+(?!\.[a-zA-Z])|team-[a-zA-Z0-9_-]+'

def extract_owners(text: str) -> list[str]:
    return re.findall(pattern, text)