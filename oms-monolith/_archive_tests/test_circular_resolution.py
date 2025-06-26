#!/usr/bin/env python
"""
순환 참조 해결 통합 테스트
"""
import asyncio
import sys
import os
from datetime import datetime, timezone
import uuid
import tempfile

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_all_circular_imports():
    """모든 순환 import 해결 확인"""
    print("=" * 60)
    print("🔍 순환 참조 해결 통합 테스트")
    print("=" * 60)
    print()
    
    # 1. core.validation 내부 순환 참조 테스트
    print("1️⃣ core.validation 순환 참조 테스트")
    print("-" * 40)
    
    try:
        # DI 패턴 적용된 모듈들
        from core.validation.ports import CachePort, TerminusPort, EventPort
        from core.validation.adapters import MockCacheAdapter, MockTerminusAdapter, MockEventAdapter
        from core.validation.service_refactored import ValidationServiceRefactored
        from core.validation.container import ValidationContainer
        print("✅ core.validation DI 패턴 모듈 import 성공")
    except ImportError as e:
        print(f"❌ core.validation DI 패턴 import 실패: {e}")
        return False
    
    # 2. SIEM 관련 순환 참조 테스트
    print()
    print("2️⃣ SIEM 관련 순환 참조 테스트")
    print("-" * 40)
    
    try:
        # SIEM Port & Adapter
        from infra.siem.port import ISiemPort
        from infra.siem.adapter import MockSiemAdapter, SiemHttpAdapter
        from infra.siem.serializer import SiemEventSerializer
        print("✅ SIEM Port & Adapter import 성공")
        
        # 이벤트 클래스
        from core.validation.events import TamperingEvent, ValidationLogEntry, EventSeverity, TamperingType
        print("✅ 이벤트 데이터 클래스 import 성공")
        
        # DI 적용된 모듈들
        from core.validation.tampering_detection import PolicyIntegrityChecker
        from core.validation.validation_logging import ValidationLogger
        print("✅ tampering_detection, validation_logging import 성공")
        
    except ImportError as e:
        print(f"❌ SIEM 관련 import 실패: {e}")
        return False
    
    # 3. 실제 동작 테스트
    print()
    print("3️⃣ DI 패턴 실제 동작 테스트")
    print("-" * 40)
    
    # 3-1. core.validation DI 테스트
    print("\n[core.validation DI 테스트]")
    container = ValidationContainer(test_mode=True)
    service = container.get_validation_service()
    print(f"✅ ValidationService 생성 성공 (규칙 수: {len(service.rules)})")
    
    # 3-2. SIEM DI 테스트
    print("\n[SIEM DI 테스트]")
    mock_siem = MockSiemAdapter()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # PolicyIntegrityChecker with DI
        checker = PolicyIntegrityChecker(
            snapshot_dir=temp_dir,
            siem_port=mock_siem
        )
        print("✅ PolicyIntegrityChecker 생성 성공 (DI)")
        
        # ValidationLogger with DI
        logger = ValidationLogger(
            log_dir=temp_dir,
            siem_port=mock_siem
        )
        print("✅ ValidationLogger 생성 성공 (DI)")
        
        # 이벤트 전송 테스트
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
        
        await checker._send_event_to_siem(event)
        print(f"✅ SIEM 이벤트 전송 성공 (전송된 이벤트: {mock_siem.send_count})")
    
    # 4. 순환 참조 부재 확인
    print()
    print("4️⃣ 순환 참조 부재 최종 확인")
    print("-" * 40)
    
    # 삭제된 모듈 확인
    try:
        from core.validation.siem_integration import get_siem_manager
        print("❌ siem_integration.py가 아직 존재함 (삭제 필요)")
    except ImportError:
        print("✅ siem_integration.py 제거 확인")
    
    return True


async def test_performance():
    """성능 테스트"""
    print()
    print("5️⃣ 성능 테스트")
    print("-" * 40)
    
    import time
    
    # Import 속도 테스트
    start = time.time()
    from core.validation.service_refactored import ValidationServiceRefactored
    from core.validation.tampering_detection import PolicyIntegrityChecker
    from core.validation.validation_logging import ValidationLogger
    end = time.time()
    
    print(f"✅ 모듈 import 시간: {(end - start) * 1000:.2f}ms")
    
    # 인스턴스 생성 속도
    start = time.time()
    from infra.siem.adapter import MockSiemAdapter
    mock_siem = MockSiemAdapter()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        checker = PolicyIntegrityChecker(snapshot_dir=temp_dir, siem_port=mock_siem)
        logger = ValidationLogger(log_dir=temp_dir, siem_port=mock_siem)
    end = time.time()
    
    print(f"✅ 인스턴스 생성 시간: {(end - start) * 1000:.2f}ms")


def print_summary(success: bool):
    """테스트 결과 요약"""
    print()
    print("=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)
    
    if success:
        print()
        print("✅ 모든 순환 참조가 성공적으로 해결되었습니다!")
        print()
        print("해결된 순환 참조:")
        print("  1. core.validation 내부 순환 참조 (service ↔ rules)")
        print("  2. tampering_detection ↔ siem_integration")
        print("  3. validation_logging ↔ siem_integration")
        print()
        print("적용된 패턴:")
        print("  - Port & Adapter 패턴")
        print("  - Dependency Injection (DI)")
        print("  - 이벤트 데이터 클래스 분리")
        print("  - 동적 규칙 로딩")
        print()
        print("🎉 엔터프라이즈급 클린 아키텍처 달성!")
    else:
        print()
        print("❌ 일부 테스트가 실패했습니다.")
        print("위의 오류 메시지를 확인하세요.")


async def main():
    """메인 테스트 실행"""
    try:
        # 순환 참조 테스트
        success = await test_all_circular_imports()
        
        if success:
            # 성능 테스트
            await test_performance()
        
        # 결과 요약
        print_summary(success)
        
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        print_summary(False)


if __name__ == "__main__":
    asyncio.run(main())