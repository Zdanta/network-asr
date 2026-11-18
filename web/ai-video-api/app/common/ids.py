import secrets
from datetime import datetime


def generate_biz_no(prefix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_hex(4).upper()
    return f"{prefix}{timestamp}{suffix}"
