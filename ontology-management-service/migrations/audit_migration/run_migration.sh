#!/bin/bash
# =============================================================================
# Audit Migration Runner Script
# OMS 모놀리스에서 audit-service로 완전 마이그레이션
# =============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OMS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MIGRATION_LOG="$SCRIPT_DIR/migration_$(date +%Y%m%d_%H%M%S).log"

# Default values
DRY_RUN=false
SKIP_VERIFICATION=false
BATCH_SIZE=1000
MAX_CONCURRENT=5
SOURCE_DB_URL=""
AUDIT_SERVICE_URL="http://localhost:8004"
API_KEY=""
START_DATE=""
END_DATE=""

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$MIGRATION_LOG"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$MIGRATION_LOG"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$MIGRATION_LOG"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$MIGRATION_LOG"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Audit Migration Runner for OMS Monolith to audit-service

OPTIONS:
    -s, --source-db URL         Source database URL (required)
    -a, --audit-url URL         Audit service URL (default: http://localhost:8004)
    -k, --api-key KEY           Audit service API key (required)
    -b, --batch-size SIZE       Batch size for migration (default: 1000)
    -c, --max-concurrent NUM    Max concurrent batches (default: 5)
    --start-date YYYY-MM-DD     Start date for migration
    --end-date YYYY-MM-DD       End date for migration
    --dry-run                   Run in dry-run mode (no actual migration)
    --skip-verification         Skip migration verification
    -h, --help                  Show this help message

EXAMPLES:
    # Full migration
    $0 -s "postgresql://user:pass@localhost:5432/oms_db" -k "api-key-123"
    
    # Dry run
    $0 -s "postgresql://user:pass@localhost:5432/oms_db" -k "api-key-123" --dry-run
    
    # Date range migration
    $0 -s "postgresql://user:pass@localhost:5432/oms_db" -k "api-key-123" \
       --start-date 2025-01-01 --end-date 2025-07-06

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--source-db)
            SOURCE_DB_URL="$2"
            shift 2
            ;;
        -a|--audit-url)
            AUDIT_SERVICE_URL="$2"
            shift 2
            ;;
        -k|--api-key)
            API_KEY="$2"
            shift 2
            ;;
        -b|--batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        -c|--max-concurrent)
            MAX_CONCURRENT="$2"
            shift 2
            ;;
        --start-date)
            START_DATE="$2"
            shift 2
            ;;
        --end-date)
            END_DATE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-verification)
            SKIP_VERIFICATION=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validation
if [[ -z "$SOURCE_DB_URL" ]]; then
    print_error "Source database URL is required"
    show_usage
    exit 1
fi

if [[ -z "$API_KEY" ]]; then
    print_error "Audit service API key is required"
    show_usage
    exit 1
fi

# Start migration
print_info "Starting Audit Migration Process"
print_info "================================="
print_info "Source DB: $SOURCE_DB_URL"
print_info "Audit Service: $AUDIT_SERVICE_URL"
print_info "Batch Size: $BATCH_SIZE"
print_info "Max Concurrent: $MAX_CONCURRENT"
print_info "Dry Run: $DRY_RUN"
print_info "Log File: $MIGRATION_LOG"
print_info ""

# Step 1: Pre-migration checks
print_info "Step 1: Pre-migration checks"
print_info "=============================="

# Check if Python dependencies are available
if ! python3 -c "import asyncpg, httpx" 2>/dev/null; then
    print_error "Required Python packages not found. Installing..."
    pip install asyncpg httpx
fi

# Check audit service health
print_info "Checking audit service health..."
if curl -f -s "$AUDIT_SERVICE_URL/api/v2/events/health" > /dev/null; then
    print_success "Audit service is healthy"
else
    print_error "Audit service health check failed. Please ensure audit-service is running."
    exit 1
fi

# Check database connectivity
print_info "Checking source database connectivity..."
if python3 -c "
import asyncio
import asyncpg
import sys

async def test_connection():
    try:
        conn = await asyncpg.connect('$SOURCE_DB_URL')
        await conn.close()
        return True
    except Exception as e:
        print(f'Connection failed: {e}')
        return False

result = asyncio.run(test_connection())
sys.exit(0 if result else 1)
" 2>/dev/null; then
    print_success "Source database connection successful"
else
    print_error "Source database connection failed"
    exit 1
fi

# Step 2: Backup verification
print_info ""
print_info "Step 2: Backup verification"
print_info "============================"

if [[ "$DRY_RUN" == "false" ]]; then
    print_warning "IMPORTANT: This migration will transfer audit data to audit-service."
    print_warning "Ensure you have a backup of your audit tables before proceeding."
    print_warning ""
    
    read -p "Do you have a backup of audit tables? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "Please create a backup before proceeding."
        print_info "You can create a backup with:"
        print_info "pg_dump -h <host> -U <user> -d <database> -t audit_events_v1 > audit_backup.sql"
        exit 1
    fi
    print_success "Backup confirmed"
