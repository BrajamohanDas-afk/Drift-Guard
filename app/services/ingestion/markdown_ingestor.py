import markdown
import re

def strip_markdown(text: str) -> str:
    # convert markdown to html
    html = markdown.markdown(text)
    # strip html tags
    clean = re.sub(r'<[^>]+>', '', html)
    # normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

class MarkdownIngestor:
    def normalize(self, text: str) -> str:
        return strip_markdown(text)