# oms-event-sdk

Auto-generated SDK for OMS Event API

## Installation

```bash
npm install oms-event-sdk
```

## Usage

```typescript
import { OMSEventClient } from 'oms-event-sdk';

// Create client (implementation depends on transport)
const client = await OMSEventClient.connect({
  natsUrl: 'nats://localhost:4222',
  websocketUrl: 'ws://localhost:8080'
});

// Subscribe to events
await client.subscribeObjecttypecreated((event) => {
  console.log('Object type created:', event);
});

// Publish events
await client.publishSchemacreated({
  specversion: '1.0',
  type: 'com.foundry.oms.schema.created',
  source: '/oms/main',
  id: crypto.randomUUID(),
  data: {
    operation: 'create',
    resource_type: 'schema',
    resource_id: 'example'
  }
});

// Cleanup
await client.close();
```

## Transport Adapters

This SDK provides interfaces but requires transport-specific adapters:

- **NATS**: Use with `nats.js` library
- **WebSocket**: Use with native WebSocket or `ws` library  
- **HTTP**: Use with `fetch` or `axios`

## Generated Types

All event types and schemas are automatically generated from the AsyncAPI specification.

## License

MIT
