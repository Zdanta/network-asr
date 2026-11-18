from datetime import datetime
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.core.config import get_settings
from app.core.database import get_engine, get_session_factory
from app.models.access_token import RevokedAccessToken
from app.models.opcpay import OpcpayTrialClaim, OpcpayOperation


def migrate(engine, factory, trial_sku):
    RevokedAccessToken.__table__.create(engine, checkfirst=True)
    OpcpayTrialClaim.__table__.create(engine, checkfirst=True)
    with factory() as db:
        candidates = {}
        for op in db.scalars(select(OpcpayOperation).where(OpcpayOperation.kind == "PURCHASE").order_by(OpcpayOperation.id)):
            body = json.loads(op.request_json)
            if body.get("sku_id") != trial_sku:
                continue
            meta = json.loads(op.metadata_json or "{}")
            paid = bool(meta.get("payment_status") in {"PAID", "REFUNDED"} and meta.get("checked_at"))
            previous = candidates.get(op.user_id)
            if previous is None or (paid and not previous[1]):
                candidates[op.user_id] = (op, paid)
        added = 0
        for user_id, (op, paid) in candidates.items():
            claim = db.get(OpcpayTrialClaim, user_id)
            if claim is None:
                db.add(OpcpayTrialClaim(user_id=user_id, sku_id=trial_sku, order_no=op.biz_no,
                    paid_at=datetime.now() if paid else None))
                added += 1
        db.commit()
        return added


if __name__ == "__main__":
    count = migrate(get_engine(), get_session_factory(), get_settings().opcpay_trial_sku_id)
    print("Payment access migration complete; trial records backfilled:", count)
