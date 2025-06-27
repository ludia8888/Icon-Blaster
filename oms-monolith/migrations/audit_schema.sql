-- Audit Service Database Schema
-- PostgreSQL schema for audit event storage and outbox pattern

-- Create database if not exists (run as superuser)
-- CREATE DATABASE audit_db;

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For text search

-- Audit events table
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(255) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    actor_id VARCHAR(255) NOT NULL,
    actor_username VARCHAR(255) NOT NULL,
    actor_email VARCHAR(255),
    actor_roles TEXT[], -- Array of roles
    actor_tenant_id VARCHAR(255),
    target_resource_type VARCHAR(100) NOT NULL,
    target_resource_id VARCHAR(500) NOT NULL,
    target_resource_name VARCHAR(500),
    target_branch VARCHAR(255),
    success BOOLEAN NOT NULL DEFAULT true,
    error_code VARCHAR(100),
    error_message TEXT,
    duration_ms INTEGER,
    request_id VARCHAR(255),
    correlation_id VARCHAR(255),
    causation_id VARCHAR(255),
    changes JSONB,
    metadata JSONB,
    tags JSONB,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for audit_events
CREATE INDEX IF NOT EXISTS idx_audit_events_event_id ON audit_events(event_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor_id ON audit_events(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_target ON audit_events(target_resource_type, target_resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_time ON audit_events(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_request_id ON audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_correlation_id ON audit_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON audit_events(actor_tenant_id) WHERE actor_tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_success ON audit_events(success) WHERE success = false;

-- Outbox table for transactional event publishing
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(255) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    source VARCHAR(255) NOT NULL,
    subject VARCHAR(500),
    correlation_id VARCHAR(255),
    idempotency_key VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, processing, published, failed
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for outbox_events
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_events(status) WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_outbox_idempotency ON outbox_events(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outbox_retry ON outbox_events(next_retry_at) WHERE status = 'failed' AND retry_count < max_retries;
CREATE INDEX IF NOT EXISTS idx_outbox_created ON outbox_events(created_at);

-- Event consumer tracking for idempotency
CREATE TABLE IF NOT EXISTS event_consumer_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consumer_name VARCHAR(255) NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processing_duration_ms INTEGER,
    status VARCHAR(50) NOT NULL DEFAULT 'success', -- success, failed, skipped
    error_message TEXT,
    
    -- Ensure idempotency
    UNIQUE(consumer_name, event_id)
);

-- Create indexes for event_consumer_tracking
CREATE INDEX IF NOT EXISTS idx_consumer_tracking_event ON event_consumer_tracking(event_id);
CREATE INDEX IF NOT EXISTS idx_consumer_tracking_processed ON event_consumer_tracking(processed_at DESC);

-- Audit retention policy table
CREATE TABLE IF NOT EXISTS audit_retention_policies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    event_type_pattern VARCHAR(255), -- Regex pattern for event types
    action_pattern VARCHAR(255), -- Regex pattern for actions
    retention_days INTEGER NOT NULL,
    archive_enabled BOOLEAN DEFAULT false,
    archive_location VARCHAR(500),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Audit reports metadata
CREATE TABLE IF NOT EXISTS audit_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_type VARCHAR(100) NOT NULL,
    report_name VARCHAR(255) NOT NULL,
    parameters JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, generating, completed, failed
    result_location VARCHAR(500),
    result_summary JSONB,
    requested_by VARCHAR(255) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Functions for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_outbox_events_updated_at BEFORE UPDATE ON outbox_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_audit_retention_policies_updated_at BEFORE UPDATE ON audit_retention_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Partitioning for audit_events table (optional, for high volume)
-- Example: Partition by month
-- CREATE TABLE audit_events_2024_01 PARTITION OF audit_events
--     FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- Default retention policies
INSERT INTO audit_retention_policies (name, description, event_type_pattern, retention_days, is_active)
VALUES 
    ('default', 'Default retention policy', '.*', 365, true),
    ('auth_events', 'Authentication events retention', 'auth\\..*', 730, true),
    ('schema_changes', 'Schema change events retention', 'schema\\..*', 1825, true),
    ('temporary_events', 'Temporary event retention', 'temp\\..*', 30, true)
ON CONFLICT (name) DO NOTHING;

-- Create indexes for JSON queries
CREATE INDEX IF NOT EXISTS idx_audit_events_metadata_gin ON audit_events USING gin(metadata);
CREATE INDEX IF NOT EXISTS idx_audit_events_tags_gin ON audit_events USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_audit_events_changes_gin ON audit_events USING gin(changes);

-- Create composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_audit_events_actor_time ON audit_events(actor_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_target_time ON audit_events(target_resource_type, target_resource_id, event_time DESC);

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO audit_user;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO audit_user;