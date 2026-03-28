import re

pattern = r'arn:aws:iam::[0-9]{12}:role/[a-zA-Z0-9+=,.@_/-]+'

def extract_iam_roles(text: str) -> list[str]:
    return re.findall(pattern, text)