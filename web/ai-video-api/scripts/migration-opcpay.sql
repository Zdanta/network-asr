-- Additive migration. No existing balances/orders/tasks are changed.
CREATE TABLE IF NOT EXISTS opcpay_operation (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  kind VARCHAR(16) NOT NULL,
  user_id BIGINT NOT NULL,
  action_id VARCHAR(64) NOT NULL,
  biz_no VARCHAR(64) NOT NULL,
  request_json LONGTEXT NOT NULL,
  response_json LONGTEXT NULL,
  result_text LONGTEXT NULL,
  state VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  lease_until DATETIME NULL,
  lease_owner VARCHAR(64) NULL,
  attempts INT NOT NULL DEFAULT 0,
  deleted INT NOT NULL DEFAULT 0,
  created_by BIGINT NULL,
  updated_by BIGINT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_opcpay_action (kind, user_id, action_id),
  UNIQUE KEY uk_opcpay_biz (biz_no),
  KEY idx_opcpay_recovery (kind, state, lease_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
