"""
Tests for Structured Logging Module
구조화 로깅 모듈 테스트
"""
import pytest
import json
import os
import logging
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from io import StringIO

from utils.logger import (
    StructuredFormatter, StructuredLoggerAdapter, LogLevel,
    get_logger, get_structured_logger, 
    log_operation_start, log_operation_end, log_validation_result, log_performance_metric,
    configure_production_logging, configure_development_logging
)


class TestLogLevel:
    """LogLevel Enum 테스트"""
    
    def test_log_level_values(self):
        """로그 레벨 값 테스트"""
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"


class TestStructuredFormatter:
    """StructuredFormatter 클래스 테스트"""
    
    def test_formatter_initialization(self):
        """포맷터 초기화 테스트"""
        formatter = StructuredFormatter("test-service", "1.2.3")
        assert formatter.service_name == "test-service"
        assert formatter.version == "1.2.3"
    
    def test_basic_log_formatting(self):
        """기본 로그 포맷팅 테스트"""
        formatter = StructuredFormatter()
        
        # 로그 레코드 생성
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function"
        )
        
        # 포맷팅
        formatted = formatter.format(record)
        
        # JSON 파싱 가능한지 확인
        log_data = json.loads(formatted)
        
        # 기본 필드 확인
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"
        assert log_data["logger"] == "test.logger"
        assert "@timestamp" in log_data
        assert "@version" in log_data
        
        # UTC 타임스탬프인지 확인
        timestamp = log_data["@timestamp"]
        assert "+" in timestamp or timestamp.endswith("Z")
        
        # 서비스 정보 확인
        assert "service" in log_data
        assert log_data["service"]["name"] == "oms-monolith"
        
        # 소스 정보 확인
        assert "source" in log_data
        assert log_data["source"]["file"] == "/test/file.py"
        assert log_data["source"]["line"] == 42
        assert log_data["source"]["function"] == "test_function"
    
    def test_exception_formatting(self):
        """예외 정보 포맷팅 테스트"""
        formatter = StructuredFormatter()
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="/test/file.py",
            lineno=42,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
            func="test_function"
        )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # 예외 정보 확인
        assert "exception" in log_data
        assert log_data["exception"]["class"] == "ValueError"
        assert log_data["exception"]["message"] == "Test exception"
        assert "stack_trace" in log_data["exception"]
    
    def test_custom_fields_formatting(self):
        """커스텀 필드 포맷팅 테스트"""
        formatter = StructuredFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function"
        )
        
        # 커스텀 필드 추가
        record.user_id = "test-user"
        record.operation_id = "op-123"
        record.custom_data = {"key": "value"}
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # 커스텀 필드 확인
        assert "fields" in log_data
        assert log_data["fields"]["user_id"] == "test-user"
        assert log_data["fields"]["operation_id"] == "op-123"
        assert log_data["fields"]["custom_data"] == {"key": "value"}
    
    @patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "AWS_REGION": "us-west-2",
        "DEPLOYMENT_ID": "prod-123",
        "HOSTNAME": "prod-server-01",
        "HOST_IP": "10.0.1.100"
    })
    def test_environment_information(self):
        """환경 정보 포맷팅 테스트"""
        formatter = StructuredFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function"
        )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # 환경 정보 확인
        assert log_data["environment"]["stage"] == "production"
        assert log_data["environment"]["region"] == "us-west-2"
        assert log_data["environment"]["deployment"] == "prod-123"
        
        # 호스트 정보 확인
        assert log_data["host"]["name"] == "prod-server-01"
        assert log_data["host"]["ip"] == "10.0.1.100"
    
    def test_json_serialization_fallback(self):
        """JSON 직렬화 실패 시 fallback 테스트"""
        formatter = StructuredFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function"
        )
        
        # 직렬화할 수 없는 객체 추가
        class UnserializableObject:
            def __str__(self):
                raise Exception("Cannot convert to string")
        
        record.bad_field = UnserializableObject()
        
        # 포맷팅 시도 (fallback이 동작해야 함)
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # fallback 데이터 확인
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"
        assert "error" in log_data
        assert "JSON serialization failed" in log_data["error"]


