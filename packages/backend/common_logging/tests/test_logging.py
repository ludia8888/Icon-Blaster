"""Integration tests for common_logging package."""

import pytest
import json
import logging
import os
from io import StringIO
from unittest.mock import patch

from common_logging import (
    setup_logging, 
    JSONFormatter, 
    StructuredFormatter,
    TraceIDFilter,
    ServiceFilter,
    AuditFieldFilter
)
from common_logging.setup import (
    setup_development_logging,
    setup_production_logging,
    setup_audit_logging,
    get_logger
)
from common_logging.filters import (
    set_trace_id,
    set_correlation_id,
    get_trace_id,
    get_correlation_id,
    clear_trace_context
)


class TestJSONFormatter:
    """Test JSON formatter functionality."""
    
    def test_basic_formatting(self):
        """Test basic JSON log formatting."""
        formatter = JSONFormatter(service="test-service", version="1.0.0")
        
        # Create test log record
        logger = logging.getLogger("test.logger")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["service"] == "test-service"
        assert log_data["version"] == "1.0.0"
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["message"] == "Test message"
        assert "timestamp" in log_data
    
    def test_extra_fields(self):
        """Test extra fields in JSON formatting."""
        formatter = JSONFormatter(
            service="test-service",
            extra_fields={"environment": "test", "region": "us-east-1"}
        )
        
        logger = logging.getLogger("test.logger")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Add custom fields to record
        record.user_id = "user123"
        record.request_id = "req456"
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["environment"] == "test"
        assert log_data["region"] == "us-east-1"
        assert log_data["user_id"] == "user123"
        assert log_data["request_id"] == "req456"
    
    def test_exception_formatting(self):
        """Test exception formatting in JSON logs."""
        formatter = JSONFormatter(service="test-service")
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            logger = logging.getLogger("test.logger")
            record = logging.LogRecord(
                name="test.logger",
                level=logging.ERROR,
                pathname="test.py",
                lineno=10,
                msg="Test error",
                args=(),
                exc_info=logger.exception.__class__.__dict__.get('exc_info', None)
            )
            # Manually set exc_info for testing
            import sys
            record.exc_info = sys.exc_info()
            
            formatted = formatter.format(record)
            log_data = json.loads(formatted)
            
            assert "exception" in log_data
            assert log_data["exception"]["type"] == "ValueError"
            assert log_data["exception"]["message"] == "Test exception"
            assert isinstance(log_data["exception"]["traceback"], list)


class TestStructuredFormatter:
    """Test structured text formatter functionality."""
    
    def test_basic_formatting(self):
        """Test basic structured text formatting."""
        formatter = StructuredFormatter(service="test-service")
        
        logger = logging.getLogger("test.logger")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        
        assert "[test-service]" in formatted
        assert "[INFO]" in formatted
        assert "[test.logger]" in formatted
        assert "Test message" in formatted
    
    def test_trace_id_formatting(self):
        """Test trace ID inclusion in structured formatting."""
        formatter = StructuredFormatter(service="test-service", include_trace=True)
        
        logger = logging.getLogger("test.logger")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Add trace ID
        record.trace_id = "trace-123456789"
        
        formatted = formatter.format(record)
        
        assert "[trace:trace-12]" in formatted  # First 8 characters


class TestFilters:
    """Test logging filters functionality."""
    
    def test_trace_id_filter(self):
        """Test trace ID filter functionality."""
        filter_obj = TraceIDFilter(auto_generate=True)
        
        logger = logging.getLogger("test.logger")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Apply filter
        result = filter_obj.filter(record)
        
        assert result is True
        assert hasattr(record, "trace_id")
        assert hasattr(record, "span_id")
        assert record.trace_id is not None
        assert record.span_id is not None
    
    def test_service_filter(self):
        """Test service filter functionality."""
        filter_obj = ServiceFilter(
            service="test-service",
            version="2.0.0",
            environment="production"
        )
        
        logger = logging.getLogger("test.logger")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Apply filter
        result = filter_obj.filter(record)
        
        assert result is True
        assert record.service == "test-service"
        assert record.version == "2.0.0"
        assert record.environment == "production"
    
    def test_audit_field_filter(self):
        """Test audit field filter functionality."""
        filter_obj = AuditFieldFilter(
            default_fields={"audit_type": "access", "compliance": "gdpr"}
        )
        
        logger = logging.getLogger("test.logger")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Apply filter
        result = filter_obj.filter(record)
        
        assert result is True
        assert record.audit_type == "access"
        assert record.compliance == "gdpr"
        assert hasattr(record, "event_type")
        assert hasattr(record, "user_id")
        assert hasattr(record, "action")


