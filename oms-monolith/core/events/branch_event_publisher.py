"""
Branch Event Publisher Adapter
Provides domain-specific event publishing methods for branch service
"""
from typing import Optional, Dict, Any
from core.event_publisher.nats_publisher import NATSEventPublisher
from core.event_publisher.cloudevents_enhanced import CloudEventBuilder, EventType
from utils.logger import get_logger

logger = get_logger(__name__)


class BranchEventPublisher:
    """
    Domain-specific event publisher for branch operations
    Wraps NATSEventPublisher with branch-specific methods
    """
    
    def __init__(self, nats_url: Optional[str] = None):
        self.publisher = NATSEventPublisher(nats_url)
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the publisher"""
        if not self._initialized:
            await self.publisher.connect()
            self._initialized = True
            logger.info("Branch event publisher initialized")
    
    async def close(self) -> None:
        """Close the publisher"""
        if self._initialized:
            await self.publisher.disconnect()
            self._initialized = False
    
    async def publish_branch_created(
        self,
        branch_name: str,
        parent_branch: str,
        author: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Publish branch created event"""
        await self.initialize()
        
        event = CloudEventBuilder(
            EventType.BRANCH_CREATED,
            f"/oms/branches/{branch_name}"
        ).with_subject(f"branch/{branch_name}").with_data({
            "branch_name": branch_name,
            "parent_branch": parent_branch,
            "author": author,
            "description": description,
            "metadata": metadata or {}
        }).with_oms_context(
            branch=branch_name,
            commit="",  # Will be filled by branch service
            author=author
        ).build()
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception("Failed to publish branch created event")
    
    async def publish_branch_updated(
        self,
        branch_name: str,
        updates: Dict[str, Any],
        author: str
    ) -> None:
        """Publish branch updated event"""
        await self.initialize()
        
        event = CloudEventBuilder(
            EventType.BRANCH_UPDATED,
            f"/oms/branches/{branch_name}"
        ).with_subject(f"branch/{branch_name}").with_data({
            "branch_name": branch_name,
            "updates": updates,
            "author": author
        }).with_oms_context(
            branch=branch_name,
            commit="",
            author=author
        ).build()
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception("Failed to publish branch updated event")
    
    async def publish_branch_merged(
        self,
        source_branch: str,
        target_branch: str,
        merge_commit: str,
        author: str,
        proposal_id: Optional[str] = None
    ) -> None:
        """Publish branch merged event"""
        await self.initialize()
        
        event = CloudEventBuilder(
            EventType.BRANCH_MERGED,
            f"/oms/branches/{source_branch}"
        ).with_subject(f"branch/{source_branch}/merge").with_data({
            "source_branch": source_branch,
            "target_branch": target_branch,
            "merge_commit": merge_commit,
            "author": author,
            "proposal_id": proposal_id
        }).with_oms_context(
            branch=target_branch,
            commit=merge_commit,
            author=author
        ).build()
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception("Failed to publish branch merged event")
    
    async def publish_proposal_created(
        self,
        proposal_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        author: str,
        description: Optional[str] = None
    ) -> None:
        """Publish proposal created event"""
        await self.initialize()
        
        event = CloudEventBuilder(
            EventType.PROPOSAL_CREATED,
            f"/oms/proposals/{proposal_id}"
        ).with_subject(f"proposal/{proposal_id}").with_data({
            "proposal_id": proposal_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "author": author,
            "description": description
        }).with_oms_context(
            branch=source_branch,
            commit="",
            author=author
        ).build()
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception("Failed to publish proposal created event")
    
    async def publish_proposal_updated(
        self,
        proposal_id: str,
        updates: Dict[str, Any],
        author: str
    ) -> None:
        """Publish proposal updated event"""
        await self.initialize()
        
        event = CloudEventBuilder(
            EventType.PROPOSAL_UPDATED,
            f"/oms/proposals/{proposal_id}"
        ).with_subject(f"proposal/{proposal_id}").with_data({
            "proposal_id": proposal_id,
            "updates": updates,
            "author": author
        }).with_oms_context(
            branch="",
            commit="",
            author=author
        ).build()
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception("Failed to publish proposal updated event")
    
    async def publish_proposal_approved(
        self,
        proposal_id: str,
        approver: str,
        comment: Optional[str] = None
    ) -> None:
        """Publish proposal approved event"""
        await self.initialize()
        
        event = CloudEventBuilder(
            EventType.PROPOSAL_APPROVED,
            f"/oms/proposals/{proposal_id}"
        ).with_subject(f"proposal/{proposal_id}/approve").with_data({
            "proposal_id": proposal_id,
            "approver": approver,
            "comment": comment
        }).with_oms_context(
            branch="",
            commit="",
            author=approver
        ).build()
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception("Failed to publish proposal approved event")
    
    async def publish_proposal_rejected(
        self,
        proposal_id: str,
        rejector: str,
        reason: Optional[str] = None
    ) -> None:
        """Publish proposal rejected event"""
        await self.initialize()
        
        event = CloudEventBuilder(
            EventType.PROPOSAL_REJECTED,
            f"/oms/proposals/{proposal_id}"
        ).with_subject(f"proposal/{proposal_id}/reject").with_data({
            "proposal_id": proposal_id,
            "rejector": rejector,
            "reason": reason
        }).with_oms_context(
            branch="",
            commit="",
            author=rejector
        ).build()
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception("Failed to publish proposal rejected event")
    
    # Implement EventPublisherProtocol methods for compatibility
    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> None:
        """Generic publish method"""
        await self.initialize()
        
        event = CloudEventBuilder(
            event_type,
            "/oms/branches"
        ).with_data(data).build()
        
        if correlation_id:
            event.add_correlation_context(correlation_id)
        
        success = await self.publisher.publish_event(event)
        if not success:
            raise Exception(f"Failed to publish event {event_type}")
    
    async def publish_batch(self, events: list[Dict[str, Any]]) -> None:
        """Publish multiple events"""
        await self.initialize()
        success = await self.publisher.publish_batch(events)
        if not success:
            raise Exception("Failed to publish batch events")
    
    def subscribe(self, event_type: str, handler: Any) -> None:
        """Subscribe to events (not implemented for publisher)"""
        logger.warning("Subscribe called on publisher - use event subscriber instead")
    
    def unsubscribe(self, event_type: str, handler: Any) -> None:
        """Unsubscribe from events (not implemented for publisher)"""
        logger.warning("Unsubscribe called on publisher - use event subscriber instead")