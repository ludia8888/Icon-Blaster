# oms-event-sdk

Auto-generated SDK for OMS Event API

## Installation

```bash
pip install oms-event-sdk
```

## Usage

```python
import asyncio
from oms_event_sdk import OMSEventClient, ClientConfig

async def main():
    # Create client (implementation depends on transport)
    config = ClientConfig(
        nats_url="nats://localhost:4222",
        websocket_url="ws://localhost:8080"
    )
    
    client = await OMSEventClient.connect(config)
    
    # Subscribe to events
    async def handle_objecttype_created(event):
        print(f"Object type created: {event}")
    
    await client.subscribe_objecttypecreated(handle_objecttype_created)
    
    # Publish events
    await client.publish_schemacreated({
        "specversion": "1.0",
        "type": "com.foundry.oms.schema.created",
        "source": "/oms/main",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "data": {
            "operation": "create",
            "resource_type": "schema",
            "resource_id": "example"
        }
    })
    
    # Cleanup
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Transport Adapters

This SDK provides interfaces but requires transport-specific adapters:

- **NATS**: Use with `nats-py` library
- **WebSocket**: Use with `websockets` library
- **HTTP**: Use with `httpx` or `aiohttp`

## Generated Models

All event types and schemas are automatically generated from the AsyncAPI specification using Pydantic models.

## Development

```bash
# Install in development mode
pip install -e .[dev]

# Run tests
pytest

# Format code
black .
isort .

# Type checking
mypy .
```

## License

MIT