class TestSetupFunctions:
    """Test logging setup functions."""
    
    def test_basic_setup(self):
        """Test basic logging setup."""
        # Capture log output
        log_capture = StringIO()
        
        # Setup logging with custom handler
        handler = logging.StreamHandler(log_capture)
        setup_logging(
            service="test-service",
            version="1.0.0",
            level="INFO",
            format_type="json",
            handlers=[handler]
        )
        
        # Test logging
        logger = get_logger("test.module")
        logger.info("Test log message")
        
        # Verify output
        log_output = log_capture.getvalue()
        assert log_output.strip()
        
        # Parse JSON
        log_data = json.loads(log_output.strip())
        assert log_data["service"] == "test-service"
        assert log_data["version"] == "1.0.0"
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test log message"
    
    def test_development_setup(self):
        """Test development logging setup."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        
        setup_development_logging(
            service="dev-service",
            handlers=[handler]
        )
        
        logger = get_logger("dev.module")
        logger.debug("Debug message")
        
        log_output = log_capture.getvalue()
        assert log_output.strip()
        assert "[dev-service]" in log_output
        assert "[DEBUG]" in log_output
    
    def test_production_setup(self):
        """Test production logging setup."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        
        setup_production_logging(
            service="prod-service",
            handlers=[handler]
        )
        
        logger = get_logger("prod.module")
        logger.info("Production message")
        
        log_output = log_capture.getvalue()
        assert log_output.strip()
        
        # Should be JSON format
        log_data = json.loads(log_output.strip())
        assert log_data["service"] == "prod-service"
        assert log_data["environment"] == "production"
    
    def test_audit_setup(self):
        """Test audit logging setup."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        
        setup_audit_logging(
            service="audit-service",
            handlers=[handler]
        )
        
        logger = get_logger("audit.module")
        logger.info(
            "User action",
            extra={
                "event_type": "login",
                "user_id": "user123",
                "action": "authenticate",
                "result": "success"
            }
        )
        
        log_output = log_capture.getvalue()
        assert log_output.strip()
        
        # Should be JSON format with audit fields
        log_data = json.loads(log_output.strip())
        assert log_data["service"] == "audit-service"
        assert "audit" in log_data
        assert log_data["audit"]["event_type"] == "login"
        assert log_data["audit"]["user_id"] == "user123"


class TestTraceContext:
    """Test trace context functionality."""
    
    def test_trace_context_management(self):
        """Test trace context setting and retrieval."""
        # Clear any existing context
        clear_trace_context()
        
        # Set trace context
        set_trace_id("trace-123")
        set_correlation_id("corr-456")
        
        # Verify retrieval
        assert get_trace_id() == "trace-123"
        assert get_correlation_id() == "corr-456"
        
        # Clear context
        clear_trace_context()
        
        # Verify cleared
        assert get_trace_id() is None
        assert get_correlation_id() is None
    
    def test_trace_context_in_logging(self):
        """Test trace context integration in logging."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        
        setup_logging(
            service="trace-service",
            handlers=[handler],
            enable_trace=True
        )
        
        # Set trace context
        set_trace_id("trace-789")
        set_correlation_id("corr-012")
        
        # Log message
        logger = get_logger("trace.module")
        logger.info("Traced message")
        
        # Verify trace context in log
        log_output = log_capture.getvalue()
        log_data = json.loads(log_output.strip())
        
        assert log_data["trace_id"] == "trace-789"
        assert log_data["correlation_id"] == "corr-012"
        
        # Clear context
        clear_trace_context()


