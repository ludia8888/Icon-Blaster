"""
Validation Logging System
검증 결과 이력 추적 및 감사 로깅 시스템
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from pydantic import BaseModel, Field
from enum import Enum
import threading
from collections import defaultdict, deque
import asyncio

from core.validation.naming_convention import EntityType, NamingValidationResult, ValidationIssue
from core.validation.events import ValidationLogEntry as EventValidationLogEntry
from infra.siem.port import ISiemPort
from utils.logger import get_logger

logger = get_logger(__name__)

# SIEM 통합을 위한 지연 로딩
_siem_integration_enabled = False
_siem_manager = None

def _get_siem_manager():
    """SIEM 관리자 지연 로딩"""
    global _siem_manager, _siem_integration_enabled
    if not _siem_integration_enabled:
        try:
            from core.validation.siem_integration import get_siem_manager
            _siem_manager = get_siem_manager()
            _siem_integration_enabled = True
            logger.info("SIEM integration enabled")
        except ImportError:
            logger.debug("SIEM integration not available")
        except Exception as e:
            logger.warning(f"SIEM integration initialization failed: {e}")
    return _siem_manager


class ValidationOutcome(str, Enum):
    """검증 결과"""
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class ValidationSeverity(str, Enum):
    """검증 심각도"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationLogEntry(BaseModel):
    """검증 로그 항목"""
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # 검증 대상 정보
    entity_type: EntityType
    entity_name: str
    convention_id: str
    
    # 검증 결과
    outcome: ValidationOutcome
    is_valid: bool
    
    # 검증 세부사항
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    suggestions: Dict[str, str] = Field(default_factory=dict)
    
    # 컨텍스트 정보
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    git_commit: Optional[str] = None
    
    # 성능 메트릭
    validation_time_ms: Optional[float] = None
    
    # 추가 메타데이터
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    def to_base_log_entry(self) -> EventValidationLogEntry:
        """events.py의 ValidationLogEntry로 변환"""
        return EventValidationLogEntry(
            log_id=self.log_id,
            validation_id=self.metadata.get('validation_id', self.log_id),
            branch=self.metadata.get('branch', 'main'),
            rule_id=self.convention_id,
            rule_name=f"{self.entity_type}_{self.entity_name}",
            is_valid=self.is_valid,
            error_message=str(self.issues[0]) if self.issues else None,
            execution_time_ms=self.validation_time_ms or 0.0,
            affected_objects=[self.entity_name],
            created_at=datetime.fromisoformat(self.timestamp.replace('Z', '+00:00')) if 'Z' in self.timestamp else datetime.fromisoformat(self.timestamp),
            user_id=self.user_id,
            correlation_id=self.session_id,
            metadata=self.metadata
        )


class ValidationMetrics(BaseModel):
    """검증 메트릭"""
    total_validations: int = 0
    successful_validations: int = 0
    failed_validations: int = 0
    error_validations: int = 0
    
    # 엔티티 타입별 통계
    by_entity_type: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    
    # 시간별 통계 (시간당)
    hourly_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    
    # 성능 통계
    avg_validation_time_ms: float = 0.0
    max_validation_time_ms: float = 0.0
    min_validation_time_ms: float = float('inf')
    
    # 최다 실패 엔티티
    top_failing_entities: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 최다 위반 규칙
    top_violated_rules: List[Dict[str, Any]] = Field(default_factory=list)
    
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ValidationEventStream(BaseModel):
    """실시간 검증 이벤트 스트림"""
    stream_id: str
    events: List[ValidationLogEntry] = Field(default_factory=list)
    max_events: int = 1000
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def add_event(self, event: ValidationLogEntry):
        """이벤트 추가 (FIFO)"""
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events.pop(0)
    
    def get_recent_events(self, count: int = 100) -> List[ValidationLogEntry]:
        """최근 이벤트 조회"""
        return self.events[-count:]


