-- Additive guest tables. Use migrate_guest.py for idempotent retries; no existing data updates.


CREATE TABLE IF NOT EXISTS guest_identity (
	user_id BIGINT NOT NULL AUTO_INCREMENT, 
	device_hash VARCHAR(64) NOT NULL, 
	session_hash VARCHAR(64) NOT NULL, 
	ip_hash VARCHAR(64) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	target_user_id BIGINT, 
	initial_points INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	expires_at DATETIME NOT NULL, 
	converted_at DATETIME, 
	upload_lease VARCHAR(36), 
	upload_until DATETIME, 
	PRIMARY KEY (user_id), 
	UNIQUE (device_hash), 
	UNIQUE (session_hash)
)

;

CREATE INDEX ix_guest_identity_ip_hash ON guest_identity (ip_hash);

CREATE INDEX idx_guest_expiry ON guest_identity (state, expires_at);

CREATE INDEX idx_guest_created ON guest_identity (created_at);


CREATE TABLE IF NOT EXISTS guest_limit_lock (
	`key` VARCHAR(40) NOT NULL, 
	PRIMARY KEY (`key`)
)

;


CREATE TABLE IF NOT EXISTS guest_reservation (
	task_no VARCHAR(64) NOT NULL, 
	user_id BIGINT NOT NULL, 
	ip_hash VARCHAR(64) NOT NULL, 
	points INTEGER NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (task_no)
)

;

CREATE INDEX idx_guest_res_window ON guest_reservation (state, created_at);

CREATE INDEX ix_guest_reservation_ip_hash ON guest_reservation (ip_hash);

CREATE INDEX ix_guest_reservation_user_id ON guest_reservation (user_id);


CREATE TABLE IF NOT EXISTS guest_event (
	user_id BIGINT NOT NULL, 
	ip_hash VARCHAR(64) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	id BIGINT NOT NULL AUTO_INCREMENT, 
	deleted INTEGER NOT NULL DEFAULT '0', 
	created_by BIGINT, 
	updated_by BIGINT, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
)

;

CREATE INDEX idx_guest_event_limits ON guest_event (ip_hash, created_at);

CREATE INDEX ix_guest_event_user_id ON guest_event (user_id);