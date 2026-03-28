import re

INLINE_COMMAND_PATTERN = re.compile(
    r"`((?:kubectl|helm|docker|aws|bash|sh|python|curl)\b[^`]*)`"
)

LINE_COMMAND_PATTERN = re.compile(
    r"^\s*(?:\$\s*)?((?:kubectl|helm|docker|aws|bash|sh|python|curl)\b.*)$",
    re.MULTILINE,
)

def extract_commands(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    commands: list[str] = []
    seen: set[str] = set()

    for pattern in (INLINE_COMMAND_PATTERN, LINE_COMMAND_PATTERN):
        for match in pattern.finditer(normalized):
            value = match.group(1).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            commands.append(value)

    return commands