fi

# Step 3: Data migration
print_info ""
print_info "Step 3: Data migration"
print_info "======================"

# Build migration command
MIGRATION_CMD="python3 $SCRIPT_DIR/migrate_audit_data.py"
MIGRATION_CMD="$MIGRATION_CMD --source-db '$SOURCE_DB_URL'"
MIGRATION_CMD="$MIGRATION_CMD --audit-service-url '$AUDIT_SERVICE_URL'"
MIGRATION_CMD="$MIGRATION_CMD --api-key '$API_KEY'"
MIGRATION_CMD="$MIGRATION_CMD --batch-size $BATCH_SIZE"
MIGRATION_CMD="$MIGRATION_CMD --max-concurrent $MAX_CONCURRENT"

if [[ -n "$START_DATE" ]]; then
    MIGRATION_CMD="$MIGRATION_CMD --start-date '$START_DATE'"
fi

if [[ -n "$END_DATE" ]]; then
    MIGRATION_CMD="$MIGRATION_CMD --end-date '$END_DATE'"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    MIGRATION_CMD="$MIGRATION_CMD --dry-run"
fi

if [[ "$SKIP_VERIFICATION" == "true" ]]; then
    MIGRATION_CMD="$MIGRATION_CMD --no-verify"
fi

print_info "Running data migration..."
print_info "Command: $MIGRATION_CMD"

if eval "$MIGRATION_CMD"; then
    print_success "Data migration completed successfully"
else
    print_error "Data migration failed. Check logs for details."
    exit 1
fi

# Step 4: Schema cleanup (only if not dry-run)
if [[ "$DRY_RUN" == "false" ]]; then
    print_info ""
    print_info "Step 4: Schema cleanup"
    print_info "======================"
    
    print_warning "This step will DROP audit tables from the source database."
    print_warning "This action is IRREVERSIBLE!"
    print_warning ""
    
    read -p "Proceed with schema cleanup? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Running schema cleanup..."
        
        if psql "$SOURCE_DB_URL" -f "$SCRIPT_DIR/001_drop_audit_tables.sql"; then
            print_success "Schema cleanup completed"
        else
            print_error "Schema cleanup failed. Manual cleanup may be required."
            print_warning "Audit data has been migrated, but old tables still exist."
        fi
    else
        print_warning "Schema cleanup skipped. Old audit tables still exist."
        print_info "You can run cleanup later with:"
        print_info "psql '$SOURCE_DB_URL' -f '$SCRIPT_DIR/001_drop_audit_tables.sql'"
    fi
fi

# Step 5: Configuration update
print_info ""
print_info "Step 5: Configuration update"
print_info "============================"

print_info "Updating OMS configuration to use audit-service..."

# Update environment variables
ENV_FILE="$OMS_ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    # Backup current .env
    cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Update audit service settings
    sed -i.bak 's/USE_AUDIT_SERVICE=false/USE_AUDIT_SERVICE=true/' "$ENV_FILE"
    
    if grep -q "AUDIT_SERVICE_URL=" "$ENV_FILE"; then
        sed -i.bak "s|AUDIT_SERVICE_URL=.*|AUDIT_SERVICE_URL=$AUDIT_SERVICE_URL|" "$ENV_FILE"
    else
        echo "AUDIT_SERVICE_URL=$AUDIT_SERVICE_URL" >> "$ENV_FILE"
    fi
    
    if grep -q "AUDIT_SERVICE_API_KEY=" "$ENV_FILE"; then
        sed -i.bak "s|AUDIT_SERVICE_API_KEY=.*|AUDIT_SERVICE_API_KEY=$API_KEY|" "$ENV_FILE"
    else
        echo "AUDIT_SERVICE_API_KEY=$API_KEY" >> "$ENV_FILE"
    fi
    
    print_success "Environment configuration updated"
else
    print_warning ".env file not found. Please update configuration manually."
    print_info "Set USE_AUDIT_SERVICE=true in your environment"
fi

# Final summary
print_info ""
print_info "Migration Summary"
print_info "=================="
print_success "✅ Audit data migration completed"

if [[ "$DRY_RUN" == "false" ]]; then
    print_success "✅ Audit service is now active"
    print_info "📝 Next steps:"
    print_info "   1. Restart OMS application with USE_AUDIT_SERVICE=true"
    print_info "   2. Monitor audit-service logs for any issues"
    print_info "   3. Verify audit events are being recorded in audit-service"
    print_info "   4. Consider running cleanup script if schema cleanup was skipped"
else
    print_info "🔍 Dry-run completed. No changes were made."
    print_info "📝 To run actual migration, remove --dry-run flag"
fi

print_info ""
print_info "Migration log: $MIGRATION_LOG"
print_success "Audit migration process completed!"

exit 0