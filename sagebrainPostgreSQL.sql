-- Run this in PostgreSQL
CREATE DATABASE sage_ng;

CREATE TABLE threats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region VARCHAR(50) NOT NULL,
    threat_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    severity_score INTEGER,
    title TEXT,
    description TEXT,
    source VARCHAR(50),
    source_url TEXT,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active',
    llm_confidence DECIMAL(3, 2),
    raw_data JSONB
);

CREATE INDEX idx_threats_region ON threats(region);
CREATE INDEX idx_threats_timestamp ON threats(timestamp);
CREATE INDEX idx_threats_severity ON threats(severity);

CREATE TABLE uav_missions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region VARCHAR(50),
    drone_id VARCHAR(50),
    mission_type VARCHAR(50), -- patrol, recon, response
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    flight_path JSONB,
    detections JSONB,
    status VARCHAR(20)
);

CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region VARCHAR(50),
    predicted_threat_type VARCHAR(50),
    probability DECIMAL(4, 2),
    time_window INTERVAL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    model_version VARCHAR(20)
);

-- TimescaleDB for time-series (install extension)
CREATE EXTENSION IF NOT EXISTS timescaledb;
SELECT create_hypertable('threats', 'timestamp');