class TestStructuredLoggerAdapter:
    """StructuredLoggerAdapter 클래스 테스트"""
    
    def test_adapter_initialization(self):
        """어댑터 초기화 테스트"""
        logger = logging.getLogger("test")
        context = {"user_id": "test-user", "request_id": "req-123"}
        
        adapter = StructuredLoggerAdapter(logger, context)
        assert adapter.logger is logger
        assert adapter.extra == context
    
    def test_context_processing(self):
        """컨텍스트 처리 테스트"""
        logger = logging.getLogger("test")
        context = {"user_id": "test-user"}
        
        adapter = StructuredLoggerAdapter(logger, context)
        
        # 메시지 처리
        msg, kwargs = adapter.process("Test message", {})
        assert kwargs["extra"] == context
        
        # 기존 extra와 병합
        msg, kwargs = adapter.process("Test message", {"extra": {"request_id": "req-123"}})
        assert kwargs["extra"]["user_id"] == "test-user"
        assert kwargs["extra"]["request_id"] == "req-123"
    
    def test_with_context(self):
        """컨텍스트 추가 테스트"""
        logger = logging.getLogger("test")
        initial_context = {"user_id": "test-user"}
        
        adapter = StructuredLoggerAdapter(logger, initial_context)
        new_adapter = adapter.with_context(request_id="req-123", operation="test")
        
        # 새 어댑터가 추가 컨텍스트를 포함하는지 확인
        assert new_adapter.extra["user_id"] == "test-user"
        assert new_adapter.extra["request_id"] == "req-123"
        assert new_adapter.extra["operation"] == "test"
        
        # 원본 어댑터는 변경되지 않았는지 확인
        assert "request_id" not in adapter.extra
        assert "operation" not in adapter.extra


class TestLoggerFunctions:
    """로거 함수 테스트"""
    
    def setup_method(self):
        """테스트 메소드 셋업"""
        # 로거 캐시 클리어
        logging.Logger.manager.loggerDict.clear()
    
    def test_get_logger_default(self):
        """기본 로거 생성 테스트"""
        logger = get_logger("test.logger")
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.logger"
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
    
    @patch.dict(os.environ, {"LOG_FORMAT": "json"})
    def test_get_logger_json_format(self):
        """JSON 포맷 로거 생성 테스트"""
        logger = get_logger("test.json.logger")
        
        # JSON 포맷터가 사용되는지 확인
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, StructuredFormatter)
    
    @patch.dict(os.environ, {"LOG_FORMAT": "text"})
    def test_get_logger_text_format(self):
        """텍스트 포맷 로거 생성 테스트"""
        logger = get_logger("test.text.logger")
        
        # 텍스트 포맷터가 사용되는지 확인
        handler = logger.handlers[0]
        assert not isinstance(handler.formatter, StructuredFormatter)
    
    def test_get_logger_with_level(self):
        """로그 레벨 설정 테스트"""
        # 문자열 레벨
        logger1 = get_logger("test.level1", level="DEBUG")
        assert logger1.level == logging.DEBUG
        
        # Enum 레벨
        logger2 = get_logger("test.level2", level=LogLevel.ERROR)
        assert logger2.level == logging.ERROR
    
    def test_get_structured_logger(self):
        """구조화 로거 어댑터 생성 테스트"""
        context = {"service": "test-service", "version": "1.0.0"}
        adapter = get_structured_logger("test.structured", context=context)
        
        assert isinstance(adapter, StructuredLoggerAdapter)
        assert adapter.extra == context
    
    def test_logger_reuse(self):
        """로거 재사용 테스트"""
        logger1 = get_logger("test.reuse")
        logger2 = get_logger("test.reuse")
        
        # 동일한 인스턴스 반환
        assert logger1 is logger2
        
        # 핸들러가 중복 추가되지 않음
        assert len(logger1.handlers) == 1


