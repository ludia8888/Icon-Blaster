#!/bin/bash
# Setup monitoring stack for OMS

set -e

echo "🚀 Setting up monitoring stack for OMS..."

# Create necessary directories
mkdir -p grafana/provisioning/{dashboards,datasources}
mkdir -p prometheus/rules

# Create Grafana datasource provisioning
cat > grafana/provisioning/datasources/prometheus.yml << EOF
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
  
  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:16686
    editable: true
EOF

# Create Grafana dashboard provisioning
cat > grafana/provisioning/dashboards/dashboards.yml << EOF
apiVersion: 1

providers:
  - name: 'OMS Dashboards'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
EOF

# Create microservices dashboard
cat > grafana/provisioning/dashboards/microservices.json << EOF
{
  "dashboard": {
    "title": "OMS Microservices Dashboard",
    "tags": ["oms", "microservices"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Embedding Service Metrics",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "type": "graph",
        "targets": [
          {
            "expr": "rate(embedding_generation_duration_seconds_sum[5m]) / rate(embedding_generation_duration_seconds_count[5m])",
            "legendFormat": "Avg Generation Time"
          }
        ]
      },
      {
        "title": "Scheduler Service Jobs",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "type": "graph",
        "targets": [
          {
            "expr": "scheduler_jobs_created_total",
            "legendFormat": "Jobs Created"
          },
          {
            "expr": "rate(scheduler_jobs_executed_total[5m])",
            "legendFormat": "Jobs Executed Rate"
          }
        ]
      },
      {
        "title": "Event Gateway Traffic",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8},
        "type": "graph",
        "targets": [
          {
            "expr": "rate(event_gateway_events_published_total[5m])",
            "legendFormat": "Events Published - {{stream}}"
          },
          {
            "expr": "rate(event_gateway_webhook_deliveries_total[5m])",
            "legendFormat": "Webhook Deliveries - {{status}}"
          }
        ]
      }
    ]
  }
}
EOF

# Create distributed tracing dashboard
cat > grafana/provisioning/dashboards/tracing.json << EOF
{
  "dashboard": {
    "title": "OMS Distributed Tracing",
    "tags": ["oms", "tracing"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Service Dependencies",
        "gridPos": {"h": 12, "w": 24, "x": 0, "y": 0},
        "type": "nodeGraph",
        "targets": [
          {
            "query": "Service dependency graph from Jaeger"
          }
        ]
      },
      {
        "title": "Trace Timeline",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 12},
        "type": "trace",
        "targets": [
          {
            "query": "Recent traces"
          }
        ]
      }
    ]
  }
}
EOF

# Start monitoring stack
echo "Starting monitoring services..."
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 10

# Check service health
echo "Checking service status..."
curl -s http://localhost:9091/-/healthy > /dev/null && echo "✅ Prometheus is healthy" || echo "❌ Prometheus is not healthy"
curl -s http://localhost:3000/api/health > /dev/null && echo "✅ Grafana is healthy" || echo "❌ Grafana is not healthy"
curl -s http://localhost:16686/ > /dev/null && echo "✅ Jaeger is healthy" || echo "❌ Jaeger is not healthy"

echo ""
echo "📊 Monitoring stack is ready!"
echo ""
echo "Access points:"
echo "  - Prometheus: http://localhost:9091"
echo "  - Grafana: http://localhost:3000 (admin/admin)"
echo "  - Jaeger UI: http://localhost:16686"
echo "  - AlertManager: http://localhost:9093"
echo ""
echo "To view all services with monitoring:"
echo "  docker-compose -f docker-compose.yml -f docker-compose.microservices.yml -f monitoring/docker-compose.monitoring.yml up"