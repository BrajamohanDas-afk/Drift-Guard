import re

pattern = r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"

def extract_env_vars(text: str) -> list[str]:
    return re.findall(pattern, text)