class TestLoggingUtilities:
    """로깅 유틸리티 함수 테스트"""
    
    def setup_method(self):
        """테스트 메소드 셋업"""
        self.logger = get_logger("test.utilities", use_json=True)
        self.log_output = StringIO()
        
        # 핸들러를 StringIO로 변경
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        handler = logging.StreamHandler(self.log_output)
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
    
    def test_log_operation_start(self):
        """작업 시작 로그 테스트"""
        log_operation_start(
            self.logger, 
            "user_registration", 
            user_id="user-123", 
            email="test@example.com"
        )
        
        log_line = self.log_output.getvalue().strip()
        log_data = json.loads(log_line)
        
        assert log_data["level"] == "INFO"
        assert "Starting operation: user_registration" in log_data["message"]
        assert log_data["fields"]["operation"] == "user_registration"
        assert log_data["fields"]["operation_status"] == "started"
        assert log_data["fields"]["user_id"] == "user-123"
        assert log_data["fields"]["email"] == "test@example.com"
        assert "start_time" in log_data["fields"]
    
    def test_log_operation_end_success(self):
        """작업 완료 로그 테스트 (성공)"""
        log_operation_end(
            self.logger,
            "user_registration",
            success=True,
            duration=1.234,
            user_id="user-123"
        )
        
        log_line = self.log_output.getvalue().strip()
        log_data = json.loads(log_line)
        
        assert log_data["level"] == "INFO"
        assert "Operation completed: user_registration" in log_data["message"]
        assert log_data["fields"]["operation"] == "user_registration"
        assert log_data["fields"]["operation_status"] == "completed"
        assert log_data["fields"]["duration_ms"] == 1234.0
        assert log_data["fields"]["user_id"] == "user-123"
    
    def test_log_operation_end_failure(self):
        """작업 완료 로그 테스트 (실패)"""
        log_operation_end(
            self.logger,
            "user_registration",
            success=False,
            error_code="VALIDATION_ERROR"
        )
        
        log_line = self.log_output.getvalue().strip()
        log_data = json.loads(log_line)
        
        assert log_data["level"] == "ERROR"
        assert "Operation failed: user_registration" in log_data["message"]
        assert log_data["fields"]["operation_status"] == "failed"
        assert log_data["fields"]["error_code"] == "VALIDATION_ERROR"
    
    def test_log_validation_result_valid(self):
        """검증 결과 로그 테스트 (유효)"""
        log_validation_result(
            self.logger,
            "naming_convention",
            "test-convention",
            True,
            rule_count=5
        )
        
        log_line = self.log_output.getvalue().strip()
        log_data = json.loads(log_line)
        
        assert log_data["level"] == "INFO"
        assert "Validation passed" in log_data["message"]
        assert log_data["fields"]["validation_target"] == "naming_convention"
        assert log_data["fields"]["entity_id"] == "test-convention"
        assert log_data["fields"]["validation_result"] == "valid"
        assert log_data["fields"]["rule_count"] == 5
    
    def test_log_validation_result_invalid(self):
        """검증 결과 로그 테스트 (무효)"""
        errors = ["Missing required field: name", "Invalid pattern format"]
        
        log_validation_result(
            self.logger,
            "naming_convention",
            "invalid-convention",
            False,
            errors
        )
        
        log_line = self.log_output.getvalue().strip()
        log_data = json.loads(log_line)
        
        assert log_data["level"] == "WARNING"
        assert "Validation failed" in log_data["message"]
        assert log_data["fields"]["validation_result"] == "invalid"
        assert log_data["fields"]["validation_errors"] == errors
    
    def test_log_performance_metric(self):
        """성능 메트릭 로그 테스트"""
        log_performance_metric(
            self.logger,
            "response_time",
            250.5,
            "ms",
            endpoint="/api/conventions",
            method="GET"
        )
        
        log_line = self.log_output.getvalue().strip()
        log_data = json.loads(log_line)
        
        assert log_data["level"] == "INFO"
        assert "Performance metric: response_time" in log_data["message"]
        assert log_data["fields"]["metric_type"] == "performance"
        assert log_data["fields"]["metric_name"] == "response_time"
        assert log_data["fields"]["metric_value"] == 250.5
        assert log_data["fields"]["metric_unit"] == "ms"
        assert log_data["fields"]["endpoint"] == "/api/conventions"
        assert log_data["fields"]["method"] == "GET"


class TestEnvironmentConfiguration:
    """환경 설정 테스트"""
    
    def test_configure_production_logging(self):
        """프로덕션 로깅 설정 테스트"""
        with patch.dict(os.environ, {}, clear=True):
            configure_production_logging()
            
            assert os.environ["LOG_FORMAT"] == "json"
            
            # 외부 라이브러리 로그 레벨 확인
            assert logging.getLogger("urllib3").level == logging.WARNING
            assert logging.getLogger("requests").level == logging.WARNING
            assert logging.getLogger("boto3").level == logging.WARNING
            assert logging.getLogger("botocore").level == logging.WARNING
    
    def test_configure_development_logging(self):
        """개발 로깅 설정 테스트"""
        with patch.dict(os.environ, {}, clear=True):
            configure_development_logging()
            
            assert os.environ["LOG_FORMAT"] == "text"
    
    @patch.dict(os.environ, {"ENVIRONMENT": "production"})
    def test_auto_production_configuration(self):
        """자동 프로덕션 설정 테스트"""
        # 모듈 재임포트로 자동 설정 테스트
        import importlib
        import utils.logger
        importlib.reload(utils.logger)
        
        assert os.environ.get("LOG_FORMAT") == "json"
    
    @patch.dict(os.environ, {"ENVIRONMENT": "development"})
    def test_auto_development_configuration(self):
        """자동 개발 설정 테스트"""
        # 모듈 재임포트로 자동 설정 테스트
        import importlib
        import utils.logger
        importlib.reload(utils.logger)
        
        assert os.environ.get("LOG_FORMAT") == "text"


