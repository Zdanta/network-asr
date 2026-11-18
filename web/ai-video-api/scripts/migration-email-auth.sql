-- Additive migration: existing mobile accounts and their IDs remain unchanged.
ALTER TABLE `user` ADD COLUMN email VARCHAR(254) NULL;
ALTER TABLE `user` ADD COLUMN email_verified_at DATETIME NULL;
ALTER TABLE `user` ADD UNIQUE KEY uk_user_email (email);
CREATE TABLE email_verification (
 email VARCHAR(254) NOT NULL PRIMARY KEY,
 nonce VARCHAR(64) NOT NULL, code_hash VARCHAR(64) NOT NULL,
 expires_at DATETIME NOT NULL, sent_at DATETIME NOT NULL,
 window_start DATETIME NOT NULL, send_count INT NOT NULL DEFAULT 0,
 attempts INT NOT NULL DEFAULT 0, state VARCHAR(16) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE email_send_limit (
 identity VARCHAR(64) NOT NULL PRIMARY KEY,
 window_start DATETIME NOT NULL, send_count INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
