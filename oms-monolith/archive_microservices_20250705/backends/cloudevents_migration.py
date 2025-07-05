"""
CloudEvents Migration - Placeholder for missing module
"""

class BackwardCompatibilityLayer:
    def create_legacy_outbox_event(self, event):
        """Convert CloudEvent to OutboxEvent"""
        from .models import OutboxEvent
        return OutboxEvent(
            id=event.id,
            type=event.type,
            source=event.source,
            data=event.data
        )