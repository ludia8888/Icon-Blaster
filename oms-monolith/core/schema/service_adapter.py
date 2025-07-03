"""
Schema Service Adapter - Placeholder for missing module
"""

from .service import SchemaService

class SchemaServiceAdapter:
    def __init__(self, db_client, event_service=None):
        self.service = SchemaService(db_client, event_service)