class ValidationLogger:
    """검증 로거 (DI 패턴 적용)"""
    
    def __init__(self, 
                 log_dir: str = "/var/log/oms/validation",
                 max_log_size_mb: int = 100,
                 max_log_files: int = 10,
                 enable_stream: bool = True,
                 siem_port: Optional[ISiemPort] = None):
        """
        초기화
        
        Args:
            log_dir: 로그 저장 디렉토리
            max_log_size_mb: 최대 로그 파일 크기 (MB)
            max_log_files: 최대 로그 파일 수
            enable_stream: 실시간 스트림 활성화
            siem_port: SIEM 포트 (의존성 주입)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.siem_port = siem_port
        
        self.max_log_size_bytes = max_log_size_mb * 1024 * 1024
        self.max_log_files = max_log_files
        self.enable_stream = enable_stream
        
        # 로그 파일 설정
        self.current_log_file = self.log_dir / "validation.log"
        self.metrics_file = self.log_dir / "metrics.json"
        
        # 메트릭 및 스트림
        self.metrics = self._load_metrics()
        self.event_streams: Dict[str, ValidationEventStream] = {}
        
        # 스레드 안전성
        self.lock = threading.Lock()
        
        # 인메모리 캐시 (성능 최적화)
        self.recent_logs = deque(maxlen=1000)
        self.failure_cache = defaultdict(int)  # 실패 엔티티 카운터
        self.rule_violation_cache = defaultdict(int)  # 규칙 위반 카운터
    
    def _load_metrics(self) -> ValidationMetrics:
        """메트릭 로드"""
        if not self.metrics_file.exists():
            return ValidationMetrics()
        
        try:
            with open(self.metrics_file, 'r') as f:
                data = json.load(f)
            return ValidationMetrics(**data)
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
            return ValidationMetrics()
    
    def _save_metrics(self):
        """메트릭 저장"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(self.metrics.model_dump(), f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def log_validation(self,
                      entity_type: EntityType,
                      entity_name: str,
                      result: NamingValidationResult,
                      convention_id: str,
                      user_id: Optional[str] = None,
                      session_id: Optional[str] = None,
                      source_file: Optional[str] = None,
                      line_number: Optional[int] = None,
                      git_commit: Optional[str] = None,
                      validation_time_ms: Optional[float] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> ValidationLogEntry:
        """
        검증 결과 로깅
        
        Args:
            entity_type: 엔티티 타입
            entity_name: 엔티티 이름
            result: 검증 결과
            convention_id: 사용된 명명 규칙 ID
            user_id: 사용자 ID
            session_id: 세션 ID
            source_file: 소스 파일 경로
            line_number: 라인 번호
            git_commit: Git 커밋 해시
            validation_time_ms: 검증 소요 시간 (ms)
            metadata: 추가 메타데이터
            
        Returns:
            생성된 로그 항목
        """
        with self.lock:
            # 검증 결과 분류
            if result.is_valid:
                outcome = ValidationOutcome.SUCCESS
            else:
                # 오류 vs 일반 실패 구분
                has_critical = any(issue.severity == "error" for issue in result.issues)
                outcome = ValidationOutcome.ERROR if has_critical else ValidationOutcome.FAILURE
            
            # 이슈를 딕셔너리로 변환
            issues_data = []
            for issue in result.issues:
                issue_dict = issue.model_dump() if hasattr(issue, 'model_dump') else {
                    'entity_type': str(issue.entity_type) if hasattr(issue, 'entity_type') else str(entity_type),
                    'entity_name': issue.entity_name if hasattr(issue, 'entity_name') else entity_name,
                    'rule_violated': issue.rule_violated if hasattr(issue, 'rule_violated') else 'unknown',
                    'severity': issue.severity if hasattr(issue, 'severity') else 'warning',
                    'message': issue.message if hasattr(issue, 'message') else 'Unknown issue',
                    'suggestion': getattr(issue, 'suggestion', None),
                    'auto_fixable': getattr(issue, 'auto_fixable', False)
                }
                issues_data.append(issue_dict)
            
            # 로그 항목 생성
            log_entry = ValidationLogEntry(
                entity_type=entity_type,
                entity_name=entity_name,
                convention_id=convention_id,
                outcome=outcome,
                is_valid=result.is_valid,
                issues=issues_data,
                suggestions=result.suggestions,
                user_id=user_id,
                session_id=session_id,
                source_file=source_file,
                line_number=line_number,
                git_commit=git_commit,
                validation_time_ms=validation_time_ms,
                metadata=metadata or {}
            )
            
            # 로그 저장
            self._write_log_entry(log_entry)
            
            # 메트릭 업데이트
            self._update_metrics(log_entry)
            
            # 스트림에 추가
            if self.enable_stream:
                self._add_to_streams(log_entry)
            
            # 인메모리 캐시 업데이트
            self.recent_logs.append(log_entry)
            
            # SIEM 통합 - 조건부 전송 (DI 패턴)
            if self.siem_port:
                asyncio.create_task(self._send_to_siem(log_entry))
            
            return log_entry
    
    def _write_log_entry(self, entry: ValidationLogEntry):
        """로그 항목을 파일에 기록"""
        try:
            # 로그 순환 확인
            if (self.current_log_file.exists() and 
                self.current_log_file.stat().st_size > self.max_log_size_bytes):
                self._rotate_logs()
            
            # 로그 기록
            with open(self.current_log_file, 'a') as f:
                json.dump(entry.model_dump(), f, default=str)
                f.write('\n')
                
        except Exception as e:
            logger.error(f"Failed to write log entry: {e}")
    
    def _rotate_logs(self):
        """로그 파일 순환"""
        try:
            # 기존 파일들 순환
            for i in range(self.max_log_files - 1, 0, -1):
                old_file = self.log_dir / f"validation.log.{i}"
                new_file = self.log_dir / f"validation.log.{i + 1}"
                if old_file.exists():
                    if new_file.exists():
                        new_file.unlink()
                    old_file.rename(new_file)
            
            # 현재 파일을 .1로 이동
            if self.current_log_file.exists():
                archive_file = self.log_dir / "validation.log.1"
                if archive_file.exists():
                    archive_file.unlink()
                self.current_log_file.rename(archive_file)
            
            logger.info("Log files rotated")
            
        except Exception as e:
            logger.error(f"Failed to rotate logs: {e}")
    
    def _update_metrics(self, entry: ValidationLogEntry):
        """메트릭 업데이트"""
        # 전체 통계
        self.metrics.total_validations += 1
        
        if entry.outcome == ValidationOutcome.SUCCESS:
            self.metrics.successful_validations += 1
        elif entry.outcome == ValidationOutcome.FAILURE:
            self.metrics.failed_validations += 1
        else:  # ERROR
            self.metrics.error_validations += 1
        
        # 엔티티 타입별 통계
        entity_type_str = entry.entity_type.value
        if entity_type_str not in self.metrics.by_entity_type:
            self.metrics.by_entity_type[entity_type_str] = {
                'total': 0, 'success': 0, 'failure': 0, 'error': 0
            }
        
        self.metrics.by_entity_type[entity_type_str]['total'] += 1
        self.metrics.by_entity_type[entity_type_str][entry.outcome.value] += 1
        
        # 시간별 통계
        hour_key = entry.timestamp[:13]  # YYYY-MM-DDTHH
        if hour_key not in self.metrics.hourly_stats:
            self.metrics.hourly_stats[hour_key] = {
                'total': 0, 'success': 0, 'failure': 0, 'error': 0
            }
        
        self.metrics.hourly_stats[hour_key]['total'] += 1
        self.metrics.hourly_stats[hour_key][entry.outcome.value] += 1
        
        # 성능 메트릭
        if entry.validation_time_ms is not None:
            # 평균 계산 (점진적 업데이트)
            n = self.metrics.total_validations
            self.metrics.avg_validation_time_ms = (
                (self.metrics.avg_validation_time_ms * (n - 1) + entry.validation_time_ms) / n
            )
            
            self.metrics.max_validation_time_ms = max(
                self.metrics.max_validation_time_ms, entry.validation_time_ms
            )
            self.metrics.min_validation_time_ms = min(
                self.metrics.min_validation_time_ms, entry.validation_time_ms
            )
        
        # 실패 엔티티 카운터 업데이트
        if not entry.is_valid:
            key = f"{entity_type_str}:{entry.entity_name}"
            self.failure_cache[key] += 1
        
        # 규칙 위반 카운터 업데이트
        for issue in entry.issues:
            rule = issue.get('rule_violated', 'unknown')
            self.rule_violation_cache[rule] += 1
        
        # 시간대별 오래된 데이터 정리 (메모리 절약)
        cutoff_time = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H")
        old_hours = [hour for hour in self.metrics.hourly_stats.keys() if hour < cutoff_time]
        for hour in old_hours:
            del self.metrics.hourly_stats[hour]
        
        # 주기적으로 Top 리스트 업데이트 (성능을 위해 1000번마다)
        if self.metrics.total_validations % 1000 == 0:
            self._update_top_lists()
        
        self.metrics.last_updated = datetime.now(timezone.utc).isoformat()
        
        # 메트릭 저장 (주기적으로)
        if self.metrics.total_validations % 100 == 0:
            self._save_metrics()
    
    def _update_top_lists(self):
        """Top 실패 엔티티 및 위반 규칙 업데이트"""
        # Top 실패 엔티티
        top_failures = sorted(self.failure_cache.items(), 
                             key=lambda x: x[1], reverse=True)[:10]
        self.metrics.top_failing_entities = [
            {'entity': entity, 'count': count} for entity, count in top_failures
        ]
        
        # Top 위반 규칙
        top_violations = sorted(self.rule_violation_cache.items(),
                               key=lambda x: x[1], reverse=True)[:10]
        self.metrics.top_violated_rules = [
            {'rule': rule, 'count': count} for rule, count in top_violations
        ]
    
    def _add_to_streams(self, entry: ValidationLogEntry):
        """이벤트 스트림에 추가"""
        # 전체 스트림
        if 'global' not in self.event_streams:
            self.event_streams['global'] = ValidationEventStream(stream_id='global')
        self.event_streams['global'].add_event(entry)
        
        # 엔티티 타입별 스트림
        entity_stream_id = f"entity_{entry.entity_type.value}"
        if entity_stream_id not in self.event_streams:
            self.event_streams[entity_stream_id] = ValidationEventStream(stream_id=entity_stream_id)
        self.event_streams[entity_stream_id].add_event(entry)
        
        # 사용자별 스트림 (세션이 있는 경우)
        if entry.session_id:
            session_stream_id = f"session_{entry.session_id}"
            if session_stream_id not in self.event_streams:
                self.event_streams[session_stream_id] = ValidationEventStream(stream_id=session_stream_id)
            self.event_streams[session_stream_id].add_event(entry)
    
    def get_metrics(self) -> ValidationMetrics:
        """현재 메트릭 조회"""
        with self.lock:
            # 실시간 Top 리스트 업데이트
            self._update_top_lists()
            self.metrics.last_updated = datetime.now(timezone.utc).isoformat()
            return self.metrics
    
    def get_logs(self,
                 entity_type: Optional[EntityType] = None,
                 outcome: Optional[ValidationOutcome] = None,
                 user_id: Optional[str] = None,
                 session_id: Optional[str] = None,
                 since: Optional[datetime] = None,
                 limit: int = 100) -> List[ValidationLogEntry]:
        """
        로그 조회
        
        Args:
            entity_type: 엔티티 타입 필터
            outcome: 결과 필터
            user_id: 사용자 ID 필터
            session_id: 세션 ID 필터
            since: 시간 필터
            limit: 최대 결과 수
            
        Returns:
            필터링된 로그 목록
        """
        with self.lock:
            # 최근 캐시에서 먼저 검색 (성능 최적화)
            logs = list(self.recent_logs)
            
            # 필터 적용
            if entity_type:
                logs = [log for log in logs if log.entity_type == entity_type]
            
            if outcome:
                logs = [log for log in logs if log.outcome == outcome]
            
            if user_id:
                logs = [log for log in logs if log.user_id == user_id]
            
            if session_id:
                logs = [log for log in logs if log.session_id == session_id]
            
            if since:
                since_str = since.isoformat()
                logs = [log for log in logs if log.timestamp >= since_str]
            
            # 최신순으로 정렬하고 제한
            logs.sort(key=lambda x: x.timestamp, reverse=True)
            return logs[:limit]
    
    def get_event_stream(self, stream_id: str) -> Optional[ValidationEventStream]:
        """이벤트 스트림 조회"""
        return self.event_streams.get(stream_id)
    
    def get_failure_summary(self, 
                           entity_type: Optional[EntityType] = None,
                           hours: int = 24) -> Dict[str, Any]:
        """
        실패 요약 정보
        
        Args:
            entity_type: 특정 엔티티 타입
            hours: 조회할 시간 범위
            
        Returns:
            실패 요약 정보
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_logs = self.get_logs(entity_type=entity_type, since=since, limit=10000)
        
        failed_logs = [log for log in recent_logs if not log.is_valid]
        
        # 실패 유형별 분석
        failure_types = defaultdict(int)
        failing_entities = defaultdict(int)
        violated_rules = defaultdict(int)
        
        for log in failed_logs:
            for issue in log.issues:
                rule = issue.get('rule_violated', 'unknown')
                violated_rules[rule] += 1
                failure_types[rule] += 1
            
            failing_entities[f"{log.entity_type.value}:{log.entity_name}"] += 1
        
        return {
            'time_range_hours': hours,
            'total_failures': len(failed_logs),
            'total_validations': len(recent_logs),
            'failure_rate': len(failed_logs) / max(len(recent_logs), 1),
            'top_failure_types': sorted(failure_types.items(), 
                                      key=lambda x: x[1], reverse=True)[:5],
            'top_failing_entities': sorted(failing_entities.items(),
                                         key=lambda x: x[1], reverse=True)[:5],
            'top_violated_rules': sorted(violated_rules.items(),
                                       key=lambda x: x[1], reverse=True)[:5]
        }
    
    def export_logs(self, 
                   start_time: datetime,
                   end_time: datetime,
                   output_file: str,
                   format: str = 'json') -> bool:
        """
        로그 내보내기
        
        Args:
            start_time: 시작 시간
            end_time: 종료 시간
            output_file: 출력 파일 경로
            format: 출력 형식 ('json' 또는 'csv')
            
        Returns:
            내보내기 성공 여부
        """
        try:
            logs = self.get_logs(since=start_time, limit=100000)
            end_str = end_time.isoformat()
            logs = [log for log in logs if log.timestamp <= end_str]
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if format == 'json':
                with open(output_path, 'w') as f:
                    json.dump([log.model_dump() for log in logs], f, indent=2, default=str)
            
            elif format == 'csv':
                import csv
                with open(output_path, 'w', newline='') as f:
                    if logs:
                        writer = csv.DictWriter(f, fieldnames=logs[0].model_dump().keys())
                        writer.writeheader()
                        for log in logs:
                            # JSON 필드는 문자열로 변환
                            row = log.model_dump()
                            for key, value in row.items():
                                if isinstance(value, (dict, list)):
                                    row[key] = json.dumps(value)
                            writer.writerow(row)
            
            logger.info(f"Exported {len(logs)} log entries to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export logs: {e}")
            return False
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """오래된 로그 정리"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            
            # 로그 파일들 정리
            for log_file in self.log_dir.glob("validation.log.*"):
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    logger.info(f"Removed old log file: {log_file}")
            
            # 메트릭의 시간별 데이터 정리
            cutoff_str = cutoff_date.strftime("%Y-%m-%dT%H")
            old_hours = [hour for hour in self.metrics.hourly_stats.keys() if hour < cutoff_str]
            for hour in old_hours:
                del self.metrics.hourly_stats[hour]
            
            if old_hours:
                self._save_metrics()
                logger.info(f"Cleaned up {len(old_hours)} old hourly metrics")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
    
    async def _send_to_siem(self, log_entry: ValidationLogEntry):
        """비동기로 SIEM으로 로그 전송 (DI 패턴)"""
        try:
            if self.siem_port and self._should_send_to_siem(log_entry):
                # ValidationLogEntry를 기본 ValidationLogEntry로 변환
                base_log_entry = log_entry.to_base_log_entry()
                await self.siem_port.send(
                    event_type="validation.log",
                    payload=base_log_entry.to_dict()
                )
                logger.debug(f"Sent validation log {log_entry.log_id} to SIEM")
        except Exception as e:
            logger.error(f"Failed to send log to SIEM: {e}")
    
    def _should_send_to_siem(self, log_entry: ValidationLogEntry) -> bool:
        """SIEM 전송 필요성 판단"""
        # 환경 변수나 설정으로 제어 가능
        import os
        
        # 전체 SIEM 비활성화 체크
        if not os.getenv("ENABLE_SIEM_INTEGRATION", "true").lower() in ("true", "1", "yes"):
            return False
        
        # 성공 케이스 제외 (설정 가능)
        if (log_entry.outcome == ValidationOutcome.SUCCESS and 
            not os.getenv("SIEM_INCLUDE_SUCCESS", "false").lower() in ("true", "1", "yes")):
            return False
        
        # 보안 관련 이벤트는 항상 전송
        if log_entry.metadata.get("security_issues") or log_entry.metadata.get("was_sanitized"):
            return True
        
        # 실패/오류 케이스는 전송
        if log_entry.outcome in (ValidationOutcome.FAILURE, ValidationOutcome.ERROR):
            return True
        
        return False
    
    def send_security_event_to_siem(self, event_data: Dict[str, Any]):
        """보안 이벤트를 SIEM으로 직접 전송"""
        try:
            siem_manager = _get_siem_manager()
            if siem_manager:
                siem_manager.send_security_event(event_data)
                logger.info(f"Sent security event to SIEM: {event_data.get('action', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to send security event to SIEM: {e}")


# 싱글톤 인스턴스
_validation_logger = None

def get_validation_logger(
    log_dir: Optional[str] = None,
    max_log_size_mb: int = 100,
    max_log_files: int = 10,
    enable_stream: bool = True,
    siem_port: Optional[ISiemPort] = None
) -> ValidationLogger:
    """검증 로거 인스턴스 반환 (DI 지원)"""
    global _validation_logger
    if not _validation_logger or log_dir or siem_port:
        _validation_logger = ValidationLogger(
            log_dir=log_dir or "/var/log/oms/validation",
            max_log_size_mb=max_log_size_mb,
            max_log_files=max_log_files,
            enable_stream=enable_stream,
            siem_port=siem_port
        )
    return _validation_logger


def log_validation_result(
    entity_type: EntityType,
    entity_name: str,
    result: NamingValidationResult,
    convention_id: str = "default",
    **kwargs
) -> ValidationLogEntry:
    """편의 함수: 검증 결과 로깅"""
    logger_instance = get_validation_logger()
    return logger_instance.log_validation(
        entity_type, entity_name, result, convention_id, **kwargs
    )