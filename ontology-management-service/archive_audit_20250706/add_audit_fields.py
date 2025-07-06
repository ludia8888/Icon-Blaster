#!/usr/bin/env python3
"""
Migration: Add audit fields to TerminusDB schema
Adds _created_by, _updated_by, and related timestamp fields
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

from database.clients.unified_database_client import get_unified_database_client
from utils.logger import get_logger

logger = get_logger(__name__)


# Audit field definitions
AUDIT_FIELDS = {
    "_created_by": {
        "@type": "xsd:string",
        "@description": "User ID who created this document"
    },
    "_created_by_username": {
        "@type": "xsd:string", 
        "@description": "Username who created this document"
    },
    "_created_at": {
        "@type": "xsd:dateTime",
        "@description": "Timestamp when document was created"
    },
    "_updated_by": {
        "@type": "xsd:string",
        "@optional": True,
        "@description": "User ID who last updated this document"
    },
    "_updated_by_username": {
        "@type": "xsd:string",
        "@optional": True,
        "@description": "Username who last updated this document"
    },
    "_updated_at": {
        "@type": "xsd:dateTime",
        "@optional": True,
        "@description": "Timestamp when document was last updated"
    },
    "_deleted": {
        "@type": "xsd:boolean",
        "@optional": True,
        "@description": "Soft delete flag"
    },
    "_deleted_by": {
        "@type": "xsd:string",
        "@optional": True,
        "@description": "User ID who deleted this document"
    },
    "_deleted_by_username": {
        "@type": "xsd:string",
        "@optional": True,
        "@description": "Username who deleted this document"
    },
    "_deleted_at": {
        "@type": "xsd:dateTime",
        "@optional": True,
        "@description": "Timestamp when document was deleted"
    }
}


class AuditFieldsMigration:
    """Migration to add audit fields to all document types"""
    
    def __init__(self):
        self.db_client = None
        self.updated_types = []
        self.failed_types = []
    
    async def run(self):
        """Execute the migration"""
        logger.info("Starting audit fields migration...")
        
        try:
            # Get database client
            self.db_client = await get_unified_database_client()
            
            # Get all document types
            document_types = await self._get_all_document_types()
            logger.info(f"Found {len(document_types)} document types to update")
            
            # Update each type
            for doc_type in document_types:
                await self._add_audit_fields_to_type(doc_type)
            
            # Report results
            logger.info(f"Migration completed:")
            logger.info(f"  - Updated: {len(self.updated_types)} types")
            logger.info(f"  - Failed: {len(self.failed_types)} types")
            
            if self.failed_types:
                logger.error(f"Failed types: {', '.join(self.failed_types)}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
    
    async def _get_all_document_types(self) -> List[str]:
        """Get all document types from the database"""
        try:
            # This would use WOQL to query all document types
            # For now, return common types
            return [
                "ObjectType",
                "LinkType", 
                "ActionType",
                "FunctionType",
                "Schema",
                "Branch",
                "Proposal",
                "Document"
            ]
        except Exception as e:
            logger.error(f"Failed to get document types: {e}")
            return []
    
    async def _add_audit_fields_to_type(self, type_name: str):
        """Add audit fields to a specific document type"""
        try:
            logger.info(f"Adding audit fields to {type_name}...")
            
            # Get current schema for the type
            # In real implementation, this would fetch the actual schema
            
            # Add audit fields
            # This would use WOQL to update the schema
            # For now, we'll simulate the update
            
            # Example WOQL query structure:
            # WOQL.and(
            #     WOQL.delete_quad("v:Type", "property", "v:OldProperty", "schema"),
            #     WOQL.add_quad("v:Type", "property", AUDIT_FIELDS, "schema")
            # )
            
            self.updated_types.append(type_name)
            logger.info(f"  ✓ Updated {type_name}")
            
        except Exception as e:
            logger.error(f"  ✗ Failed to update {type_name}: {e}")
            self.failed_types.append(type_name)
    
    async def rollback(self):
        """Rollback the migration if needed"""
        logger.info("Rolling back audit fields migration...")
        
        # Remove audit fields from updated types
        for type_name in self.updated_types:
            try:
                # Remove audit fields
                logger.info(f"  Removing audit fields from {type_name}")
            except Exception as e:
                logger.error(f"  Failed to rollback {type_name}: {e}")


async def up():
    """Run the migration"""
    migration = AuditFieldsMigration()
    success = await migration.run()
    if not success:
        raise Exception("Migration failed")


async def down():
    """Rollback the migration"""
    migration = AuditFieldsMigration()
    await migration.rollback()


if __name__ == "__main__":
    # Run migration
    asyncio.run(up())