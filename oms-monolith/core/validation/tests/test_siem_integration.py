"""
SIEM Integration Tests
중앙 SIEM 연동 감사 로그 전송 테스트
"""
import json
import tempfile
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest

from core.validation.siem_integration import (
    SIEMPlatform, SIEMFormat, SeverityLevel, SIEMEvent, SIEMConfig,
    SIEMFormatter, SIEMEventConverter, SIEMTransmitter, SIEMIntegrationManager
)
from core.validation.validation_logging import (
    ValidationLogEntry, ValidationOutcome, get_validation_logger
)
from core.validation.tampering_detection import (
    TamperingEvent, TamperingAlert, get_integrity_checker
)
from core.validation.naming_convention import (
    EntityType, NamingConvention, get_naming_engine
)


class TestSIEMFormatter:
    """SIEM 포맷터 테스트"""
    
    def test_cef_formatting(self):
        """CEF 포맷 테스트"""
        formatter = SIEMFormatter(SIEMFormat.CEF)
        
        event = SIEMEvent(
            timestamp="2025-01-15T10:30:00Z",
            event_id="test-123",
            source="OMS-Test",
            event_type="naming_validation", 
            severity=SeverityLevel.HIGH,
            user_id="test_user",
            source_ip="192.168.1.100",
            entity_type="objectType",
            entity_name="TestEntity",
            action="validate_naming",
            outcome="failure",
            details={"convention_id": "default", "issues_count": 2}
        )
        
        cef_output = formatter.format_event(event)
        
        assert cef_output.startswith("CEF:0|OMS|Naming Convention Validator|1.0|naming_validation|")
        assert "validate_naming|8|" in cef_output  # severity 8 for HIGH
        assert "rt=2025-01-15T10:30:00Z" in cef_output
        assert "src=192.168.1.100" in cef_output
        assert "suser=test_user" in cef_output
        assert "outcome=failure" in cef_output
    
    def test_json_formatting(self):
        """JSON 포맷 테스트"""
        formatter = SIEMFormatter(SIEMFormat.JSON)
        
        event = SIEMEvent(
            timestamp="2025-01-15T10:30:00Z",
            event_id="test-123",
            source="OMS-Test",
            event_type="security_event",
            severity=SeverityLevel.CRITICAL,
            user_id="test_user",
            source_ip="192.168.1.100",
            entity_type="policy",
            entity_name="test_policy",
            action="tamper_detection",
            outcome="detected",
            details={"alert_level": "critical", "description": "Policy modified"}
        )
        
        json_output = formatter.format_event(event)
        parsed = json.loads(json_output)
        
        assert parsed["event_id"] == "test-123"
        assert parsed["event_type"] == "security_event"
        assert parsed["severity"] == "Critical"
        assert parsed["details"]["alert_level"] == "critical"
    
    def test_syslog_rfc5424_formatting(self):
        """Syslog RFC5424 포맷 테스트"""
        formatter = SIEMFormatter(SIEMFormat.SYSLOG_RFC5424)
        
        event = SIEMEvent(
            timestamp="2025-01-15T10:30:00Z",
            event_id="test-123",
            source="OMS-Test",
            event_type="naming_validation",
            severity=SeverityLevel.MEDIUM,
            user_id="test_user",
            source_ip=None,
            entity_type="objectType",
            entity_name="TestEntity",
            action="validate_naming",
            outcome="failure",
            details={"convention_id": "default"}
        )
        
        syslog_output = formatter.format_event(event)
        
        assert syslog_output.startswith("<132>1")  # priority 132 for facility 16, severity 4
        assert "2025-01-15T10:30:00Z" in syslog_output
        assert "OMS-Naming" in syslog_output
        assert '[oms@32473 eventId="test-123"' in syslog_output
    
    def test_leef_formatting(self):
        """LEEF 포맷 테스트"""
        formatter = SIEMFormatter(SIEMFormat.LEEF)
        
        event = SIEMEvent(
            timestamp="2025-01-15T10:30:00Z",
            event_id="test-123",
            source="OMS-Test",
            event_type="policy_tampering",
            severity=SeverityLevel.CRITICAL,
            user_id=None,
            source_ip="unknown",
            entity_type="policy",
            entity_name="security_policy",
            action="tamper_detection",
            outcome="detected",
            details={"description": "Unauthorized modification"}
        )
        
        leef_output = formatter.format_event(event)
        
        assert leef_output.startswith("LEEF:2.0|OMS|Naming Validator|1.0|policy_tampering|^|")
        assert "devTime=2025-01-15T10:30:00Z" in leef_output
        assert "sev=10" in leef_output  # severity 10 for CRITICAL
        assert "cat=policy_tampering" in leef_output


