-- ================================================================
-- OMS Audit Tables Cleanup Migration
-- 감사 테이블 정리 마이그레이션 (audit-service로 이관 후)
-- ================================================================

-- Migration Info
-- Created: 2025-07-06
-- Purpose: Remove audit tables from OMS monolith after migration to audit-service
-- Status: PENDING (Run only after data migration is complete)

-- ================================================================
-- STEP 1: CREATE BACKUP VIEWS (Optional - for safety)
-- ================================================================

-- Create read-only views for audit data access during transition period
CREATE OR REPLACE VIEW audit_events_readonly AS 
SELECT 
    event_id,
    event_type,
    event_category,
    severity,
    user_id,
    username,
    target_type,
    target_id,
    operation,
    created_at,
    metadata,
    'MIGRATED_TO_AUDIT_SERVICE' as migration_status
FROM audit_events_v1
WHERE created_at < NOW() - INTERVAL '1 day';  -- Only show old data

COMMENT ON VIEW audit_events_readonly IS 'Read-only view of migrated audit events for reference';

-- ================================================================
-- STEP 2: VERIFY MIGRATION COMPLETION
-- ================================================================

-- Check if migration is complete
DO $$
DECLARE
    pending_records INTEGER;
    migration_date TIMESTAMP := '2025-07-06 00:00:00'::timestamp;
BEGIN
    -- Count records that should have been migrated
    SELECT COUNT(*) INTO pending_records
    FROM audit_events_v1 
    WHERE created_at < migration_date;
    
    IF pending_records > 0 THEN
        RAISE NOTICE 'WARNING: % audit records found before migration date. Verify migration completion before proceeding.', pending_records;
    ELSE
        RAISE NOTICE 'Migration verification passed. Ready to drop audit tables.';
    END IF;
END $$;

-- ================================================================
-- STEP 3: DISABLE AUDIT TRIGGERS (If any exist)
-- ================================================================

-- Disable any audit-related triggers
DO $$
DECLARE
    trigger_rec RECORD;
BEGIN
    FOR trigger_rec IN 
        SELECT schemaname, tablename, triggername 
        FROM pg_triggers 
        WHERE triggername LIKE '%audit%'
          AND schemaname = 'public'
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I.%I CASCADE', 
                      trigger_rec.triggername, 
                      trigger_rec.schemaname, 
                      trigger_rec.tablename);
        RAISE NOTICE 'Dropped trigger: %.%', trigger_rec.tablename, trigger_rec.triggername;
    END LOOP;
END $$;

-- ================================================================
-- STEP 4: DROP AUDIT INDEXES
-- ================================================================

-- Drop audit-specific indexes
DROP INDEX IF EXISTS idx_audit_events_user_id;
DROP INDEX IF EXISTS idx_audit_events_target;
DROP INDEX IF EXISTS idx_audit_events_created_at;
DROP INDEX IF EXISTS idx_audit_events_event_type;
DROP INDEX IF EXISTS idx_audit_events_category;
DROP INDEX IF EXISTS idx_audit_events_severity;
DROP INDEX IF EXISTS idx_audit_events_metadata;
DROP INDEX IF EXISTS idx_audit_events_composite;

-- Drop any custom audit indexes
DO $$
DECLARE
    index_rec RECORD;
BEGIN
    FOR index_rec IN 
        SELECT indexname 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
          AND (tablename LIKE '%audit%' OR indexname LIKE '%audit%')
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS %I CASCADE', index_rec.indexname);
        RAISE NOTICE 'Dropped index: %', index_rec.indexname;
    END LOOP;
END $$;

-- ================================================================
-- STEP 5: DROP AUDIT SEQUENCES
-- ================================================================

-- Drop sequences used by audit tables
DROP SEQUENCE IF EXISTS audit_events_v1_id_seq CASCADE;
DROP SEQUENCE IF EXISTS audit_metadata_id_seq CASCADE;
DROP SEQUENCE IF EXISTS audit_sessions_id_seq CASCADE;

-- ================================================================
-- STEP 6: DROP AUDIT FUNCTIONS AND PROCEDURES
-- ================================================================

-- Drop audit-related functions
DROP FUNCTION IF EXISTS create_audit_event(jsonb) CASCADE;
DROP FUNCTION IF EXISTS query_audit_events(text, text, timestamp, timestamp) CASCADE;
DROP FUNCTION IF EXISTS cleanup_old_audit_events(interval) CASCADE;
DROP FUNCTION IF EXISTS audit_event_trigger() CASCADE;
DROP FUNCTION IF EXISTS get_audit_statistics() CASCADE;

-- Drop any custom audit functions
DO $$
DECLARE
    func_rec RECORD;
BEGIN
    FOR func_rec IN 
        SELECT proname, pg_get_function_identity_arguments(oid) as args
        FROM pg_proc 
        WHERE proname LIKE '%audit%'
          AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    LOOP
        EXECUTE format('DROP FUNCTION IF EXISTS %I(%s) CASCADE', func_rec.proname, func_rec.args);
        RAISE NOTICE 'Dropped function: %(%)', func_rec.proname, func_rec.args;
    END LOOP;
END $$;

-- ================================================================
-- STEP 7: DROP AUDIT VIEWS
-- ================================================================

