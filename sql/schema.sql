-- Run as MySQL root/admin:  mysql -u root -p < backend/sql/schema.sql
CREATE DATABASE IF NOT EXISTS mandi_dashboard
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Change the password before running!
CREATE USER IF NOT EXISTS 'mandi_user'@'localhost' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON mandi_dashboard.* TO 'mandi_user'@'localhost';
FLUSH PRIVILEGES;

USE mandi_dashboard;

CREATE TABLE IF NOT EXISTS mandi_prices (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  record_hash   CHAR(64)     NOT NULL COMMENT 'SHA-256 of date|state|district|market|commodity|variety|grade',
  price_date    DATE         NOT NULL,
  state         VARCHAR(100) NOT NULL,
  district      VARCHAR(150) NOT NULL,
  market        VARCHAR(200) NOT NULL,
  commodity     VARCHAR(100) NOT NULL,
  variety       VARCHAR(150) NOT NULL DEFAULT '',
  grade         VARCHAR(100) NOT NULL DEFAULT '',
  min_price     DECIMAL(10,2) NULL,
  max_price     DECIMAL(10,2) NULL,
  modal_price   DECIMAL(10,2) NULL,
  fetched_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_record_hash (record_hash),
  KEY ix_commodity_date (commodity, price_date),
  KEY ix_district_date (district, price_date),
  KEY ix_market_date (market, price_date),
  KEY ix_price_date (price_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fetch_logs (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  trigger_source   VARCHAR(20)  NOT NULL COMMENT 'scheduler | manual | cli',
  status           VARCHAR(20)  NOT NULL COMMENT 'running | success | partial | failed',
  records_fetched  INT NOT NULL DEFAULT 0,
  records_inserted INT NOT NULL DEFAULT 0,
  records_updated  INT NOT NULL DEFAULT 0,
  records_rejected INT NOT NULL DEFAULT 0,
  error_message    TEXT NULL,
  started_at       DATETIME NOT NULL,
  finished_at      DATETIME NULL,
  PRIMARY KEY (id),
  KEY ix_fetch_started (started_at),
  KEY ix_fetch_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Government Minimum Support Prices (Rs/quintal) per commodity and marketing season.
-- Seeded automatically by the app / scripts/init_db.py; add a row when a new MSP is announced.
CREATE TABLE IF NOT EXISTS msp_rates (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  commodity     VARCHAR(100) NOT NULL,
  season        VARCHAR(20)  NOT NULL COMMENT 'e.g. RMS 2026-27 (rabi) or KMS 2026-27 (kharif)',
  applies_from  DATE         NOT NULL,
  applies_to    DATE         NOT NULL,
  msp           DECIMAL(10,2) NOT NULL,
  source        VARCHAR(300) NOT NULL DEFAULT '',
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_msp_commodity_season (commodity, season),
  KEY ix_msp_commodity_from (commodity, applies_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
