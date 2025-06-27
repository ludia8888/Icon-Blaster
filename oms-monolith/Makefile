# Makefile for OMS Integration Testing

.PHONY: help
help:
	@echo "OMS Integration Test Commands:"
	@echo "  make integration-up      - Start all services for integration testing"
	@echo "  make integration-test    - Run integration tests"
	@echo "  make integration-down    - Stop and clean up all services"
	@echo "  make integration-logs    - Show logs from all services"
	@echo "  make integration-clean   - Clean up all data and volumes"
	@echo "  make test-audit-flow     - Test only the audit flow"
	@echo "  make test-resilience     - Test system resilience"
	@echo "  make verify-services     - Verify all services are healthy"

# Docker compose file
COMPOSE_FILE := docker-compose.integration.yml
COMPOSE := docker-compose -f $(COMPOSE_FILE)

.PHONY: integration-up
integration-up:
	@echo "🚀 Starting integration test environment..."
	$(COMPOSE) up -d
	@echo "⏳ Waiting for services to be ready..."
	@sleep 10
	@make verify-services

.PHONY: integration-test
integration-test:
	@echo "🧪 Running integration tests..."
	@python -m pytest tests/integration/test_real_msa_flow.py -v -s

.PHONY: integration-down
integration-down:
	@echo "🛑 Stopping integration test environment..."
	$(COMPOSE) down

.PHONY: integration-logs
integration-logs:
	$(COMPOSE) logs -f

.PHONY: integration-clean
integration-clean:
	@echo "🧹 Cleaning up integration test environment..."
	$(COMPOSE) down -v
	@rm -rf test-results/

.PHONY: verify-services
verify-services:
	@echo "🔍 Verifying service health..."
	@echo -n "OMS Service: "
	@curl -s http://localhost:18000/health | jq -r '.status' || echo "❌ Not ready"
	@echo -n "Audit Service: "
	@curl -s http://localhost:18001/health | jq -r '.status' || echo "❌ Not ready"
	@echo -n "TerminusDB: "
	@curl -s http://localhost:16363/api/status | jq -r '.terminusdb' || echo "❌ Not ready"
	@echo -n "NATS: "
	@curl -s http://localhost:18222/healthz | grep -q "ok" && echo "✅ Healthy" || echo "❌ Not ready"
	@echo -n "PostgreSQL: "
	@docker exec oms-test-postgres pg_isready -U audit_user -d audit_db | grep -q "accepting connections" && echo "✅ Healthy" || echo "❌ Not ready"
	@echo -n "Redis: "
	@docker exec oms-test-redis redis-cli -a redis123 ping | grep -q "PONG" && echo "✅ Healthy" || echo "❌ Not ready"

.PHONY: test-audit-flow
test-audit-flow:
	@echo "🔄 Testing audit flow only..."
	@python tests/integration/test_real_msa_flow.py test_complete_audit_flow

.PHONY: test-resilience
test-resilience:
	@echo "💪 Testing system resilience..."
	@python tests/integration/test_real_msa_flow.py test_resilience

# Development helpers
.PHONY: shell-oms
shell-oms:
	@docker exec -it oms-test-service /bin/bash

.PHONY: shell-audit
shell-audit:
	@docker exec -it oms-test-audit-service /bin/bash

.PHONY: db-shell
db-shell:
	@docker exec -it oms-test-postgres psql -U audit_user -d audit_db

.PHONY: redis-shell
redis-shell:
	@docker exec -it oms-test-redis redis-cli -a redis123

# Quick test cycle
.PHONY: quick-test
quick-test: integration-up integration-test integration-down

# Full test with cleanup
.PHONY: full-test
full-test: integration-clean integration-up integration-test integration-clean