class TestSIEMEventConverter:
    """SIEM 이벤트 변환기 테스트"""
    
    def test_validation_log_conversion(self):
        """검증 로그 변환 테스트"""
        converter = SIEMEventConverter()
        
        # 모의 검증 로그 생성
        log_entry = ValidationLogEntry(
            entity_type=EntityType.OBJECT_TYPE,
            entity_name="TestEntity",
            convention_id="default",
            outcome=ValidationOutcome.FAILURE,
            is_valid=False,
            issues=[{"rule_violated": "pattern", "message": "Invalid pattern"}],
            suggestions={"TestEntity": "TestEntity_Fixed"},
            user_id="test_user",
            validation_time_ms=5.2,
            metadata={"source_ip": "192.168.1.100", "security_issues": ["pattern_violation"]}
        )
        
        siem_event = converter.convert_validation_log(log_entry)
        
        assert siem_event.event_type == "naming_validation"
        assert siem_event.severity == SeverityLevel.MEDIUM  # failure -> medium
        assert siem_event.user_id == "test_user"
        assert siem_event.source_ip == "192.168.1.100"
        assert siem_event.entity_type == "objectType"
        assert siem_event.entity_name == "TestEntity"
        assert siem_event.action == "validate_naming"
        assert siem_event.outcome == "failure"
        assert siem_event.details["issues_count"] == 1
        assert siem_event.details["validation_time_ms"] == 5.2
    
    def test_tampering_event_conversion(self):
        """변조 이벤트 변환 테스트"""
        converter = SIEMEventConverter()
        
        # 모의 변조 이벤트 생성
        tamper_event = TamperingEvent(
            event_id="tamper-123",
            policy_id="test_policy",
            alert_level=TamperingAlert.CRITICAL,
            event_type="signature_verification_failed",
            description="Policy signature verification failed",
            timestamp="2025-01-15T10:30:00Z",
            details={"signer": "unknown", "signature_status": "invalid"}
        )
        
        siem_event = converter.convert_tampering_event(tamper_event)
        
        assert siem_event.event_type == "policy_tampering"
        assert siem_event.severity == SeverityLevel.CRITICAL
        assert siem_event.user_id is None  # 변조는 사용자 불명
        assert siem_event.entity_type == "policy"
        assert siem_event.entity_name == "test_policy"
        assert siem_event.action == "tamper_detection"
        assert siem_event.outcome == "detected"
        assert siem_event.details["alert_level"] == "critical"
        assert siem_event.details["description"] == "Policy signature verification failed"
    
    def test_security_event_conversion(self):
        """보안 이벤트 변환 테스트"""
        converter = SIEMEventConverter()
        
        event_data = {
            "timestamp": "2025-01-15T10:30:00Z",
            "user_id": "malicious_user",
            "source_ip": "192.168.1.100",
            "entity_type": "objectType",
            "entity_name": "'; DROP TABLE users; --",
            "action": "input_sanitization",
            "outcome": "blocked",
            "details": {
                "threats_detected": ["sql_injection", "suspicious_chars"],
                "risk_score": 85,
                "original_input": "'; DROP TABLE users; --Entity"
            }
        }
        
        siem_event = converter.convert_security_event(event_data)
        
        assert siem_event.event_type == "security_event"
        assert siem_event.severity == SeverityLevel.HIGH
        assert siem_event.user_id == "malicious_user"
        assert siem_event.action == "input_sanitization"
        assert siem_event.outcome == "blocked"
        assert siem_event.details["threats_detected"] == ["sql_injection", "suspicious_chars"]


class TestSIEMTransmitter:
    """SIEM 전송자 테스트"""
    
    def test_splunk_transmission(self):
        """Splunk 전송 테스트"""
        config = SIEMConfig(
            platform=SIEMPlatform.SPLUNK,
            format=SIEMFormat.JSON,
            endpoint="https://test-splunk:8088",
            api_key="test-token",
            index="test_index"
        )
        
        transmitter = SIEMTransmitter(config)
        
        # requests.post 모킹
        with patch('requests.post') as mock_post:
            mock_post.return_value.raise_for_status = Mock()
            
            event = SIEMEvent(
                timestamp="2025-01-15T10:30:00Z",
                event_id="test-123",
                source="test",
                event_type="test",
                severity=SeverityLevel.LOW,
                user_id="test",
                source_ip=None,
                entity_type="test",
                entity_name="test",
                action="test",
                outcome="test",
                details={}
            )
            
            # 배치 전송 시뮬레이션
            transmitter._send_to_splunk([transmitter.formatter.format_event(event)])
            
            # HTTP 요청 확인
            assert mock_post.called
            call_args = mock_post.call_args
            assert call_args[1]['headers']['Authorization'] == 'Splunk test-token'
            assert 'services/collector/event' in call_args[0][0]
    
    def test_webhook_transmission(self):
        """Webhook 전송 테스트"""
        config = SIEMConfig(
            platform=SIEMPlatform.WEBHOOK,
            format=SIEMFormat.JSON,
            endpoint="https://test-webhook.com/api/events",
            api_key="webhook-token",
            custom_headers={"X-Source": "OMS-Test"}
        )
        
        transmitter = SIEMTransmitter(config)
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.raise_for_status = Mock()
            
            event = SIEMEvent(
                timestamp="2025-01-15T10:30:00Z",
                event_id="webhook-test",
                source="test",
                event_type="test_event",
                severity=SeverityLevel.MEDIUM,
                user_id="webhook_user",
                source_ip="10.0.0.1",
                entity_type="test",
                entity_name="test_entity",
                action="test_action",
                outcome="success",
                details={"test_key": "test_value"}
            )
            
            transmitter._send_to_webhook([transmitter.formatter.format_event(event)])
            
            assert mock_post.called
            call_args = mock_post.call_args
            assert call_args[1]['headers']['Authorization'] == 'Bearer webhook-token'
            assert call_args[1]['headers']['X-Source'] == 'OMS-Test'
            
            # 전송된 데이터 확인
            sent_data = call_args[1]['json']
            assert 'events' in sent_data
            assert sent_data['source'] == 'oms-naming-validator'
    
    def test_syslog_transmission(self):
        """Syslog 전송 테스트"""
        config = SIEMConfig(
            platform=SIEMPlatform.GENERIC_SYSLOG,
            format=SIEMFormat.SYSLOG_RFC3164,
            endpoint="test-syslog-server",
            port=514
        )
        
        transmitter = SIEMTransmitter(config)
        
        # socket.socket 모킹
        with patch('socket.socket') as mock_socket:
            mock_sock = Mock()
            mock_socket.return_value = mock_sock
            
            event_message = "<134>Jan 15 10:30:00 hostname OMS-Naming: test message"
            transmitter._send_to_syslog([event_message])
            
            # socket 호출 확인
            mock_socket.assert_called_with(mock_socket.AF_INET, mock_socket.SOCK_DGRAM)
            mock_sock.sendto.assert_called_once()
            sent_data, address = mock_sock.sendto.call_args[0]
            assert sent_data == event_message.encode('utf-8')
            assert address == ("test-syslog-server", 514)


