Import Issue Resolution Summary:
================================

1. Counter/Histogram/Gauge imports fixed:
   - Changed from middleware.common.metrics to prometheus_client in:
     - core/embeddings/service.py
     - core/time_travel/metrics.py
     - services/graph_analysis.py

2. circuit_breaker decorator name fixed:
   - Changed from @unified_circuit_breaker to @circuit_breaker

3. UnifiedHTTPClient casing fixed:
   - Fixed import statements to use correct casing (HTTP not Http)

4. models/exceptions.py created:
   - Added OMSException, ConcurrencyError, ConflictError classes
   - Resolved import errors in concurrency and branch modules

5. OpenTelemetry packages added to requirements.txt:
   - opentelemetry-instrumentation-asyncio
   - opentelemetry-instrumentation-redis
   - opentelemetry-instrumentation-requests
   - opentelemetry-exporter-jaeger
