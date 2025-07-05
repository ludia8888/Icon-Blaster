# GraphQL Service Architecture

## Overview

This GraphQL service implements a **modular architecture** with feature flags for enterprise capabilities.

## Architecture Decision

### Phase 1: Simple (Current)
- `simple_main.py` - Minimal viable GraphQL service
- Core features only (Auth, Redis, NATS)
- Used for development and initial deployment

### Phase 2: Modular (Recommended)
- `modular_main.py` - Production-ready with optional features
- Feature flags for Security, Cache, Tracing
- Environment-based configuration

### Phase 3: Enterprise (Future)
- Full DataLoader integration
- Advanced caching strategies
- Schema federation support

## Feature Flags

| Feature | Environment Variable | Default (Dev) | Default (Prod) |
|---------|---------------------|---------------|----------------|
| Security | `ENABLE_GQL_SECURITY` | false | true |
| Cache | `ENABLE_GQL_CACHE` | false | true |
| Tracing | `ENABLE_GQL_TRACING` | false | true |
| Introspection | Auto | true | false |

## Migration Path

1. **Current State**: Using `simple_main.py` for quick startup
2. **Next Step**: Switch to `modular_main.py` in staging
3. **Production**: Enable all features via environment variables

```bash
# Development
APP_ENV=development python main.py

# Staging  
APP_ENV=staging \
ENABLE_GQL_CACHE=true \
ENABLE_GQL_TRACING=true \
python main.py

# Production
APP_ENV=production \
ENABLE_GQL_SECURITY=true \
ENABLE_GQL_CACHE=true \
ENABLE_GQL_TRACING=true \
python main.py
```

## Performance Considerations

### Without Features (Simple)
- Startup: ~5s
- Memory: ~100MB
- Latency: Direct pass-through

### With All Features (Modular)
- Startup: ~10s
- Memory: ~150MB
- Latency: +2-5ms (cache check + security validation)

### Cache Hit Benefits
- 10-100x faster for repeated queries
- Reduces database load
- Essential for read-heavy workloads

## Security Features

When `ENABLE_GQL_SECURITY=true`:
- Query depth limiting (default: 15)
- Query complexity limiting (default: 2000)
- Rate limiting (default: 100 req/60s)
- Introspection disabled in production

## Monitoring

When `ENABLE_GQL_TRACING=true`:
- Prometheus metrics at `/metrics`
- OpenTelemetry spans
- Request duration histograms
- Error rate tracking