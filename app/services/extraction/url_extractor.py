import re

pattern = r'https?://[^\s]+'

def extract_urls(text: str) -> list[str]:
    return re.findall(pattern, text)