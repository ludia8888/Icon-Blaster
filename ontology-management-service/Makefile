# Makefile for OMS Integration Testing

.PHONY: help
help:
	@echo "OMS Commands:"
	@echo "Development:"
	@echo "  make proto               - Generate Python stubs from proto files"
	@echo "  make install             - Install dependencies"
	@echo "  make lint                - Run linters"
	@echo "  make run                 - Run the application"
	@echo ""
	@echo "Integration Testing:"
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

# Proto generation
.PHONY: proto
proto:
	@echo "Generating Python stubs from proto files..."
	@mkdir -p shared/proto_stubs
	@mkdir -p data_kernel/proto
	@mkdir -p services/embedding-service/proto
	# Data-Kernel proto
	python -m grpc_tools.protoc \
		-I data_kernel/proto \
		--python_out=shared/proto_stubs \
		--grpc_python_out=shared/proto_stubs \
		--pyi_out=shared/proto_stubs \
		data_kernel/proto/data_kernel.proto
	# Also generate for data_kernel module itself
	python -m grpc_tools.protoc \
		-I data_kernel/proto \
		--python_out=data_kernel/proto \
		--grpc_python_out=data_kernel/proto \
		--pyi_out=data_kernel/proto \
		data_kernel/proto/data_kernel.proto
	# Embedding service proto
	python -m grpc_tools.protoc \
		-I services/embedding-service/proto \
		--python_out=services/embedding-service/proto \
		--grpc_python_out=services/embedding-service/proto \
		--pyi_out=services/embedding-service/proto \
		services/embedding-service/proto/embedding_service.proto
	# Create __init__.py files
	@touch shared/proto_stubs/__init__.py
	@touch services/embedding-service/proto/__init__.py
	@echo "Proto stubs generated successfully!"

# Install dependencies
.PHONY: install
install:
	pip install -r requirements.txt
	@if [ -f data_kernel/requirements.txt ]; then pip install -r data_kernel/requirements.txt; fi

# Run linters
.PHONY: lint
lint:
	ruff check .
	mypy .

# Run the application
.PHONY: run
run:
	python -m uvicorn bootstrap.app:app --reload --host 0.0.0.0 --port 8000

# Clean generated files
.PHONY: clean
clean:
	rm -rf shared/proto_stubs
	rm -f data_kernel/proto/*_pb2.py
	rm -f data_kernel/proto/*_pb2_grpc.py
	rm -f data_kernel/proto/*_pb2.pyi
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete