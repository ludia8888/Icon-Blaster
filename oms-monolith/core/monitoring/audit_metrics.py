"""
Audit Monitoring and Metrics
Provides Prometheus metrics and DLQ monitoring for audit events
"""
from typing import Dict, Any, Optional
import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from prometheus_client import Counter, Histogram, Gauge, Info
from utils.logger import get_logger

logger = get_logger(__name__)

# Prometheus Metrics
audit_events_total = Counter(
    'oms_audit_events_total',
    'Total number of audit events',
    ['action', 'resource_type', 'success']
)

audit_events_failed = Counter(
    'oms_audit_events_failed_total',
    'Total number of failed audit events',
    ['action', 'resource_type', 'failure_reason']
)

audit_event_duration = Histogram(
    'oms_audit_event_duration_seconds',
    'Time taken to process audit events',
    ['action', 'resource_type'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

audit_dlq_size = Gauge(
    'oms_audit_dlq_size',
    'Number of events in audit DLQ',
    ['dlq_type']
)

audit_dlq_oldest_event_age = Gauge(
    'oms_audit_dlq_oldest_event_age_seconds',
    'Age of oldest event in DLQ in seconds',
    ['dlq_type']
)

secure_author_verifications = Counter(
    'oms_secure_author_verifications_total',
    'Total number of secure author verifications',
    ['result', 'reason']
)

service_account_operations = Counter(
    'oms_service_account_operations_total',
    'Operations performed by service accounts',
    ['service_name', 'operation', 'resource_type']
)

audit_info = Info(
    'oms_audit_service',
    'Audit service information'
)

# Set audit service info
audit_info.info({
    'version': '1.0.0',
    'dlq_path': '/tmp/audit_dlq_*.jsonl',
    'dual_write_enabled': 'true'
})


class AuditMetricsCollector:
    """Collects and exposes audit metrics"""
    
    def __init__(self, dlq_path: str = "/tmp"):
        self.dlq_path = Path(dlq_path)
        self._monitor_task: Optional[asyncio.Task] = None
        self._shutdown = False
    
    async def start_monitoring(self):
        """Start background monitoring tasks"""
        self._monitor_task = asyncio.create_task(self._monitor_dlq())
        logger.info("Audit metrics monitoring started")
    
    async def stop_monitoring(self):
        """Stop background monitoring tasks"""
        self._shutdown = True
        if self._monitor_task:
            await self._monitor_task
        logger.info("Audit metrics monitoring stopped")
    
    def record_audit_event(
        self,
        action: str,
        resource_type: str,
        success: bool,
        duration_seconds: float,
        failure_reason: Optional[str] = None
    ):
        """Record metrics for an audit event"""
        # Count total events
        audit_events_total.labels(
            action=action,
            resource_type=resource_type,
            success=str(success)
        ).inc()
        
        # Record duration
        audit_event_duration.labels(
            action=action,
            resource_type=resource_type
        ).observe(duration_seconds)
        
        # Count failures
        if not success and failure_reason:
            audit_events_failed.labels(
                action=action,
                resource_type=resource_type,
                failure_reason=failure_reason
            ).inc()
    
    def record_secure_author_verification(self, is_valid: bool, reason: str):
        """Record secure author verification attempt"""
        secure_author_verifications.labels(
            result="valid" if is_valid else "invalid",
            reason=reason
        ).inc()
    
    def record_service_account_operation(
        self,
        service_name: str,
        operation: str,
        resource_type: str
    ):
        """Record operation by service account"""
        service_account_operations.labels(
            service_name=service_name,
            operation=operation,
            resource_type=resource_type
        ).inc()
    
    async def _monitor_dlq(self):
        """Monitor DLQ files for metrics"""
        while not self._shutdown:
            try:
                # Check different DLQ files
                dlq_files = {
                    "fallback": self.dlq_path / "audit_dlq_fallback.jsonl",
                    "emergency": self.dlq_path / "audit_dlq_emergency.jsonl"
                }
                
                for dlq_type, dlq_file in dlq_files.items():
                    if dlq_file.exists():
                        # Count events
                        event_count = 0
                        oldest_timestamp = None
                        
                        with open(dlq_file, 'r') as f:
                            for line in f:
                                event_count += 1
                                try:
                                    event = json.loads(line)
                                    # Get timestamp
                                    ts_str = (
                                        event.get('failed_at') or 
                                        event.get('timestamp') or
                                        event.get('original_event', {}).get('timestamp')
                                    )
                                    if ts_str:
                                        ts = datetime.fromisoformat(
                                            ts_str.replace('Z', '+00:00')
                                        )
                                        if oldest_timestamp is None or ts < oldest_timestamp:
                                            oldest_timestamp = ts
                                except:
                                    pass
                        
                        # Update metrics
                        audit_dlq_size.labels(dlq_type=dlq_type).set(event_count)
                        
                        if oldest_timestamp:
                            age_seconds = (
                                datetime.now(timezone.utc) - oldest_timestamp
                            ).total_seconds()
                            audit_dlq_oldest_event_age.labels(
                                dlq_type=dlq_type
                            ).set(age_seconds)
                    else:
                        # No file, set to 0
                        audit_dlq_size.labels(dlq_type=dlq_type).set(0)
                
            except Exception as e:
                logger.error(f"Error monitoring DLQ: {e}")
            
            # Check every 30 seconds
            await asyncio.sleep(30)


class DLQAlertManager:
    """Manages alerts for DLQ issues"""
    
    def __init__(self, alert_threshold: int = 100, age_threshold_seconds: int = 3600):
        self.alert_threshold = alert_threshold
        self.age_threshold_seconds = age_threshold_seconds
        self._last_alert_time: Dict[str, datetime] = {}
        self._alert_cooldown_seconds = 300  # 5 minutes between alerts
    
    async def check_dlq_health(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check DLQ health and generate alerts if needed"""
        alerts = []
        now = datetime.now(timezone.utc)
        
        # Check DLQ size
        for dlq_type in ["fallback", "emergency"]:
            size_key = f"dlq_size_{dlq_type}"
            if size_key in metrics:
                size = metrics[size_key]
                if size > self.alert_threshold:
                    if self._should_alert(f"size_{dlq_type}", now):
                        alerts.append({
                            "severity": "warning" if dlq_type == "fallback" else "critical",
                            "type": "dlq_size_exceeded",
                            "dlq_type": dlq_type,
                            "message": f"DLQ {dlq_type} has {size} events (threshold: {self.alert_threshold})",
                            "current_size": size,
                            "threshold": self.alert_threshold
                        })
        
        # Check event age
        for dlq_type in ["fallback", "emergency"]:
            age_key = f"dlq_oldest_age_{dlq_type}"
            if age_key in metrics:
                age_seconds = metrics[age_key]
                if age_seconds > self.age_threshold_seconds:
                    if self._should_alert(f"age_{dlq_type}", now):
                        alerts.append({
                            "severity": "warning",
                            "type": "dlq_age_exceeded",
                            "dlq_type": dlq_type,
                            "message": f"DLQ {dlq_type} has events older than {age_seconds/3600:.1f} hours",
                            "oldest_age_hours": age_seconds / 3600,
                            "threshold_hours": self.age_threshold_seconds / 3600
                        })
        
        return alerts
    
    def _should_alert(self, alert_key: str, now: datetime) -> bool:
        """Check if we should send an alert (with cooldown)"""
        last_alert = self._last_alert_time.get(alert_key)
        if last_alert is None:
            self._last_alert_time[alert_key] = now
            return True
        
        if (now - last_alert).total_seconds() > self._alert_cooldown_seconds:
            self._last_alert_time[alert_key] = now
            return True
        
        return False


# Global instances
_metrics_collector: Optional[AuditMetricsCollector] = None
_alert_manager: Optional[DLQAlertManager] = None


def get_metrics_collector() -> AuditMetricsCollector:
    """Get global metrics collector instance"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = AuditMetricsCollector()
    return _metrics_collector


def get_alert_manager() -> DLQAlertManager:
    """Get global alert manager instance"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = DLQAlertManager()
    return _alert_manager