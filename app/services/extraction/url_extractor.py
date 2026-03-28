import re

def extract_urls(text: str) -> list[str]:
    raw = re.findall(r'https?://[^\s<>"\')\]]+', text)
    # strip trailing punctuation that isn't part of the URL
    cleaned = [url.rstrip('.,;:!?)>') for url in raw]
    return cleaned