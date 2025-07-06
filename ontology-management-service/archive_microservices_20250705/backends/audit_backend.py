"""Audit backend for compliance-focused event publishing with dual-write pattern"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from core.events.unified_publisher import EventPublisherBackend, PublisherConfig
from core.events.backends.http_backend import HTTPEventBackend

logger = logging.getLogger(__name__)


class AuditEventBackend(EventPublisherBackend):
    """
    Audit-compliant event publishing backend with dual-write pattern.
    
    Features:
    - Dual-write to database and event stream for compliance
    - Immutability guarantees
    - Cryptographic event hashing
    - Compliance metadata enrichment
    - Automatic PII detection and masking
    """
    
    def __init__(self, config: PublisherConfig):
        self.config = config
        self.db_client = config.audit_db_client
        self.enable_dual_write = config.enable_dual_write
        
        # Use HTTP backend for event streaming
        self.stream_backend = HTTPEventBackend(config)
        
        # Audit-specific settings
        self.compliance_mode = True
        self.hash_events = True
        self.mask_pii = config.enable_pii_protection
        
        self._connected = False
    
    async def connect(self) -> None:
        """Initialize connections for dual-write"""
        if not self._connected:
            # Connect to event stream backend
            await self.stream_backend.connect()
            
            # Verify database client is available
            if self.enable_dual_write and not self.db_client:
                logger.warning("Dual-write enabled but no database client provided")
            
            self._connected = True
            logger.info("Audit backend connected with dual-write enabled")
    
    async def disconnect(self) -> None:
        """Close connections"""
        if self._connected:
            await self.stream_backend.disconnect()
            self._connected = False
            logger.info("Audit backend disconnected")
    
    async def publish(self, event: Dict[str, Any]) -> bool:
        """
        Publish single audit event with dual-write pattern.
        
        Args:
            event: Event data dictionary
            
        Returns:
            bool: True if both writes succeed (or if fallback succeeds)
        """
        if not self._connected:
            logger.error("Audit backend not connected")
            return False
        
        try:
            # Enrich event with audit metadata
            audit_event = self._enrich_audit_event(event)
            
            # Phase 1: Write to database (primary storage)
            db_success = await self._write_to_database(audit_event)
            
            # Phase 2: Publish to event stream (for real-time processing)
            stream_success = await self.stream_backend.publish(audit_event)
            
            # Dual-write success tracking
            if db_success and stream_success:
                logger.debug(f"Audit event dual-write successful: {audit_event.get('event_id')}")
                return True
            elif db_success and not stream_success:
                # Database write succeeded but stream failed - compliance still met
                logger.warning(f"Audit event stream publish failed, but database write succeeded: {audit_event.get('event_id')}")
                return True  # Return True because audit trail is preserved
            else:
                # Database write failed - critical compliance issue
                logger.error(f"Audit event database write failed: {audit_event.get('event_id')}")
                return False
                
        except Exception as e:
            logger.error(f"Audit publish error: {e}")
            # Send to DLQ for retry
            await self._send_to_dlq(audit_event, str(e))
            return False
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> bool:
        """
        Publish multiple audit events with dual-write pattern.
        
        Args:
            events: List of event dictionaries
            
        Returns:
            bool: True if all events are successfully written
        """
        if not self._connected:
            logger.error("Audit backend not connected")
            return False
        
        try:
            # Enrich all events
            audit_events = [self._enrich_audit_event(event) for event in events]
            
            # Phase 1: Batch write to database
            db_success = await self._write_batch_to_database(audit_events)
            
            # Phase 2: Batch publish to event stream
            stream_success = await self.stream_backend.publish_batch(audit_events)
            
            if db_success and stream_success:
                logger.debug(f"Audit batch dual-write successful: {len(audit_events)} events")
                return True
            elif db_success and not stream_success:
                logger.warning(f"Audit batch stream publish failed, but database write succeeded: {len(audit_events)} events")
                return True  # Database write is sufficient for compliance
            else:
                logger.error(f"Audit batch database write failed: {len(audit_events)} events")
                return False
                
        except Exception as e:
            logger.error(f"Audit batch publish error: {e}")
            # Send entire batch to DLQ
            for event in audit_events:
                await self._send_to_dlq(event, str(e))
            return False
    
    async def health_check(self) -> bool:
        """Check health of both database and stream backends"""
        try:
            # Check stream backend health
            stream_health = await self.stream_backend.health_check()
            
            # Check database health (if client available)
            db_health = True
            if self.db_client and hasattr(self.db_client, 'health_check'):
                db_health = await self.db_client.health_check()
            
            return stream_health and db_health
            
        except Exception:
            return False
    
    def _enrich_audit_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich event with audit-specific metadata.
        
        Args:
            event: Original event data
            
        Returns:
            Dict with audit metadata added
        """
        import uuid
        import hashlib
        
        # Create a copy to avoid modifying original
        audit_event = event.copy()
        
        # Add audit metadata
        audit_event['audit_metadata'] = {
            'event_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'compliance_version': '1.0',
            'immutable': True
        }
        
        # Add cryptographic hash for integrity
        if self.hash_events:
            event_json = json.dumps(audit_event, sort_keys=True)
            event_hash = hashlib.sha256(event_json.encode()).hexdigest()
            audit_event['audit_metadata']['hash'] = event_hash
        
        # Mask PII if enabled
        if self.mask_pii:
            audit_event = self._mask_pii_fields(audit_event)
        
        return audit_event
    
    def _mask_pii_fields(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mask potential PII fields in the event.
        
        Args:
            event: Event data
            
        Returns:
            Event with PII fields masked
        """
        pii_fields = ['email', 'phone', 'ssn', 'credit_card', 'password', 'ip_address']
        
        def mask_value(value: str) -> str:
            if len(value) <= 4:
                return '*' * len(value)
            return value[:2] + '*' * (len(value) - 4) + value[-2:]
        
        def mask_recursive(obj):
            if isinstance(obj, dict):
                return {
                    k: mask_value(v) if k.lower() in pii_fields and isinstance(v, str) else mask_recursive(v)
                    for k, v in obj.items()
                }
            elif isinstance(obj, list):
                return [mask_recursive(item) for item in obj]
            return obj
        
        return mask_recursive(event)
    
    async def _write_to_database(self, event: Dict[str, Any]) -> bool:
        """
        Write audit event to database.
        
        Args:
            event: Audit event data
            
        Returns:
            bool: Success status
        """
        if not self.db_client:
            return True  # No database configured, skip
        
        try:
            # If db_client has specific audit method, use it
            if hasattr(self.db_client, 'write_audit_event'):
                await self.db_client.write_audit_event(event)
            else:
                # Generic write method
                await self.db_client.write(event)
            
            return True
            
        except Exception as e:
            logger.error(f"Database write error: {e}")
            return False
    
    async def _write_batch_to_database(self, events: List[Dict[str, Any]]) -> bool:
        """
        Write multiple audit events to database.
        
        Args:
            events: List of audit events
            
        Returns:
            bool: Success status
        """
        if not self.db_client:
            return True  # No database configured, skip
        
        try:
            # If db_client has specific batch audit method, use it
            if hasattr(self.db_client, 'write_audit_events_batch'):
                await self.db_client.write_audit_events_batch(events)
            elif hasattr(self.db_client, 'write_batch'):
                await self.db_client.write_batch(events)
            else:
                # Fall back to individual writes
                for event in events:
                    await self._write_to_database(event)
            
            return True
            
        except Exception as e:
            logger.error(f"Database batch write error: {e}")
            return False
    
    async def _send_to_dlq(self, event: Dict[str, Any], error_reason: str):
        """
        Send failed audit event to Dead Letter Queue
        
        Args:
            event: Failed audit event
            error_reason: Reason for failure
        """
        try:
            dlq_event = {
                "original_event": event,
                "error_reason": error_reason,
                "failed_at": datetime.utcnow().isoformat(),
                "retry_count": event.get("audit_metadata", {}).get("retry_count", 0) + 1,
                "backend": "audit"
            }
            
            # Try to send to DLQ using HTTP backend with different config
            dlq_config = self.config.copy()
            dlq_config.endpoint = self.config.endpoint or "http://localhost:8080/dlq"
            dlq_config.enable_retry = False  # Don't retry DLQ sends
            
            dlq_backend = HTTPEventBackend(dlq_config)
            await dlq_backend.connect()
            
            success = await dlq_backend.publish({
                "type": "audit.dlq",
                "data": dlq_event,
                "subject": "audit.failed",
                "source": "/oms/audit/dlq"
            })
            
            if success:
                logger.warning(f"Sent audit event to DLQ: {event.get('audit_metadata', {}).get('event_id')}")
            else:
                # If DLQ also fails, log to file as last resort
                import json
                with open("/tmp/audit_dlq_fallback.jsonl", "a") as f:
                    f.write(json.dumps(dlq_event) + "\n")
                logger.error(f"Failed to send to DLQ, wrote to fallback file")
                
        except Exception as e:
            logger.error(f"DLQ send failed: {e}")
            # Last resort - ensure we don't lose the audit event
            import json
            try:
                with open("/tmp/audit_dlq_emergency.jsonl", "a") as f:
                    f.write(json.dumps({
                        "event": event,
                        "error": str(error_reason),
                        "dlq_error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    }) + "\n")
            except:
                pass
    
    # Additional method for compatibility with audit_service.py
    async def publish_audit_event_direct(self, event: Dict[str, Any]) -> bool:
        """
        Direct publish method for backward compatibility with audit_service.py
        
        This method is deprecated and will be removed in future versions.
        Use publish() instead.
        """
        logger.warning("publish_audit_event_direct is deprecated, use publish() instead")
        return await self.publish(event)