class TestSIEMIntegrationManager:
    """SIEM 통합 관리자 테스트"""
    
    def test_siem_config_loading(self):
        """SIEM 설정 로딩 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/siem_config.json"
            
            # 테스트 설정 생성
            test_config = {
                "siem_integrations": {
                    "test_splunk": {
                        "platform": "splunk",
                        "format": "json",
                        "endpoint": "https://test:8088",
                        "api_key": "test-key",
                        "batch_size": 10
                    },
                    "test_webhook": {
                        "platform": "webhook",
                        "format": "cef", 
                        "endpoint": "https://test-webhook/api",
                        "api_key": "webhook-key"
                    }
                }
            }
            
            with open(config_file, 'w') as f:
                json.dump(test_config, f)
            
            # 관리자 초기화
            manager = SIEMIntegrationManager(config_file)
            
            assert len(manager.configs) == 2
            assert "test_splunk" in manager.configs
            assert "test_webhook" in manager.configs
            
            splunk_config = manager.configs["test_splunk"]
            assert splunk_config.platform == SIEMPlatform.SPLUNK
            assert splunk_config.format == SIEMFormat.JSON
            assert splunk_config.batch_size == 10
    
    def test_validation_log_forwarding(self):
        """검증 로그 전달 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/siem_config.json"
            
            # 최소 설정
            test_config = {
                "siem_integrations": {
                    "test_siem": {
                        "platform": "webhook",
                        "format": "json",
                        "endpoint": "https://test/api",
                        "batch_size": 1,
                        "batch_timeout": 1
                    }
                }
            }
            
            with open(config_file, 'w') as f:
                json.dump(test_config, f)
            
            manager = SIEMIntegrationManager(config_file)
            
            # 전송자 모킹
            mock_transmitter = Mock()
            manager.transmitters["test_siem"] = mock_transmitter
            
            # 테스트 로그 생성
            log_entry = ValidationLogEntry(
                entity_type=EntityType.PROPERTY,
                entity_name="testProperty",
                convention_id="default",
                outcome=ValidationOutcome.SUCCESS,
                is_valid=True
            )
            
            # 로그 전송
            manager.send_validation_log(log_entry)
            
            # 전송 확인
            mock_transmitter.send_event.assert_called_once()
            sent_event = mock_transmitter.send_event.call_args[0][0]
            assert isinstance(sent_event, SIEMEvent)
            assert sent_event.event_type == "naming_validation"
    
    def test_tampering_event_forwarding(self):
        """변조 이벤트 전달 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/siem_config.json"
            
            test_config = {
                "siem_integrations": {
                    "security_siem": {
                        "platform": "webhook",
                        "format": "cef",
                        "endpoint": "https://security/api",
                        "batch_size": 1
                    }
                }
            }
            
            with open(config_file, 'w') as f:
                json.dump(test_config, f)
            
            manager = SIEMIntegrationManager(config_file)
            
            # 전송자 모킹
            mock_transmitter = Mock()
            manager.transmitters["security_siem"] = mock_transmitter
            
            # 변조 이벤트 생성
            tamper_event = TamperingEvent(
                event_id="tamper-456",
                policy_id="critical_policy",
                alert_level=TamperingAlert.CRITICAL,
                event_type="unauthorized_modification",
                description="Critical policy was modified without authorization",
                timestamp=datetime.now(timezone.utc).isoformat(),
                details={"modified_fields": ["rules", "reserved_words"]}
            )
            
            # 이벤트 전송
            manager.send_tampering_event(tamper_event)
            
            # 전송 확인
            mock_transmitter.send_event.assert_called_once()
            sent_event = mock_transmitter.send_event.call_args[0][0]
            assert sent_event.event_type == "policy_tampering"
            assert sent_event.severity == SeverityLevel.CRITICAL


class TestSIEMIntegrationWithValidationSystem:
    """검증 시스템과 SIEM 통합 테스트"""
    
    @patch.dict('os.environ', {'ENABLE_SIEM_INTEGRATION': 'true'})
    def test_validation_logging_siem_integration(self):
        """검증 로깅 SIEM 통합 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # SIEM 모킹
            with patch('core.validation.validation_logging._get_siem_manager') as mock_get_siem:
                mock_siem_manager = Mock()
                mock_get_siem.return_value = mock_siem_manager
                
                # 검증 로거 생성
                logger = get_validation_logger(temp_dir)
                engine = get_naming_engine()
                
                # 실패 케이스 검증
                result = engine.validate(EntityType.OBJECT_TYPE, "invalid_name")
                log_entry = logger.log_validation(
                    EntityType.OBJECT_TYPE,
                    "invalid_name",
                    result,
                    "default",
                    user_id="test_user",
                    metadata={"source_ip": "192.168.1.100"}
                )
                
                # SIEM 전송 확인
                mock_siem_manager.send_validation_log.assert_called_once()
                sent_log = mock_siem_manager.send_validation_log.call_args[0][0]
                assert sent_log.entity_name == "invalid_name"
                assert sent_log.outcome == ValidationOutcome.FAILURE
    
    @patch.dict('os.environ', {'ENABLE_SIEM_INTEGRATION': 'true'})
    def test_tampering_detection_siem_integration(self):
        """변조 감지 SIEM 통합 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # SIEM 모킹
            with patch('core.validation.tampering_detection._get_siem_manager') as mock_get_siem:
                mock_siem_manager = Mock()
                mock_get_siem.return_value = mock_siem_manager
                
                # 무결성 검증기 생성
                checker = get_integrity_checker(temp_dir)
                
                # 테스트 정책 생성
                policy = NamingConvention(
                    id="siem_test_policy",
                    name="Original Name",
                    rules={},
                    created_at="2025-01-15T00:00:00Z",
                    updated_at="2025-01-15T00:00:00Z",
                    created_by="test"
                )
                
                # 첫 번째 검사 (스냅샷 생성)
                checker.check_integrity(policy)
                
                # 정책 수정
                policy.name = "Modified Name"
                policy.updated_at = "2025-01-15T01:00:00Z"
                
                # 두 번째 검사 (변조 감지)
                is_valid, events = checker.check_integrity(policy)
                
                # SIEM 전송 확인
                assert len(events) > 0
                assert mock_siem_manager.send_tampering_event.call_count > 0


class TestSIEMEventFiltering:
    """SIEM 이벤트 필터링 테스트"""
    
    @patch.dict('os.environ', {'ENABLE_SIEM_INTEGRATION': 'true', 'SIEM_INCLUDE_SUCCESS': 'false'})
    def test_success_event_filtering(self):
        """성공 이벤트 필터링 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('core.validation.validation_logging._get_siem_manager') as mock_get_siem:
                mock_siem_manager = Mock()
                mock_get_siem.return_value = mock_siem_manager
                
                logger = get_validation_logger(temp_dir)
                engine = get_naming_engine()
                
                # 성공 케이스
                result = engine.validate(EntityType.OBJECT_TYPE, "ValidName")
                logger.log_validation(EntityType.OBJECT_TYPE, "ValidName", result, "default")
                
                # SIEM 전송이 호출되지 않아야 함
                mock_siem_manager.send_validation_log.assert_not_called()
    
    @patch.dict('os.environ', {'ENABLE_SIEM_INTEGRATION': 'true'})
    def test_security_event_always_sent(self):
        """보안 이벤트는 항상 전송되는지 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('core.validation.validation_logging._get_siem_manager') as mock_get_siem:
                mock_siem_manager = Mock()
                mock_get_siem.return_value = mock_siem_manager
                
                logger = get_validation_logger(temp_dir)
                
                # 보안 이슈가 있는 성공 케이스도 전송되어야 함
                result_mock = Mock()
                result_mock.is_valid = True
                result_mock.issues = []
                result_mock.suggestions = {}
                
                log_entry = logger.log_validation(
                    EntityType.PROPERTY,
                    "cleanedName",
                    result_mock,
                    "default",
                    metadata={"security_issues": ["sql_injection"], "was_sanitized": True}
                )
                
                # 보안 이슈가 있으므로 SIEM에 전송되어야 함
                mock_siem_manager.send_validation_log.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])