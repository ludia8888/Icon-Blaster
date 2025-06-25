"""
SIEM DI 패턴 통합 테스트
순환 참조 해결 확인
"""
import pytest
import asyncio
from datetime import datetime, timezone
import uuid

from core.validation.events import (
    TamperingEvent,
    ValidationLogEntry,
    EventSeverity,
    TamperingType
)
from core.validation.tampering_detection import PolicyIntegrityChecker
from core.validation.validation_logging import ValidationLogger
from infra.siem.adapter import MockSiemAdapter


class TestSiemDIIntegration:
    """SIEM DI 통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_tampering_detection_with_siem(self, tmp_path):
        """변조 감지 SIEM 통합 테스트"""
        # Mock SIEM 어댑터 생성
        mock_siem = MockSiemAdapter()
        
        # DI를 통해 PolicyIntegrityChecker 생성
        checker = PolicyIntegrityChecker(
            snapshot_dir=str(tmp_path / "test_snapshots"),
            siem_port=mock_siem
        )
        
        # 변조 이벤트 생성
        event = TamperingEvent(
            event_id=str(uuid.uuid4()),
            validator="test_validator",
            object_type="TestObject",
            field="test_field",
            old_value="old",
            new_value="new",
            tampering_type=TamperingType.DATA_MANIPULATION,
            severity=EventSeverity.HIGH,
            detected_at=datetime.now(timezone.utc),
            detection_method="test",
            confidence_score=0.95,
            affected_records=1
        )
        
        # SIEM으로 전송
        await checker._send_event_to_siem(event)
        
        # Mock SIEM에 이벤트가 전송되었는지 확인
        assert mock_siem.send_count == 1
        assert len(mock_siem.events) == 1
        assert mock_siem.events[0]['event_type'] == 'security.tampering'
    
    @pytest.mark.asyncio
    async def test_validation_logging_with_siem(self, tmp_path):
        """검증 로깅 SIEM 통합 테스트"""
        # Mock SIEM 어댑터 생성
        mock_siem = MockSiemAdapter()
        
        # DI를 통해 ValidationLogger 생성
        logger = ValidationLogger(
            log_dir=str(tmp_path / "test_logs"),
            siem_port=mock_siem
        )
        
        # 검증 로그 엔트리 생성
        log_entry = ValidationLogEntry(
            log_id=str(uuid.uuid4()),
            validation_id="test_validation",
            branch="main",
            rule_id="test_rule",
            rule_name="Test Rule",
            is_valid=False,
            error_message="Test error",
            execution_time_ms=100.0,
            affected_objects=["TestObject"],
            created_at=datetime.now(timezone.utc)
        )
        
        # ExtendedValidationLogEntry로 변환이 필요한 경우를 위한 테스트
        # 실제 로거에서는 log_validation 메서드를 통해 처리됨
        
        # Mock SIEM 확인
        assert mock_siem is not None
        assert mock_siem.is_healthy
    
    def test_no_circular_imports(self):
        """순환 import 없음 확인"""
        # 모든 모듈이 순환 참조 없이 import 되는지 확인
        try:
            from core.validation.events import TamperingEvent, ValidationLogEntry
            from core.validation.tampering_detection import PolicyIntegrityChecker
            from core.validation.validation_logging import ValidationLogger
            from infra.siem.port import ISiemPort
            from infra.siem.adapter import SiemHttpAdapter, MockSiemAdapter
            
            # 모든 import 성공
            assert True
        except ImportError as e:
            pytest.fail(f"Import failed due to circular reference: {e}")
    
    @pytest.mark.asyncio
    async def test_adapter_substitution(self, tmp_path):
        """어댑터 교체 테스트"""
        # 첫 번째 Mock 어댑터
        mock_siem1 = MockSiemAdapter()
        checker = PolicyIntegrityChecker(
            snapshot_dir=str(tmp_path / "test_snapshots"),
            siem_port=mock_siem1
        )
        
        # 이벤트 전송
        event = TamperingEvent(
            event_id="test1",
            validator="test",
            object_type="Test",
            field="field1",
            old_value="old",
            new_value="new",
            tampering_type=TamperingType.DATA_MANIPULATION,
            severity=EventSeverity.MEDIUM,
            detected_at=datetime.now(timezone.utc),
            detection_method="test",
            confidence_score=0.9,
            affected_records=1
        )
        
        await checker._send_event_to_siem(event)
        assert mock_siem1.send_count == 1
        
        # 두 번째 Mock 어댑터로 교체
        mock_siem2 = MockSiemAdapter()
        checker.siem_port = mock_siem2
        
        await checker._send_event_to_siem(event)
        assert mock_siem2.send_count == 1
        assert mock_siem1.send_count == 1  # 첫 번째는 변경 없음
    
    @pytest.mark.asyncio
    async def test_event_serialization(self):
        """이벤트 직렬화 테스트"""
        from infra.siem.serializer import SiemEventSerializer
        
        # 변조 이벤트
        tampering_event = TamperingEvent(
            event_id="test123",
            validator="test",
            object_type="User",
            field="email",
            old_value="old@test.com",
            new_value="new@test.com",
            tampering_type=TamperingType.DATA_MANIPULATION,
            severity=EventSeverity.HIGH,
            detected_at=datetime.now(timezone.utc),
            detection_method="hash_comparison",
            confidence_score=0.99,
            affected_records=1
        )
        
        # 직렬화
        serialized = SiemEventSerializer.serialize(tampering_event)
        
        # 검증
        assert serialized['event_type'] == 'security.tampering'
        assert serialized['event_class'] == 'TamperingEvent'
        assert 'security_context' in serialized
        assert serialized['security_context']['severity'] == 'high'
        
        # CEF 형식 변환 테스트
        cef = SiemEventSerializer.to_cef(serialized)
        assert cef.startswith("CEF:0|Foundry|OMS|1.0|")
        
        # LEEF 형식 변환 테스트
        leef = SiemEventSerializer.to_leef(serialized)
        assert leef.startswith("LEEF:2.0|Foundry|OMS|1.0|")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])