class TestIntegration:
    """통합 테스트"""
    
    def test_end_to_end_structured_logging(self):
        """엔드투엔드 구조화 로깅 테스트"""
        # JSON 포맷 로거 생성
        logger = get_structured_logger(
            "integration.test",
            context={
                "request_id": "req-12345",
                "user_id": "user-67890"
            },
            use_json=True
        )
        
        # 로그 출력 캡처
        log_output = StringIO()
        handler = logging.StreamHandler(log_output)
        handler.setFormatter(StructuredFormatter("integration-service", "2.0.0"))
        logger.logger.handlers = [handler]
        
        # 다양한 로그 생성
        logger.info("User login attempt", extra={
            "email": "user@example.com",
            "ip_address": "192.168.1.100"
        })
        
        logger.warning("Rate limit approaching", extra={
            "current_requests": 95,
            "limit": 100
        })
        
        try:
            raise ValueError("Database connection failed")
        except ValueError:
            logger.error("Login failed due to database error", exc_info=True)
        
        # 로그 출력 분석
        log_lines = log_output.getvalue().strip().split('\n')
        assert len(log_lines) == 3
        
        # 각 로그 라인이 유효한 JSON인지 확인
        for line in log_lines:
            log_data = json.loads(line)
            
            # 공통 필드 확인
            assert "@timestamp" in log_data
            assert log_data["service"]["name"] == "integration-service"
            assert log_data["service"]["version"] == "2.0.0"
            
            # 컨텍스트 정보 확인
            assert log_data["fields"]["request_id"] == "req-12345"
            assert log_data["fields"]["user_id"] == "user-67890"
        
        # 첫 번째 로그 (info)
        info_log = json.loads(log_lines[0])
        assert info_log["level"] == "INFO"
        assert info_log["fields"]["email"] == "user@example.com"
        
        # 두 번째 로그 (warning)
        warning_log = json.loads(log_lines[1])
        assert warning_log["level"] == "WARNING"
        assert warning_log["fields"]["current_requests"] == 95
        
        # 세 번째 로그 (error with exception)
        error_log = json.loads(log_lines[2])
        assert error_log["level"] == "ERROR"
        assert "exception" in error_log
        assert error_log["exception"]["class"] == "ValueError"
    
    def test_backward_compatibility(self):
        """기존 코드와의 하위 호환성 테스트"""
        # 기존 방식으로 로거 사용
        logger = get_logger("compatibility.test")
        
        # 기본 로깅 메소드들이 정상 작동하는지 확인
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")
        
        # 예외와 함께 로그
        try:
            raise RuntimeError("Test exception")
        except RuntimeError:
            logger.exception("Exception occurred")
        
        # 포맷 문자열 사용
        logger.info("User %s logged in from %s", "testuser", "192.168.1.1")
        
        # extra 파라미터 사용
        logger.info("Operation completed", extra={"duration": 123, "status": "success"})
        
        # 모든 호출이 예외 없이 완료되어야 함
        assert True  # 여기까지 도달하면 성공


class TestPerformance:
    """성능 테스트"""
    
    def test_logging_performance(self):
        """로깅 성능 테스트"""
        import time
        
        logger = get_logger("performance.test", use_json=True)
        
        # 로그 출력을 /dev/null로 리디렉션 (성능 측정을 위해)
        null_handler = logging.NullHandler()
        logger.handlers = [null_handler]
        
        # 1000개 로그 메시지 생성 시간 측정
        start_time = time.time()
        
        for i in range(1000):
            logger.info(f"Performance test message {i}", extra={
                "iteration": i,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"key": f"value_{i}"}
            })
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 1000개 로그가 1초 이내에 처리되어야 함 (매우 관대한 임계값)
        assert duration < 1.0, f"Logging too slow: {duration:.3f}s for 1000 messages"
        
        # 평균 로그 생성 시간 계산
        avg_time_per_log = duration / 1000
        print(f"Average time per log: {avg_time_per_log * 1000:.2f}ms")