"""
IAM Event Handler
Handles events from IAM service for role/permission synchronization
"""
import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from shared.events.cloudevents_enhanced import EnhancedCloudEvent
from utils.logger import get_logger

logger = get_logger(__name__)


class IAMEventHandler:
    """
    Handles IAM service events:
    - iam.role.changed.v1: Role modifications
    - iam.user.updated.v1: User attribute changes
    - iam.permission.granted/revoked.v1: Permission changes
    """
    
    def __init__(self, cache_service=None):
        self.cache_service = cache_service
        self.handlers = {
            "iam.role.changed.v1": self.handle_role_changed,
            "iam.user.updated.v1": self.handle_user_updated,
            "iam.permission.granted.v1": self.handle_permission_granted,
            "iam.permission.revoked.v1": self.handle_permission_revoked,
        }
    
    async def handle_event(self, event: EnhancedCloudEvent):
        """
        Main event handler that routes to specific handlers
        """
        event_type = event.type
        handler = self.handlers.get(event_type)
        
        if not handler:
            logger.warning(f"No handler for IAM event type: {event_type}")
            return
        
        try:
            await handler(event)
            logger.info(f"Successfully processed IAM event: {event_type}")
        except Exception as e:
            logger.error(f"Error processing IAM event {event_type}: {e}")
            raise
    
    async def handle_role_changed(self, event: EnhancedCloudEvent):
        """
        Handle role change events from IAM
        Invalidates cached role/permission mappings
        """
        data = event.data
        role_id = data.get("roleId")
        change_type = data.get("changeType")  # created, updated, deleted
        role_name = data.get("roleName")
        permissions = data.get("permissions", [])
        scopes = data.get("scopes", [])
        
        logger.info(f"Role changed: {role_name} ({role_id}) - {change_type}")
        
        if self.cache_service:
            # Invalidate role cache
            cache_keys = [
                f"role:{role_id}",
                f"role:name:{role_name}",
                f"permissions:role:{role_id}",
                f"scopes:role:{role_id}"
            ]
            
            for key in cache_keys:
                await self.cache_service.delete(key)
            
            # If role was deleted, invalidate all user caches with this role
            if change_type == "deleted":
                await self._invalidate_users_with_role(role_id)
        
        # Store updated role information if not deleted
        if change_type != "deleted" and self.cache_service:
            role_data = {
                "id": role_id,
                "name": role_name,
                "permissions": permissions,
                "scopes": scopes,
                "updated_at": datetime.utcnow().isoformat()
            }
            await self.cache_service.set(
                f"role:{role_id}",
                json.dumps(role_data),
                ttl=3600  # 1 hour
            )
    
    async def handle_user_updated(self, event: EnhancedCloudEvent):
        """
        Handle user update events from IAM
        Invalidates user-specific caches
        """
        data = event.data
        user_id = data.get("userId")
        changes = data.get("changes", {})
        
        logger.info(f"User updated: {user_id} - changes: {list(changes.keys())}")
        
        if self.cache_service:
            # Invalidate user cache
            cache_keys = [
                f"user:{user_id}",
                f"user:permissions:{user_id}",
                f"user:scopes:{user_id}",
                f"jwt:user:{user_id}"  # Invalidate cached JWT validations
            ]
            
            for key in cache_keys:
                await self.cache_service.delete(key)
            
            # If roles changed, update role memberships
            if "roles" in changes:
                old_roles = changes["roles"].get("old", [])
                new_roles = changes["roles"].get("new", [])
                
                # Remove from old role member lists
                for role_id in old_roles:
                    if role_id not in new_roles:
                        await self._remove_user_from_role(user_id, role_id)
                
                # Add to new role member lists
                for role_id in new_roles:
                    if role_id not in old_roles:
                        await self._add_user_to_role(user_id, role_id)
    
    async def handle_permission_granted(self, event: EnhancedCloudEvent):
        """
        Handle permission grant events
        Updates permission caches
        """
        data = event.data
        principal_id = data.get("principalId")  # User or role ID
        principal_type = data.get("principalType")  # user, role, service_account
        permission = data.get("permission")
        resource = data.get("resource")
        
        logger.info(
            f"Permission granted: {permission} on {resource} "
            f"to {principal_type} {principal_id}"
        )
        
        if self.cache_service:
            # Add to permission set
            cache_key = f"permissions:{principal_type}:{principal_id}"
            permissions = await self._get_permissions(principal_type, principal_id)
            
            permission_entry = {
                "permission": permission,
                "resource": resource,
                "granted_at": datetime.utcnow().isoformat()
            }
            
            permissions.append(permission_entry)
            
            await self.cache_service.set(
                cache_key,
                json.dumps(permissions),
                ttl=3600
            )
    
    async def handle_permission_revoked(self, event: EnhancedCloudEvent):
        """
        Handle permission revoke events
        Updates permission caches
        """
        data = event.data
        principal_id = data.get("principalId")
        principal_type = data.get("principalType")
        permission = data.get("permission")
        resource = data.get("resource")
        
        logger.info(
            f"Permission revoked: {permission} on {resource} "
            f"from {principal_type} {principal_id}"
        )
        
        if self.cache_service:
            # Remove from permission set
            cache_key = f"permissions:{principal_type}:{principal_id}"
            permissions = await self._get_permissions(principal_type, principal_id)
            
            # Filter out revoked permission
            permissions = [
                p for p in permissions
                if not (p["permission"] == permission and p["resource"] == resource)
            ]
            
            await self.cache_service.set(
                cache_key,
                json.dumps(permissions),
                ttl=3600
            )
    
    async def _get_permissions(self, principal_type: str, principal_id: str) -> List[Dict]:
        """Get cached permissions for a principal"""
        if not self.cache_service:
            return []
        
        cache_key = f"permissions:{principal_type}:{principal_id}"
        cached = await self.cache_service.get(cache_key)
        
        if cached:
            return json.loads(cached)
        return []
    
    async def _invalidate_users_with_role(self, role_id: str):
        """Invalidate cache for all users with a specific role"""
        if not self.cache_service:
            return
        
        # Get users with this role from cache
        members_key = f"role:members:{role_id}"
        members_data = await self.cache_service.get(members_key)
        
        if members_data:
            user_ids = json.loads(members_data)
            for user_id in user_ids:
                await self.cache_service.delete(f"user:{user_id}")
                await self.cache_service.delete(f"user:permissions:{user_id}")
                await self.cache_service.delete(f"user:scopes:{user_id}")
    
    async def _add_user_to_role(self, user_id: str, role_id: str):
        """Add user to role member list in cache"""
        if not self.cache_service:
            return
        
        members_key = f"role:members:{role_id}"
        members_data = await self.cache_service.get(members_key)
        
        if members_data:
            members = json.loads(members_data)
        else:
            members = []
        
        if user_id not in members:
            members.append(user_id)
            await self.cache_service.set(
                members_key,
                json.dumps(members),
                ttl=3600
            )
    
    async def _remove_user_from_role(self, user_id: str, role_id: str):
        """Remove user from role member list in cache"""
        if not self.cache_service:
            return
        
        members_key = f"role:members:{role_id}"
        members_data = await self.cache_service.get(members_key)
        
        if members_data:
            members = json.loads(members_data)
            if user_id in members:
                members.remove(user_id)
                await self.cache_service.set(
                    members_key,
                    json.dumps(members),
                    ttl=3600
                )


# Event handler registration for NATS consumer
async def setup_iam_event_consumer(nats_client, cache_service=None):
    """
    Set up NATS JetStream consumer for IAM events
    
    Args:
        nats_client: NATS client instance
        cache_service: Cache service for storing role/permission data
    """
    handler = IAMEventHandler(cache_service)
    
    # Create durable consumer for IAM events
    js = nats_client.jetstream()
    
    # Subscribe to IAM events
    await js.subscribe(
        "iam.>",  # All IAM events
        durable_name="oms-iam-consumer",
        stream="IAM_EVENTS",
        cb=lambda msg: asyncio.create_task(
            process_iam_event(msg, handler)
        )
    )
    
    logger.info("IAM event consumer started")


async def process_iam_event(msg, handler: IAMEventHandler):
    """Process incoming IAM event message"""
    try:
        # Parse CloudEvent
        event_data = json.loads(msg.data.decode())
        event = EnhancedCloudEvent.from_dict(event_data)
        
        # Handle event
        await handler.handle_event(event)
        
        # Acknowledge message
        await msg.ack()
        
    except Exception as e:
        logger.error(f"Error processing IAM event: {e}")
        # Negative acknowledge for retry
        await msg.nak()