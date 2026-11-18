"""Incremental guest migration: create only four new tables; never rewrite existing users/balances."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import get_engine
from app.models.guest import GuestIdentity, GuestLimitLock, GuestReservation, GuestEvent


def migrate(engine):
    for model in (GuestIdentity, GuestLimitLock, GuestReservation, GuestEvent):
        model.__table__.create(engine, checkfirst=True)


if __name__ == "__main__":
    migrate(get_engine())
    print("Guest tables ready; existing account balances unchanged.")
