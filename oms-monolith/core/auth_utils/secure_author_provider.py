"""
Secure Author Provider for TerminusDB Integration
Ensures author field in commits is cryptographically verified

SECURITY REQUIREMENTS:
1. Author field MUST come from verified JWT token
2. Service accounts must be clearly identified
3. Impersonation must be prevented
4. Audit trail must be tamper-proof

INTEGRATION POINTS:
- AuthMiddleware: Provides verified UserContext
- TerminusDB commits: Receives secure author string
- Audit logs: Records author verification
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

from core.auth_utils import UserContext
from utils.logger import get_logger

logger = get_logger(__name__)


class SecureAuthorProvider:
    """
    Provides cryptographically secure author information for database commits
    
    Features:
    - Verified user identity from JWT
    - Service account identification
    - Delegation tracking
    - Tamper detection
    """
    
    def __init__(self, jwt_secret: Optional[str] = None):
        self.jwt_secret = jwt_secret
        
    def get_secure_author(
        self,
        user_context: UserContext,
        include_metadata: bool = True
    ) -> str:
        """
        Generate secure author string from verified UserContext
        
        Format: "username (user_id) [verified]"
        With metadata: "username (user_id) [verified|hash:abc123|ts:2025-01-01T00:00:00Z]"
        
        Args:
            user_context: Verified user context from JWT
            include_metadata: Include verification metadata
            
        Returns:
            Secure author string for commits
        """
        if not user_context:
            raise ValueError("UserContext is required for secure author")
        
        # Basic format
        author = f"{user_context.username} ({user_context.user_id})"
        
        # Add service account indicator
        if user_context.is_service_account:
            author += " [service]"
        else:
            author += " [verified]"
        
        # Add metadata for enhanced security
        if include_metadata:
            metadata = self._generate_author_metadata(user_context)
            author += f"|{metadata}"
        
        logger.debug(f"Generated secure author: {author[:50]}...")
        return author
    
    def parse_secure_author(self, author_string: str) -> Dict[str, Any]:
        """
        Parse secure author string back to components
        
        Returns:
            Dict with username, user_id, is_service, metadata
        """
        try:
            # Extract basic components
            import re
            
            # Pattern: username (user_id) [type]|metadata
            pattern = r'^(.+?)\s+\((.+?)\)\s+\[(service|verified)\](?:\|(.+))?$'
            match = re.match(pattern, author_string)
            
            if not match:
                return {"raw": author_string, "verified": False}
            
            username, user_id, account_type, metadata = match.groups()
            
            result = {
                "username": username,
                "user_id": user_id,
                "is_service_account": account_type == "service",
                "verified": True,
                "raw": author_string
            }
            
            # Parse metadata if present
            if metadata:
                result["metadata"] = self._parse_metadata(metadata)
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to parse author string: {e}")
            return {"raw": author_string, "verified": False}
    
    def verify_author_integrity(
        self,
        author_string: str,
        user_context: Optional[UserContext] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify author string integrity
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        parsed = self.parse_secure_author(author_string)
        
        if not parsed.get("verified"):
            return False, "Invalid author format"
        
        # If we have current context, verify it matches
        if user_context:
            if parsed["user_id"] != user_context.user_id:
                return False, "User ID mismatch"
            if parsed["username"] != user_context.username:
                return False, "Username mismatch"
        
        # Verify metadata if present
        if "metadata" in parsed:
            metadata = parsed["metadata"]
            
            # Check timestamp is reasonable (within last 24 hours)
            if "ts" in metadata:
                try:
                    ts = datetime.fromisoformat(metadata["ts"].replace("Z", "+00:00"))
                    age = datetime.now(timezone.utc) - ts
                    if age.days > 1:
                        return False, "Author timestamp too old"
                except:
                    return False, "Invalid timestamp"
            
            # Verify hash if we have the secret
            if "hash" in metadata and self.jwt_secret:
                expected_hash = self._calculate_author_hash(
                    parsed["username"],
                    parsed["user_id"],
                    metadata.get("ts", "")
                )
                if metadata["hash"] != expected_hash[:8]:
                    return False, "Hash verification failed"
        
        return True, None
    
    def _generate_author_metadata(self, user_context: UserContext) -> str:
        """Generate metadata string for author field"""
        metadata_parts = []
        
        # Add timestamp
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        metadata_parts.append(f"ts:{ts}")
        
        # Add verification hash
        if self.jwt_secret:
            hash_value = self._calculate_author_hash(
                user_context.username,
                user_context.user_id,
                ts
            )
            metadata_parts.append(f"hash:{hash_value[:8]}")
        
        # Add roles summary
        if user_context.roles:
            roles_str = ",".join(sorted(user_context.roles)[:3])  # First 3 roles
            metadata_parts.append(f"roles:{roles_str}")
        
        # Add tenant if multi-tenant
        if user_context.tenant_id:
            metadata_parts.append(f"tenant:{user_context.tenant_id}")
        
        return "|".join(metadata_parts)
    
    def _parse_metadata(self, metadata_str: str) -> Dict[str, str]:
        """Parse metadata string into dict"""
        metadata = {}
        
        for part in metadata_str.split("|"):
            if ":" in part:
                key, value = part.split(":", 1)
                metadata[key] = value
        
        return metadata
    
    def _calculate_author_hash(
        self,
        username: str,
        user_id: str,
        timestamp: str
    ) -> str:
        """Calculate verification hash for author"""
        if not self.jwt_secret:
            return ""
        
        # Create hash input
        hash_input = f"{username}|{user_id}|{timestamp}|{self.jwt_secret}"
        
        # Calculate SHA-256
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def create_delegation_author(
        self,
        delegator: UserContext,
        on_behalf_of: str,
        reason: str
    ) -> str:
        """
        Create author string for delegated actions
        
        Used when a service or admin acts on behalf of another user
        """
        # Get base author for delegator
        delegator_author = self.get_secure_author(delegator, include_metadata=False)
        
        # Add delegation info
        delegation_info = f"on_behalf_of:{on_behalf_of}|reason:{reason}"
        
        return f"{delegator_author} [delegated|{delegation_info}]"
    
    def extract_effective_user(self, author_string: str) -> str:
        """
        Extract the effective user from author string
        
        For delegated actions, returns the on_behalf_of user
        For regular actions, returns the primary user
        """
        parsed = self.parse_secure_author(author_string)
        
        if not parsed.get("verified"):
            return author_string
        
        # Check for delegation
        if "[delegated|" in author_string:
            import re
            match = re.search(r'on_behalf_of:([^|]+)', author_string)
            if match:
                return match.group(1)
        
        return parsed.get("user_id", author_string)


# Global instance
_secure_author_provider: Optional[SecureAuthorProvider] = None


def get_secure_author_provider(jwt_secret: Optional[str] = None) -> SecureAuthorProvider:
    """Get or create secure author provider"""
    global _secure_author_provider
    
    if not _secure_author_provider:
        import os
        # Try multiple sources for JWT secret
        secret = (
            jwt_secret or 
            os.getenv("JWT_SECRET") or 
            os.getenv("JWT_SECRET_KEY") or
            os.getenv("AUTH_JWT_SECRET")
        )
        
        if not secret:
            logger.warning(
                "No JWT secret found in environment. "
                "Author hash verification will be disabled. "
                "Set JWT_SECRET environment variable for production use."
            )
        
        _secure_author_provider = SecureAuthorProvider(secret)
    
    return _secure_author_provider


def format_secure_author(user_context: UserContext) -> str:
    """Convenience function to format secure author"""
    provider = get_secure_author_provider()
    return provider.get_secure_author(user_context)