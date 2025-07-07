"""
TerminusDB Side-Car Process for Audit Cross-Validation
Collects Outbox events and validates against TerminusDB retention policies
"""
import asyncio
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

from models.audit_events import AuditEventV1, AuditAction, ResourceType
from database.unified_terminus_client import create_terminus_client
from core.events.outbox_event import OutboxEvent
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationReport:
    """Audit validation report"""
    timestamp: datetime
    total_events_checked: int
    terminus_events: int
    audit_db_events: int
    missing_in_terminus: List[str]
    missing_in_audit: List[str]
    retention_violations: List[Dict[str, Any]]
    integrity_issues: List[Dict[str, Any]]
    recommendations: List[str]


class TerminusDBSideCarValidator:
    """
    Side-car process for cross-validating audit logs with TerminusDB
    
    Features:
    - Subscribes to Outbox audit events
    - Queries TerminusDB for corresponding records
    - Validates retention policies
    - Generates compliance reports
    - Detects data integrity issues
    """
    
    def __init__(self, terminus_config: Dict[str, Any]):
        """
        Initialize side-car validator
        
        Args:
            terminus_config: TerminusDB connection configuration
        """
        self.terminus_config = terminus_config
        self.terminus_client = None
        self.validation_interval = 3600  # 1 hour
        self.batch_size = 1000
        self._running = False
        self._processed_events: Set[str] = set()
        
    async def initialize(self):
        """Initialize TerminusDB connection"""
        self.terminus_client = await create_terminus_client(
            **self.terminus_config
        )
        logger.info("TerminusDB Side-Car Validator initialized")
    
    async def start(self):
        """Start the side-car validation process"""
        if self._running:
            return
        
        self._running = True
        await self.initialize()
        
        # Start validation loop
        asyncio.create_task(self._validation_loop())
        
        # Start outbox event consumer
        asyncio.create_task(self._consume_outbox_events())
        
        logger.info("Side-car validator started")
    
    async def stop(self):
        """Stop the side-car process"""
        self._running = False
        logger.info("Side-car validator stopped")
    
    async def _validation_loop(self):
        """Main validation loop"""
        while self._running:
            try:
                # Run validation
                report = await self.validate_audit_consistency()
                
                # Log report summary
                logger.info(
                    f"Validation complete - Events: {report.total_events_checked}, "
                    f"Issues: {len(report.integrity_issues)}, "
                    f"Violations: {len(report.retention_violations)}"
                )
                
                # Store report if there are issues
                if report.integrity_issues or report.retention_violations:
                    await self._store_validation_report(report)
                
                # Wait for next interval
                await asyncio.sleep(self.validation_interval)
                
            except Exception as e:
                logger.error(f"Validation loop error: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    async def _consume_outbox_events(self):
        """Consume audit events from outbox"""
        # This would typically connect to your message queue
        # For now, we'll simulate with a simple approach
        while self._running:
            try:
                # In production, this would consume from NATS/Kafka/etc
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Outbox consumer error: {e}")
    
    async def validate_audit_consistency(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> ValidationReport:
        """
        Validate audit log consistency between sources
        
        Args:
            start_time: Start of validation period
            end_time: End of validation period
            
        Returns:
            Validation report with findings
        """
        if not start_time:
            start_time = datetime.now(timezone.utc) - timedelta(hours=24)
        if not end_time:
            end_time = datetime.now(timezone.utc)
        
        report = ValidationReport(
            timestamp=datetime.now(timezone.utc),
            total_events_checked=0,
            terminus_events=0,
            audit_db_events=0,
            missing_in_terminus=[],
            missing_in_audit=[],
            retention_violations=[],
            integrity_issues=[],
            recommendations=[]
        )
        
        try:
            # Get audit events from TerminusDB
            terminus_events = await self._get_terminus_audit_events(
                start_time, end_time
            )
            report.terminus_events = len(terminus_events)
            
            # Get audit events from audit database
            from core.audit.audit_database import get_audit_database
            from models.audit_events import AuditEventFilter
            
            audit_db = await get_audit_database()
            filter_criteria = AuditEventFilter(
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )
            
            audit_events, total_count = await audit_db.query_audit_events(
                filter_criteria
            )
            report.audit_db_events = total_count
            
            # Cross-validate events
            terminus_ids = {e['id'] for e in terminus_events}
            audit_ids = {e['id'] for e in audit_events}
            
            # Find missing events
            report.missing_in_terminus = list(audit_ids - terminus_ids)
            report.missing_in_audit = list(terminus_ids - audit_ids)
            
            # Check retention policies
            violations = await self._check_retention_violations(
                terminus_events, audit_events
            )
            report.retention_violations = violations
            
            # Check data integrity
            integrity_issues = await self._check_data_integrity(
                terminus_events, audit_events
            )
            report.integrity_issues = integrity_issues
            
            # Generate recommendations
            report.recommendations = self._generate_recommendations(report)
            
            report.total_events_checked = len(audit_ids | terminus_ids)
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            report.integrity_issues.append({
                "type": "validation_error",
                "message": str(e)
            })
        
        return report
    
    async def _get_terminus_audit_events(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get audit events from TerminusDB"""
        try:
            # Query TerminusDB for audit events
            query = f"""
            WOQL.and(
                WOQL.greater(v('Time'), '{start_time.isoformat()}'),
                WOQL.less(v('Time'), '{end_time.isoformat()}'),
                WOQL.triple(v('Event'), 'rdf:type', 'AuditEvent'),
                WOQL.triple(v('Event'), 'time', v('Time')),
                WOQL.triple(v('Event'), 'action', v('Action')),
                WOQL.triple(v('Event'), 'actor', v('Actor')),
                WOQL.triple(v('Event'), 'target', v('Target'))
            )
            """
            
            result = await self.terminus_client.query(query)
            
            # Transform results to match audit event structure
            events = []
            for binding in result.get('bindings', []):
                events.append({
                    'id': binding.get('Event', {}).get('@id', ''),
                    'time': binding.get('Time', {}).get('@value', ''),
                    'action': binding.get('Action', {}).get('@value', ''),
                    'actor': binding.get('Actor', {}).get('@id', ''),
                    'target': binding.get('Target', {}).get('@id', '')
                })
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to query TerminusDB: {e}")
            return []
    
    async def _check_retention_violations(
        self,
        terminus_events: List[Dict[str, Any]],
        audit_events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Check for retention policy violations"""
        violations = []
        
        from core.audit.audit_database import AuditRetentionPolicy
        retention_policy = AuditRetentionPolicy()
        
        # Check each audit event
        for event in audit_events:
            try:
                # Parse event details
                action = AuditAction(event.get('action', ''))
                created_at = datetime.fromisoformat(event['created_at'])
                retention_until = datetime.fromisoformat(event['retention_until'])
                
                # Calculate expected retention
                expected_retention = retention_policy.calculate_expiry_date(
                    action, created_at
                )
                
                # Check if retention is correct
                if abs((retention_until - expected_retention).total_seconds()) > 86400:
                    violations.append({
                        'event_id': event['id'],
                        'action': event['action'],
                        'created_at': created_at.isoformat(),
                        'actual_retention': retention_until.isoformat(),
                        'expected_retention': expected_retention.isoformat(),
                        'difference_days': (retention_until - expected_retention).days
                    })
                    
            except Exception as e:
                logger.debug(f"Error checking retention for {event.get('id')}: {e}")
        
        return violations
    
    async def _check_data_integrity(
        self,
        terminus_events: List[Dict[str, Any]],
        audit_events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Check data integrity between sources"""
        issues = []
        
        # Create lookup maps
        terminus_map = {e['id']: e for e in terminus_events}
        audit_map = {e['id']: e for e in audit_events}
        
        # Check events that exist in both
        common_ids = set(terminus_map.keys()) & set(audit_map.keys())
        
        for event_id in common_ids:
            terminus_event = terminus_map[event_id]
            audit_event = audit_map[event_id]
            
            # Compare key fields
            discrepancies = []
            
            # Check action
            if terminus_event.get('action') != audit_event.get('action'):
                discrepancies.append({
                    'field': 'action',
                    'terminus': terminus_event.get('action'),
                    'audit': audit_event.get('action')
                })
            
            # Check timestamp (allow small differences)
            try:
                terminus_time = datetime.fromisoformat(terminus_event.get('time', ''))
                audit_time = datetime.fromisoformat(audit_event.get('created_at', ''))
                
                if abs((terminus_time - audit_time).total_seconds()) > 60:
                    discrepancies.append({
                        'field': 'timestamp',
                        'terminus': terminus_time.isoformat(),
                        'audit': audit_time.isoformat(),
                        'difference_seconds': (terminus_time - audit_time).total_seconds()
                    })
            except:
                pass
            
            if discrepancies:
                issues.append({
                    'event_id': event_id,
                    'type': 'data_mismatch',
                    'discrepancies': discrepancies
                })
        
        return issues
    
    def _generate_recommendations(self, report: ValidationReport) -> List[str]:
        """Generate recommendations based on validation findings"""
        recommendations = []
        
        # Missing events recommendations
        if report.missing_in_terminus:
            recommendations.append(
                f"Sync {len(report.missing_in_terminus)} audit events to TerminusDB"
            )
        
        if report.missing_in_audit:
            recommendations.append(
                f"Investigate {len(report.missing_in_audit)} events only in TerminusDB"
            )
        
        # Retention violations
        if report.retention_violations:
            recommendations.append(
                f"Review retention policy for {len(report.retention_violations)} events"
            )
        
        # Integrity issues
        if report.integrity_issues:
            recommendations.append(
                f"Resolve {len(report.integrity_issues)} data integrity issues"
            )
        
        # General recommendations
        if report.terminus_events == 0:
            recommendations.append(
                "Enable audit event replication to TerminusDB"
            )
        
        sync_rate = 1.0 - (len(report.missing_in_terminus) / max(report.audit_db_events, 1))
        if sync_rate < 0.95:
            recommendations.append(
                f"Improve sync reliability (current: {sync_rate:.1%})"
            )
        
        return recommendations
    
    async def _store_validation_report(self, report: ValidationReport):
        """Store validation report for compliance"""
        try:
            # Store in TerminusDB for historical tracking
            doc = {
                "@type": "AuditValidationReport",
                "@id": f"report_{report.timestamp.isoformat()}",
                "timestamp": report.timestamp.isoformat(),
                "summary": {
                    "total_events_checked": report.total_events_checked,
                    "terminus_events": report.terminus_events,
                    "audit_db_events": report.audit_db_events,
                    "missing_count": len(report.missing_in_terminus) + len(report.missing_in_audit),
                    "violation_count": len(report.retention_violations),
                    "integrity_issue_count": len(report.integrity_issues)
                },
                "details": asdict(report)
            }
            
            await self.terminus_client.insert_document(doc)
            logger.info(f"Stored validation report: {doc['@id']}")
            
        except Exception as e:
            logger.error(f"Failed to store validation report: {e}")
    
    async def generate_compliance_report(
        self,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """
        Generate compliance report for audit trail
        
        Args:
            period_days: Number of days to include in report
            
        Returns:
            Compliance report summary
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=period_days)
        
        # Get all validation reports for period
        query = f"""
        WOQL.and(
            WOQL.triple(v('Report'), 'rdf:type', 'AuditValidationReport'),
            WOQL.triple(v('Report'), 'timestamp', v('Time')),
            WOQL.greater(v('Time'), '{start_time.isoformat()}'),
            WOQL.less(v('Time'), '{end_time.isoformat()}')
        )
        """
        
        result = await self.terminus_client.query(query)
        
        # Aggregate findings
        total_validations = 0
        total_issues = 0
        issue_types = {}
        
        for binding in result.get('bindings', []):
            total_validations += 1
            # Process each report
            # ... aggregation logic ...
        
        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "days": period_days
            },
            "validations_performed": total_validations,
            "total_issues": total_issues,
            "issue_breakdown": issue_types,
            "compliance_score": max(0, 100 - (total_issues / max(total_validations, 1))),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


# Factory function
async def create_sidecar_validator(
    terminus_config: Dict[str, Any]
) -> TerminusDBSideCarValidator:
    """
    Create and initialize side-car validator
    
    Args:
        terminus_config: TerminusDB connection configuration
        
    Returns:
        Initialized validator instance
    """
    validator = TerminusDBSideCarValidator(terminus_config)
    await validator.initialize()
    return validator