class TestEnvironmentIntegration:
    """Test environment variable integration."""
    
    def test_environment_variables(self):
        """Test logging configuration from environment variables."""
        # Set environment variables
        os.environ["LOG_LEVEL"] = "DEBUG"
        os.environ["LOG_FORMAT"] = "structured"
        os.environ["ENVIRONMENT"] = "test"
        
        try:
            log_capture = StringIO()
            handler = logging.StreamHandler(log_capture)
            
            setup_logging(
                service="env-service",
                handlers=[handler]
            )
            
            # Test debug logging
            logger = get_logger("env.module")
            logger.debug("Debug from env")
            
            log_output = log_capture.getvalue()
            assert log_output.strip()
            assert "[env-service]" in log_output
            assert "[DEBUG]" in log_output
            
        finally:
            # Clean up environment
            for key in ["LOG_LEVEL", "LOG_FORMAT", "ENVIRONMENT"]:
                if key in os.environ:
                    del os.environ[key]


class TestCompatibility:
    """Test compatibility with existing logging patterns."""
    
    def test_user_service_compatibility(self):
        """Test compatibility with user-service logging patterns."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        
        # Setup similar to user-service
        setup_logging(
            service="user-service",
            version="1.0.0",
            format_type="json",
            handlers=[handler]
        )
        
        logger = get_logger("user.auth")
        logger.info("User login", extra={"user_id": "user123"})
        
        log_output = log_capture.getvalue()
        log_data = json.loads(log_output.strip())
        
        assert log_data["service"] == "user-service"
        assert log_data["user_id"] == "user123"
    
    def test_oms_monolith_compatibility(self):
        """Test compatibility with oms-monolith logging patterns."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        
        # Setup similar to oms-monolith
        setup_logging(
            service="oms-monolith",
            version="2.0.0",
            format_type="json",
            enable_trace=True,
            handlers=[handler]
        )
        
        logger = get_logger("oms.validation")
        logger.info("Policy validated", extra={
            "policy_id": "policy123",
            "validation_result": "success"
        })
        
        log_output = log_capture.getvalue()
        log_data = json.loads(log_output.strip())
        
        assert log_data["service"] == "oms-monolith"
        assert log_data["policy_id"] == "policy123"
        assert log_data["validation_result"] == "success"
        assert "trace_id" in log_data


class TestIntegration:
    """Integration tests combining multiple features."""
    
    def test_end_to_end_logging_workflow(self):
        """Test complete end-to-end logging workflow."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        
        # Setup comprehensive logging
        setup_logging(
            service="integration-service",
            version="3.0.0",
            format_type="json",
            enable_trace=True,
            enable_audit=True,
            mask_sensitive=True,
            extra_fields={"deployment": "prod", "region": "us-west-2"},
            handlers=[handler]
        )
        
        # Set trace context
        set_trace_id("integration-trace-123")
        set_correlation_id("integration-corr-456")
        
        # Log various types of messages
        logger = get_logger("integration.workflow")
        
        # Standard info log
        logger.info("Workflow started", extra={"workflow_id": "wf123"})
        
        # Audit log
        logger.info("User action", extra={
            "event_type": "data_access",
            "user_id": "user789",
            "resource_id": "resource456",
            "action": "read",
            "result": "allowed"
        })
        
        # Error log
        logger.error("Workflow failed", extra={
            "workflow_id": "wf123",
            "error_code": "TIMEOUT",
            "duration_ms": 5000
        })
        
        # Verify all logs
        log_output = log_capture.getvalue()
        log_lines = log_output.strip().split('\n')
        
        assert len(log_lines) == 3
        
        # Verify each log entry
        for line in log_lines:
            log_data = json.loads(line)
            assert log_data["service"] == "integration-service"
            assert log_data["version"] == "3.0.0"
            assert log_data["deployment"] == "prod"
            assert log_data["region"] == "us-west-2"
            assert log_data["trace_id"] == "integration-trace-123"
            assert log_data["correlation_id"] == "integration-corr-456"
        
        # Verify specific log content
        info_log = json.loads(log_lines[0])
        assert info_log["message"] == "Workflow started"
        assert info_log["workflow_id"] == "wf123"
        
        audit_log = json.loads(log_lines[1])
        assert audit_log["message"] == "User action"
        assert "audit" in audit_log
        assert audit_log["audit"]["event_type"] == "data_access"
        
        error_log = json.loads(log_lines[2])
        assert error_log["level"] == "ERROR"
        assert error_log["error_code"] == "TIMEOUT"
        
        # Clear context
        clear_trace_context()