import re

DEPENDENCY_LABEL_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?"
    r"(?:dependencies|depends on|requires|uses|calls|"
    r"upstream services?|downstream services?|service dependencies?)"
    r"\s*[:\-]\s*(?P<values>.+)$"
)
INLINE_DEPENDENCY_RE = re.compile(
    r"(?i)\b(?:depends on|requires|calls|uses)\s+"
    r"(?P<values>[a-z][a-z0-9_.-]*(?:\s*(?:,|and)\s*[a-z][a-z0-9_.-]*)*)"
)
DEPENDENCY_TOKEN_RE = re.compile(r"\b[a-z][a-z0-9_.-]{1,63}\b")
STOP_WORDS = {
    "and",
    "dependency",
    "dependencies",
    "downstream",
    "service",
    "services",
    "upstream",
}


def _extract_tokens(value_text: str) -> list[str]:
    dependencies: list[str] = []
    seen: set[str] = set()
    for match in DEPENDENCY_TOKEN_RE.finditer(value_text):
        value = match.group(0).strip(".,;:").lower()
        if value in STOP_WORDS or value in seen:
            continue
        seen.add(value)
        dependencies.append(value)
    return dependencies


def extract_dependencies(text: str) -> list[str]:
    dependencies: list[str] = []
    seen: set[str] = set()

    for pattern in (DEPENDENCY_LABEL_RE, INLINE_DEPENDENCY_RE):
        for match in pattern.finditer(text):
            for dependency in _extract_tokens(match.group("values")):
                if dependency in seen:
                    continue
                seen.add(dependency)
                dependencies.append(dependency)

    return dependencies
