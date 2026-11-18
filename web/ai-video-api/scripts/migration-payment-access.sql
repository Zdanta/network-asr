CREATE TABLE IF NOT EXISTS revoked_access_token (
 token_hash VARCHAR(64) NOT NULL PRIMARY KEY,
 revoked_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS opcpay_trial_claim (
 user_id BIGINT NOT NULL PRIMARY KEY,
 sku_id VARCHAR(128) NOT NULL,
 order_no VARCHAR(64) NOT NULL UNIQUE,
 paid_at DATETIME NULL,
 created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Existing purchase backfill is performed by migrate_payment_access.py.
-- READY/UNKNOWN entries do not count as paid; only verified metadata with checked_at does.