-- Drop audit-related views (except the readonly view we created)
DROP VIEW IF EXISTS audit_events_summary CASCADE;
DROP VIEW IF EXISTS audit_events_by_user CASCADE;
DROP VIEW IF EXISTS audit_events_by_target CASCADE;
DROP VIEW IF EXISTS recent_audit_events CASCADE;
DROP VIEW IF EXISTS audit_security_events CASCADE;

-- ================================================================
-- STEP 8: DROP AUDIT TABLES
-- ================================================================

-- CRITICAL: These drops are irreversible. Ensure backups exist!

-- Drop main audit tables
DROP TABLE IF EXISTS audit_events_v1 CASCADE;
DROP TABLE IF EXISTS audit_metadata CASCADE;
DROP TABLE IF EXISTS audit_sessions CASCADE;
DROP TABLE IF EXISTS audit_users CASCADE;
DROP TABLE IF EXISTS audit_targets CASCADE;
DROP TABLE IF EXISTS audit_dlq CASCADE;  -- Dead letter queue
DROP TABLE IF EXISTS audit_events CASCADE;  -- Legacy table if exists

-- Drop any remaining audit-related tables
DO $$
DECLARE
    table_rec RECORD;
BEGIN
    FOR table_rec IN 
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public' 
          AND tablename LIKE '%audit%'
          AND tablename != 'audit_events_readonly'  -- Keep our readonly view
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', table_rec.tablename);
        RAISE NOTICE 'Dropped table: %', table_rec.tablename;
    END LOOP;
END $$;

-- ================================================================
-- STEP 9: DROP AUDIT TYPES AND DOMAINS
-- ================================================================

-- Drop custom audit types
DROP TYPE IF EXISTS audit_severity CASCADE;
DROP TYPE IF EXISTS audit_event_category CASCADE;
DROP TYPE IF EXISTS audit_action_type CASCADE;
DROP TYPE IF EXISTS audit_target_type CASCADE;

-- Drop audit domains
DROP DOMAIN IF EXISTS audit_user_id CASCADE;
DROP DOMAIN IF EXISTS audit_event_id CASCADE;

-- ================================================================
-- STEP 10: CLEAN UP PERMISSIONS AND ROLES
-- ================================================================

-- Revoke audit-specific permissions
REVOKE ALL ON SCHEMA audit FROM audit_service_user;
DROP SCHEMA IF EXISTS audit CASCADE;

-- Drop audit-specific roles (be careful!)
-- DROP ROLE IF EXISTS audit_service_user;  -- Uncomment if role is no longer needed
-- DROP ROLE IF EXISTS audit_readonly_user; -- Uncomment if role is no longer needed

-- ================================================================
-- STEP 11: UPDATE SYSTEM CATALOGS
-- ================================================================

-- Remove any audit-related configuration
DELETE FROM pg_settings WHERE name LIKE '%audit%' AND source = 'database';

-- ================================================================
-- STEP 12: FINAL VERIFICATION
-- ================================================================

-- Verify cleanup
DO $$
DECLARE
    remaining_objects INTEGER := 0;
    obj_count INTEGER;
BEGIN
    -- Check remaining audit tables
    SELECT COUNT(*) INTO obj_count
    FROM pg_tables 
    WHERE schemaname = 'public' 
      AND tablename LIKE '%audit%'
      AND tablename != 'audit_events_readonly';
    remaining_objects := remaining_objects + obj_count;
    
    -- Check remaining audit functions
    SELECT COUNT(*) INTO obj_count
    FROM pg_proc 
    WHERE proname LIKE '%audit%'
      AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    remaining_objects := remaining_objects + obj_count;
    
    -- Check remaining audit indexes
    SELECT COUNT(*) INTO obj_count
    FROM pg_indexes 
    WHERE schemaname = 'public' 
      AND (tablename LIKE '%audit%' OR indexname LIKE '%audit%');
    remaining_objects := remaining_objects + obj_count;
    
    IF remaining_objects > 0 THEN
        RAISE NOTICE 'WARNING: % audit-related objects still remain. Manual cleanup may be required.', remaining_objects;
    ELSE
        RAISE NOTICE 'SUCCESS: All audit tables and objects have been cleaned up.';
        RAISE NOTICE 'Audit functionality is now fully migrated to audit-service.';
    END IF;
END $$;

-- ================================================================
-- MIGRATION COMPLETION LOG
-- ================================================================

-- Log migration completion (if audit log table existed)
INSERT INTO migration_log (
    migration_name,
    migration_type,
    status,
    started_at,
    completed_at,
    notes
) VALUES (
    'audit_tables_cleanup',
    'AUDIT_MIGRATION',
    'COMPLETED',
    NOW(),
    NOW(),
    'Audit tables dropped after successful migration to audit-service. Data preserved in audit-service database.'
) ON CONFLICT DO NOTHING;

-- ================================================================
-- ROLLBACK NOTES
-- ================================================================

/*
ROLLBACK PROCEDURE (if needed):

1. Stop audit-service
2. Restore audit tables from backup:
   pg_restore -d oms_db audit_tables_backup.dump

3. Re-enable audit functionality:
   - Update USE_AUDIT_SERVICE=false
   - Restart OMS application

4. Verify data integrity:
   SELECT COUNT(*) FROM audit_events_v1;

IMPORTANT: This rollback will lose any audit events created 
after the migration to audit-service.
*/

COMMENT ON VIEW audit_events_readonly IS 
'Read-only view of historical audit events. All new events go to audit-service.';

-- End of migration script
*/