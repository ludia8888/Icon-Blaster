"""
SIEM 설정 및 DI 구성
"""
import os
from typing import Optional
from infra.siem.port import ISiemPort
from infra.siem.adapter import (
    SiemHttpAdapter,
    MockSiemAdapter,
    KafkaSiemAdapter,
    BufferedSiemAdapter
)


def get_siem_adapter() -> Optional[ISiemPort]:
    """
    환경 설정에 따라 적절한 SIEM 어댑터 반환
    """
    # SIEM 활성화 여부 확인
    if not os.getenv("ENABLE_SIEM_INTEGRATION", "true").lower() in ("true", "1", "yes"):
        return None
    
    # 테스트 모드
    if os.getenv("TEST_MODE", "false").lower() in ("true", "1", "yes"):
        return MockSiemAdapter()
    
    # SIEM 타입에 따라 적절한 어댑터 선택
    siem_type = os.getenv("SIEM_TYPE", "http").lower()
    
    if siem_type == "http":
        endpoint = os.getenv("SIEM_ENDPOINT", "http://localhost:8088/services/collector")
        token = os.getenv("SIEM_TOKEN", "")
        
        if not endpoint or not token:
            raise ValueError("SIEM_ENDPOINT and SIEM_TOKEN must be set for HTTP adapter")
        
        # 버퍼링 활성화 옵션
        if os.getenv("SIEM_BUFFERING", "true").lower() in ("true", "1", "yes"):
            base_adapter = SiemHttpAdapter(endpoint=endpoint, token=token)
            return BufferedSiemAdapter(
                base_adapter=base_adapter,
                buffer_size=int(os.getenv("SIEM_BUFFER_SIZE", "100")),
                flush_interval=float(os.getenv("SIEM_FLUSH_INTERVAL", "5.0"))
            )
        else:
            return SiemHttpAdapter(endpoint=endpoint, token=token)
    
    elif siem_type == "kafka":
        bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        topic = os.getenv("KAFKA_TOPIC", "oms-validation-events")
        return KafkaSiemAdapter(
            bootstrap_servers=bootstrap_servers,
            topic=topic
        )
    
    elif siem_type == "mock":
        return MockSiemAdapter()
    
    else:
        raise ValueError(f"Unknown SIEM type: {siem_type}")


# 싱글톤 인스턴스
_siem_adapter: Optional[ISiemPort] = None


def get_shared_siem_adapter() -> Optional[ISiemPort]:
    """
    공유 SIEM 어댑터 인스턴스 반환 (싱글톤)
    """
    global _siem_adapter
    if _siem_adapter is None:
        _siem_adapter = get_siem_adapter()
    return _siem_adapter