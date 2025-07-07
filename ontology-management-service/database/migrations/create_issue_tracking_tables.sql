-- Issue Tracking Database Schema
-- Links all changes to issue IDs for complete traceability

-- Table to store change-issue links
CREATE TABLE IF NOT EXISTS change_issue_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Change information
    change_id TEXT NOT NULL,
    change_type TEXT NOT NULL, -- schema, acl, branch, merge, deletion
    branch_name TEXT NOT NULL,
    
    -- Primary issue (required)
    primary_issue_provider TEXT NOT NULL,
    primary_issue_id TEXT NOT NULL,
    
    -- Emergency override information
    emergency_override BOOLEAN DEFAULT FALSE,
    override_justification TEXT,
    override_approver TEXT,
    
    -- Metadata
    linked_by TEXT NOT NULL,
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Validation results (JSON)
    validation_result TEXT,
    
    -- Indexes
    INDEX idx_change_id (change_id),
    INDEX idx_issue_id (primary_issue_id),
    INDEX idx_branch_name (branch_name),
    INDEX idx_linked_at (linked_at)
);

-- Table for related issues (many-to-many)
CREATE TABLE IF NOT EXISTS change_related_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    issue_provider TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    
    FOREIGN KEY (link_id) REFERENCES change_issue_links(id) ON DELETE CASCADE,
    INDEX idx_link_id (link_id),
    INDEX idx_issue (issue_provider, issue_id)
);

-- Table for issue metadata cache
CREATE TABLE IF NOT EXISTS issue_metadata_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_provider TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    
    -- Issue details
    title TEXT,
    status TEXT,
    issue_type TEXT,
    priority TEXT,
    assignee TEXT,
    issue_url TEXT,
    
    -- Metadata (JSON)
    metadata TEXT,
    
    -- Cache management
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    
    UNIQUE(issue_provider, issue_id),
    INDEX idx_expires_at (expires_at)
);

-- Table for issue requirement overrides
CREATE TABLE IF NOT EXISTS issue_requirement_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Override context
    branch_pattern TEXT,
    operation_type TEXT,
    user_pattern TEXT,
    
    -- Override settings
    requirement_enabled BOOLEAN DEFAULT TRUE,
    allow_types TEXT, -- JSON array of allowed issue types
    require_status_check BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    created_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    reason TEXT,
    
    INDEX idx_branch_pattern (branch_pattern),
    INDEX idx_expires_at (expires_at)
);

-- View for issue tracking compliance
CREATE VIEW IF NOT EXISTS issue_tracking_compliance AS
SELECT 
    DATE(linked_at) as date,
    change_type,
    branch_name,
    COUNT(*) as total_changes,
    SUM(CASE WHEN emergency_override = 1 THEN 1 ELSE 0 END) as emergency_overrides,
    COUNT(DISTINCT primary_issue_id) as unique_issues,
    COUNT(DISTINCT linked_by) as unique_users
FROM change_issue_links
GROUP BY DATE(linked_at), change_type, branch_name;

-- View for user issue activity
CREATE VIEW IF NOT EXISTS user_issue_activity AS
SELECT 
    linked_by as user,
    COUNT(*) as total_changes,
    COUNT(DISTINCT primary_issue_id) as unique_issues,
    SUM(CASE WHEN emergency_override = 1 THEN 1 ELSE 0 END) as emergency_overrides,
    MIN(linked_at) as first_change,
    MAX(linked_at) as last_change
FROM change_issue_links
GROUP BY linked_by;