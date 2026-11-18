from datetime import datetime, timezone


def utc_naive_now() -> datetime:
    """UTC for the guest tables' timezone-naive SQL DATETIME columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
