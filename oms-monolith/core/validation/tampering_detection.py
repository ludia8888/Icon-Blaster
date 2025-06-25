"""
Policy Tampering Detection System
정책 변조 감지 및 무결성 검증 시스템
"""
import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from pydantic import BaseModel, Field
import uuid

from core.validation.naming_convention import NamingConvention
from core.validation.policy_signing import SignedNamingPolicy, get_policy_signing_manager
from core.validation.events import TamperingEvent, TamperingType, EventSeverity
from infra.siem.port import ISiemPort
from utils.logger import get_logger

logger = get_logger(__name__)


class PolicySnapshot(BaseModel):
    """정책 스냅샷"""
    policy_id: str
    snapshot_hash: str
    content_hash: str  # 정책 내용 해시
    metadata_hash: str  # 메타데이터 해시
    file_hash: str  # 파일 전체 해시
    timestamp: str
    file_size: int
    file_mtime: float  # 파일 수정 시간
    signature_hash: Optional[str] = None  # 서명 해시 (서명된 정책의 경우)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


# TamperingEvent는 이제 events.py에서 import됨


class PolicyIntegrityChecker:
    """정책 무결성 검증자 (DI 패턴 적용)"""
    
    def __init__(self, snapshot_dir: str = "/etc/oms/snapshots", siem_port: Optional[ISiemPort] = None):
        """
        초기화
        
        Args:
            snapshot_dir: 스냅샷 저장 디렉토리
            siem_port: SIEM 포트 (의존성 주입)
        """
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.siem_port = siem_port
        
        # 이벤트 저장소
        self.events_file = self.snapshot_dir / "tampering_events.json"
        self.snapshots_file = self.snapshot_dir / "policy_snapshots.json"
        
        # 기존 데이터 로드
        self.snapshots = self._load_snapshots()
        self.events = self._load_events()
    
    def _load_snapshots(self) -> Dict[str, PolicySnapshot]:
        """저장된 스냅샷 로드"""
        if not self.snapshots_file.exists():
            return {}
        
        try:
            with open(self.snapshots_file, 'r') as f:
                data = json.load(f)
            
            snapshots = {}
            for policy_id, snapshot_data in data.items():
                snapshots[policy_id] = PolicySnapshot(**snapshot_data)
            
            return snapshots
        except Exception as e:
            logger.error(f"Failed to load snapshots: {e}")
            return {}
    
    def _save_snapshots(self):
        """스냅샷 저장"""
        try:
            data = {}
            for policy_id, snapshot in self.snapshots.items():
                data[policy_id] = snapshot.model_dump()
            
            with open(self.snapshots_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save snapshots: {e}")
    
    def _load_events(self) -> List[TamperingEvent]:
        """저장된 이벤트 로드"""
        if not self.events_file.exists():
            return []
        
        try:
            with open(self.events_file, 'r') as f:
                data = json.load(f)
            
            events = []
            for event_data in data:
                # 중첩된 객체 복원
                if event_data.get('previous_snapshot'):
                    event_data['previous_snapshot'] = PolicySnapshot(**event_data['previous_snapshot'])
                if event_data.get('current_snapshot'):
                    event_data['current_snapshot'] = PolicySnapshot(**event_data['current_snapshot'])
                
                events.append(TamperingEvent(**event_data))
            
            return events
        except Exception as e:
            logger.error(f"Failed to load events: {e}")
            return []
    
    def _save_events(self):
        """이벤트 저장"""
        try:
            data = []
            for event in self.events:
                data.append(event.model_dump())
            
            with open(self.events_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save events: {e}")
    
    def create_snapshot(
        self,
        policy: NamingConvention,
        file_path: Optional[Path] = None,
        signed_policy: Optional[SignedNamingPolicy] = None
    ) -> PolicySnapshot:
        """
        정책 스냅샷 생성
        
        Args:
            policy: 명명 규칙 정책
            file_path: 정책 파일 경로
            signed_policy: 서명된 정책 (있는 경우)
            
        Returns:
            생성된 스냅샷
        """
        # 정책 내용 해시
        policy_dict = policy.model_dump()
        policy_json = json.dumps(policy_dict, sort_keys=True, default=str)
        content_hash = hashlib.sha256(policy_json.encode()).hexdigest()
        
        # 메타데이터 해시 (created_at, updated_at, created_by)
        metadata = {
            'created_at': policy.created_at,
            'updated_at': policy.updated_at,
            'created_by': policy.created_by
        }
        metadata_json = json.dumps(metadata, sort_keys=True)
        metadata_hash = hashlib.sha256(metadata_json.encode()).hexdigest()
        
        # 파일 정보 (파일이 있는 경우)
        file_size = 0
        file_mtime = time.time()
        file_hash = ""
        
        if file_path and file_path.exists():
            file_stat = file_path.stat()
            file_size = file_stat.st_size
            file_mtime = file_stat.st_mtime
            
            with open(file_path, 'rb') as f:
                file_content = f.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
        
        # 서명 해시 (서명된 정책의 경우)
        signature_hash = None
        if signed_policy:
            signature_dict = signed_policy.signature.model_dump()
            signature_data = json.dumps(signature_dict, sort_keys=True, default=str)
            signature_hash = hashlib.sha256(signature_data.encode()).hexdigest()
        
        # 스냅샷 전체 해시
        snapshot_data = {
            'policy_id': policy.id,
            'content_hash': content_hash,
            'metadata_hash': metadata_hash,
            'file_hash': file_hash,
            'signature_hash': signature_hash
        }
        snapshot_json = json.dumps(snapshot_data, sort_keys=True)
        snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
        
        # 스냅샷 생성
        snapshot = PolicySnapshot(
            policy_id=policy.id,
            snapshot_hash=snapshot_hash,
            content_hash=content_hash,
            metadata_hash=metadata_hash,
            file_hash=file_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
            file_size=file_size,
            file_mtime=file_mtime,
            signature_hash=signature_hash
        )
        
        # 스냅샷 저장
        self.snapshots[policy.id] = snapshot
        self._save_snapshots()
        
        logger.info(f"Created snapshot for policy {policy.id}: {snapshot_hash[:8]}")
        return snapshot
    
    def check_integrity(
        self,
        policy: NamingConvention,
        file_path: Optional[Path] = None,
        signed_policy: Optional[SignedNamingPolicy] = None
    ) -> Tuple[bool, List[TamperingEvent]]:
        """
        정책 무결성 검증
        
        Args:
            policy: 검증할 정책
            file_path: 정책 파일 경로
            signed_policy: 서명된 정책 (있는 경우)
            
        Returns:
            (무결성_정상, 감지된_이벤트_목록)
        """
        events = []
        
        # 이전 스냅샷 조회
        previous_snapshot = self.snapshots.get(policy.id)
        if not previous_snapshot:
            # 첫 번째 검사 - 스냅샷 생성만
            current_snapshot = self.create_snapshot(policy, file_path, signed_policy)
            return True, []
        
        # 현재 스냅샷 생성
        current_snapshot = self.create_snapshot(policy, file_path, signed_policy)
        
        # 변경 사항 검증
        if previous_snapshot.snapshot_hash != current_snapshot.snapshot_hash:
            # 변경 감지 - 세부 분석
            events.extend(self._analyze_changes(previous_snapshot, current_snapshot))
        
        # 서명 검증 (서명된 정책의 경우)
        if signed_policy:
            signing_manager = get_policy_signing_manager()
            if not signing_manager.verify_policy(signed_policy):
                events.append(self._create_event(
                    policy.id,
                    "critical",
                    "signature_verification_failed",
                    "Policy signature verification failed",
                    {'signer': signed_policy.signature.signer}
                ))
        
        # 이벤트 저장
        if events:
            self.events.extend(events)
            self._save_events()
            
            # SIEM으로 변조 이벤트 전송 (DI 패턴)
            if self.siem_port:
                for event in events:
                    if self._should_send_tampering_event_to_siem(event):
                        asyncio.create_task(self._send_event_to_siem(event))
        
        # 치명적인 이벤트가 있는지 확인
        has_critical = any(event.severity == EventSeverity.CRITICAL for event in events)
        
        return not has_critical, events
    
    def _analyze_changes(
        self,
        previous: PolicySnapshot,
        current: PolicySnapshot
    ) -> List[TamperingEvent]:
        """변경 사항 분석"""
        events = []
        
        # 내용 변경 검사
        if previous.content_hash != current.content_hash:
            events.append(self._create_event(
                current.policy_id,
                "warning",
                "content_modified",
                "Policy content has been modified",
                {
                    'previous_hash': previous.content_hash,
                    'current_hash': current.content_hash
                },
                previous,
                current
            ))
        
        # 메타데이터 변경 검사
        if previous.metadata_hash != current.metadata_hash:
            events.append(self._create_event(
                current.policy_id,
                "info",
                "metadata_modified",
                "Policy metadata has been modified",
                {
                    'previous_hash': previous.metadata_hash,
                    'current_hash': current.metadata_hash
                },
                previous,
                current
            ))
        
        # 파일 변경 검사
        if previous.file_hash != current.file_hash:
            # 파일 크기가 크게 다르면 더 심각한 경고
            size_diff_ratio = abs(current.file_size - previous.file_size) / max(previous.file_size, 1)
            alert_level = "critical" if size_diff_ratio > 0.5 else "warning"
            
            events.append(self._create_event(
                current.policy_id,
                alert_level,
                "file_modified",
                "Policy file has been modified",
                {
                    'previous_hash': previous.file_hash,
                    'current_hash': current.file_hash,
                    'previous_size': previous.file_size,
                    'current_size': current.file_size,
                    'size_diff_ratio': size_diff_ratio
                },
                previous,
                current
            ))
        
        # 서명 변경 검사
        if previous.signature_hash != current.signature_hash:
            events.append(self._create_event(
                current.policy_id,
                "critical",
                "signature_modified",
                "Policy signature has been modified or removed",
                {
                    'previous_hash': previous.signature_hash,
                    'current_hash': current.signature_hash
                },
                previous,
                current
            ))
        
        # 파일 수정 시간 이상 검사
        time_diff = abs(current.file_mtime - previous.file_mtime)
        if time_diff > 0 and previous.content_hash == current.content_hash:
            # 내용은 같은데 파일 시간이 변경됨 - 의심스러운 활동
            events.append(self._create_event(
                current.policy_id,
                "warning",
                "suspicious_file_touch",
                "File modification time changed without content changes",
                {
                    'previous_mtime': previous.file_mtime,
                    'current_mtime': current.file_mtime,
                    'time_diff': time_diff
                },
                previous,
                current
            ))
        
        return events
    
    def _create_event(
        self,
        policy_id: str,
        alert_level: str,  # TamperingAlert 대신 문자열
        event_type: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
        previous_snapshot: Optional[PolicySnapshot] = None,
        current_snapshot: Optional[PolicySnapshot] = None
    ) -> TamperingEvent:
        """변조 이벤트 생성 (새로운 이벤트 모델 사용)"""
        # alert_level을 EventSeverity로 매핑
        severity_map = {
            "info": EventSeverity.INFO,
            "warning": EventSeverity.HIGH,
            "critical": EventSeverity.CRITICAL
        }
        
        # event_type을 TamperingType으로 매핑
        tampering_type_map = {
            "content_modified": TamperingType.SCHEMA_MODIFICATION,
            "metadata_modified": TamperingType.DATA_MANIPULATION,
            "file_modified": TamperingType.DATA_MANIPULATION,
            "signature_modified": TamperingType.SIGNATURE_MISMATCH,
            "signature_verification_failed": TamperingType.SIGNATURE_MISMATCH,
            "suspicious_file_touch": TamperingType.TIMESTAMP_FORGERY
        }
        
        return TamperingEvent(
            event_id=str(uuid.uuid4()),
            validator="PolicyIntegrityChecker",
            object_type="NamingConvention",
            field="policy",
            old_value=str(previous_snapshot.snapshot_hash) if previous_snapshot else "N/A",
            new_value=str(current_snapshot.snapshot_hash) if current_snapshot else "N/A",
            tampering_type=tampering_type_map.get(event_type, TamperingType.DATA_MANIPULATION),
            severity=severity_map.get(alert_level, EventSeverity.MEDIUM),
            detected_at=datetime.now(timezone.utc),
            detection_method="hash_comparison",
            confidence_score=0.95,
            affected_records=1,
            metadata={
                "policy_id": policy_id,
                "event_type": event_type,
                "description": description,
                "details": details or {}
            }
        )
    
    def get_events(
        self,
        policy_id: Optional[str] = None,
        alert_level: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> List[TamperingEvent]:
        """
        이벤트 조회
        
        Args:
            policy_id: 특정 정책 ID로 필터링
            alert_level: 특정 알림 레벨로 필터링
            since: 특정 시간 이후 이벤트만
            
        Returns:
            필터링된 이벤트 목록
        """
        filtered_events = self.events[:]
        
        if policy_id:
            filtered_events = [e for e in filtered_events if e.metadata.get('policy_id') == policy_id]
        
        if alert_level:
            # alert_level을 severity로 매핑
            severity_map = {
                "info": EventSeverity.INFO,
                "warning": EventSeverity.HIGH,  
                "critical": EventSeverity.CRITICAL
            }
            target_severity = severity_map.get(alert_level)
            if target_severity:
                filtered_events = [e for e in filtered_events if e.severity == target_severity]
        
        if since:
            filtered_events = [e for e in filtered_events if e.detected_at >= since]
        
        return filtered_events
    
    def get_policy_status(self, policy_id: str) -> Dict[str, Any]:
        """
        정책 상태 조회
        
        Args:
            policy_id: 정책 ID
            
        Returns:
            정책 상태 정보
        """
        snapshot = self.snapshots.get(policy_id)
        events = self.get_events(policy_id=policy_id)
        
        # 최근 이벤트들 분석
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_events = [e for e in events if e.detected_at >= cutoff_time]
        
        critical_count = sum(1 for e in recent_events if e.severity == EventSeverity.CRITICAL)
        warning_count = sum(1 for e in recent_events if e.severity == EventSeverity.HIGH)
        
        return {
            'policy_id': policy_id,
            'has_snapshot': snapshot is not None,
            'last_snapshot': snapshot.timestamp if snapshot else None,
            'total_events': len(events),
            'recent_events_24h': len(recent_events),
            'critical_events_24h': critical_count,
            'warning_events_24h': warning_count,
            'integrity_status': 'clean' if critical_count == 0 else 'compromised',
            'last_check': datetime.now(timezone.utc).isoformat()
        }
    
    def cleanup_old_events(self, days_to_keep: int = 90):
        """
        오래된 이벤트 정리
        
        Args:
            days_to_keep: 보관할 일수
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        original_count = len(self.events)
        self.events = [e for e in self.events if e.detected_at >= cutoff_date]
        removed_count = original_count - len(self.events)
        
        if removed_count > 0:
            self._save_events()
            logger.info(f"Cleaned up {removed_count} old tampering events")
    
    def generate_integrity_report(self, policy_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        무결성 리포트 생성
        
        Args:
            policy_ids: 특정 정책들만 리포트 (None이면 전체)
            
        Returns:
            무결성 리포트
        """
        if policy_ids is None:
            policy_ids = list(self.snapshots.keys())
        
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_policies': len(policy_ids),
            'policies': {},
            'summary': {
                'clean': 0,
                'warning': 0,
                'compromised': 0
            }
        }
        
        for policy_id in policy_ids:
            status = self.get_policy_status(policy_id)
            report['policies'][policy_id] = status
            
            # 요약 통계 업데이트
            if status['critical_events_24h'] > 0:
                report['summary']['compromised'] += 1
            elif status['warning_events_24h'] > 0:
                report['summary']['warning'] += 1
            else:
                report['summary']['clean'] += 1
        
        return report
    
    async def _send_event_to_siem(self, event: TamperingEvent):
        """변조 이벤트를 SIEM으로 전송 (비동기)"""
        try:
            if self.siem_port:
                await self.siem_port.send(
                    event_type="security.tampering",
                    payload=event.to_dict()
                )
                logger.debug(f"Sent tampering event {event.event_id} to SIEM")
        except Exception as e:
            logger.error(f"Failed to send tampering event to SIEM: {e}")
    
    def _should_send_tampering_event_to_siem(self, event: TamperingEvent) -> bool:
        """SIEM 전송 필요성 판단"""
        import os
        
        # 전체 SIEM 비활성화 체크
        if not os.getenv("ENABLE_SIEM_INTEGRATION", "true").lower() in ("true", "1", "yes"):
            return False
        
        # 변조 감지 SIEM 전송 비활성화 체크
        if not os.getenv("SIEM_SEND_TAMPERING_EVENTS", "true").lower() in ("true", "1", "yes"):
            return False
        
        # CRITICAL 및 HIGH 이벤트는 항상 전송
        if event.severity in (EventSeverity.CRITICAL, EventSeverity.HIGH):
            return True
        
        # INFO 이벤트는 설정에 따라
        if (event.severity == EventSeverity.INFO and 
            os.getenv("SIEM_SEND_INFO_TAMPERING", "false").lower() in ("true", "1", "yes")):
            return True
        
        return False


# 싱글톤 인스턴스
_integrity_checker = None

def get_integrity_checker(snapshot_dir: Optional[str] = None, siem_port: Optional[ISiemPort] = None) -> PolicyIntegrityChecker:
    """무결성 검증자 인스턴스 반환 (DI 지원)"""
    global _integrity_checker
    if not _integrity_checker or snapshot_dir or siem_port:
        _integrity_checker = PolicyIntegrityChecker(
            snapshot_dir=snapshot_dir or "/etc/oms/snapshots",
            siem_port=siem_port
        )
    return _integrity_checker