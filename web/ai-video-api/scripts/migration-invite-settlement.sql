-- Snapshot referral owner, price, rate, hold period and monotonic verified observations.
ALTER TABLE opcpay_operation ADD COLUMN metadata_json LONGTEXT NULL;
-- Old rows remain NULL; do not infer past paid orders or grant rewards from balance changes.
